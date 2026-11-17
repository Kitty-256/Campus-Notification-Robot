"""离线端到端演练：不联网、不调 LLM、不起 HTTP，直接跑「入库 → 去重 → 摘要 → 日报」。

    python scripts/dryrun.py

用途：
1. 验证 pipeline 是否通（真机上出问题时，先跑它，能区分「逻辑坏」还是「网络坏」）；
2. 给答辩演示留一个不依赖外网的兜底脚本。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "svc"))

# 必须在 import app.* 之前设置环境变量
TMP = Path(tempfile.gettempdir()) / "notice_dryrun.db"
for f in (TMP, Path(str(TMP) + "-wal"), Path(str(TMP) + "-shm")):
    if f.exists():
        f.unlink()
os.environ["DB_PATH"] = str(TMP)
os.environ["SOURCES_FILE"] = str(TMP.with_suffix(".sources.yaml"))
os.environ["LLM_API_KEY"] = ""            # 强制走降级摘要，保证离线可跑

from app import db, pipeline                       # noqa: E402
from app.llm import fallback_summary               # noqa: E402
from app.parse import clean_text, find_deadline    # noqa: E402

SAMPLES = [
    {
        "source": "jwc",
        "url": "https://jwc.xmu.edu.cn/info/1000/1234.htm?utm_source=wechat",
        "title": "关于做好2026年国家奖学金评审工作的通知",
        "content": "请各学院于2026年12月5日17:00前完成材料初审，并将汇总表提交至教务处。联系人：张老师。",
    },
    {
        # 同一条通知被学院转载：标题略不同、URL 不同 —— 应当被判为重复
        "source": "informatics",
        "url": "https://informatics.xmu.edu.cn/info/1089/7157.htm",
        "title": "国家奖学金评审工作通知",
        "content": "请各单位于2026年12月5日17:00前完成初审并提交材料。",
    },
    {
        "source": "gs",
        "url": "https://gs.xmu.edu.cn/info/1891/45521.htm",
        "title": "关于举办第十七届数学建模竞赛校内选拔赛的通知",
        "content": "报名截止时间为2026年11月30日24:00，请登录竞赛系统提交。比赛设一等奖、二等奖若干。",
    },
    {
        # 正文太短（多为图片型正文/纯附件），应被标 short_content 而不生成通知
        "source": "lib",
        "url": "https://library.xmu.edu.cn/info/1/2.htm",
        "title": "闭馆通知",
        "content": "详见附件。",
    },
]


def main() -> int:
    print("=== notice-daily 离线演练 ===\n")
    db.init_db()
    print(f"数据库：{TMP}\n")

    r1 = pipeline.ingest(SAMPLES)
    print(f"[1] 入库结果：accepted={r1['accepted']} skipped={r1['skipped']}")

    r2 = pipeline.ingest(SAMPLES)          # 再灌一遍，验证幂等
    print(f"[2] 重复入库：accepted={r2['accepted']} skipped={r2['skipped']}（应为 0 / 4）")

    r3 = pipeline.process_pending()
    print(f"[3] 处理结果：created={r3['created']} dup={r3['dup']} "
          f"dropped={r3['dropped']} scanned={r3['scanned']}")

    d = pipeline.digest(limit=12)
    print(f"\n[4] 今日日报（{d['date']}，共 {d['total']} 条）")
    print("-" * 72)
    for i, it in enumerate(d["items"], 1):
        dl = it.get("deadline") or "-"
        print(f"{i}. {it['one_line']}")
        print(f"   截止：{dl} ｜ 标签：{','.join(it['tags']) or '-'} ｜ score={it['score']}")
        print(f"   {it['url']}")
    print("-" * 72)

    s = pipeline.search("奖学金")
    print(f"\n[5] 检索「奖学金」：{len(s['items'])} 条")
    for it in s["items"]:
        print(f"   · {it['title']}")

    st = pipeline.stats()
    print(f"[6] 源状态：{len(st['sources'])} 个源有日志（离线演练不抓取，应为 0）")

    # ---- 断言：这就是这一批的验收标准
    ok = True
    ok &= r2["accepted"] == 0
    ok &= r3["created"] >= 2
    ok &= r3["dup"] >= 1
    ok &= r3["dropped"] >= 1
    ok &= d["total"] >= 2
    ok &= any(it["deadline"] for it in d["items"])

    print("\n" + ("[PASS] 流水线正常：入库幂等 / 跨源去重 / 截止时间抽取 / 降级摘要 全部生效"
                  if ok else "[FAIL] 有断言未通过，见上面输出"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
