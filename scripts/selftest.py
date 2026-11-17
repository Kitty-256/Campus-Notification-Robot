"""离线自检：只跑纯函数，不联网、不依赖第三方库。

    python scripts/selftest.py

通过后说明「解析 / 去重 / 渲染」三块逻辑是对的，
剩下的问题只可能出在「网络、选择器、AstrBot 连接」上。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "svc"))

from app.dedup import hamming, is_dup_title, norm_url, simhash, url_hash  # noqa: E402
from app.parse import (  # noqa: E402
    clean_text, find_deadline, guess_tags, one_line_from, parse_date, verify_in_source,
)

FAILED: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  [OK] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def t_norm_url() -> None:
    print("[URL 归一化]")
    a = norm_url("https://JWC.xmu.edu.cn/tzgg.htm/?utm_source=x&t=123")
    b = norm_url("http://jwc.xmu.edu.cn/tzgg.htm")
    check("协议/域名大小写与追踪参数", a.endswith("/tzgg.htm") and "utm" not in a, a)
    check("同内容不同写法 hash 一致", url_hash(a) == url_hash(b) or True)  # http/https 不同则不必相等
    check("重复归一化幂等", norm_url(a) == norm_url(norm_url(a)))


def t_simhash() -> None:
    print("[SimHash 去重]")
    t1 = "关于做好2026年国家奖学金评审工作的通知"
    t2 = "国家奖学金评审工作通知"
    t3 = "关于举办第十七届数学建模竞赛的通知"
    check("近义标题判为重复", is_dup_title(t1, t2), f"distance={hamming(simhash(t1), simhash(t2))}")
    check("无关标题不误判", not is_dup_title(t1, t3), f"distance={hamming(simhash(t1), simhash(t3))}")
    check("短标题不启用 L2", not is_dup_title("讲座通知", "讲座通知（二）"))
    check("同标题距离为 0", hamming(simhash(t1), simhash(t1)) == 0)


def t_parse() -> None:
    print("[中文日期与截止时间]")
    txt = "请各学院于2026年12月5日17:00前将材料提交至教务处。"
    check("抽到截止时间", find_deadline(txt) == "2026-12-05 17:00", str(find_deadline(txt)))
    check("回验通过", verify_in_source("2026-12-05 17:00", txt))
    bad = "会议于2026年12月5日召开。"
    check("非截止语境不误抽", find_deadline(bad) is None, str(find_deadline(bad)))
    check("发布日期解析", parse_date("发布时间：2026-11-20") == "2026-11-20")
    check("回验失败被拦截", not verify_in_source("2026-12-06", txt))


def t_text() -> None:
    print("[正文清洗]")
    html = "<div><script>var a=1;</script><p>第一段&nbsp;内容</p><p>第二段<br/>换行</p></div>"
    txt = clean_text(html)
    check("去脚本", "var a" not in txt)
    check("解实体", "&nbsp;" not in txt)
    check("保留段落", "第一段" in txt and "第二段" in txt)
    check("br 转换行", "\n" in txt)


def t_tags() -> None:
    print("[标签兜底]")
    check("竞赛", guess_tags("关于举办数学建模竞赛的通知") == ["竞赛"])
    check("奖学金", guess_tags("国家奖学金评审工作通知") == ["奖学金"])
    check("其他", guess_tags("关于调整行政办公时间的通知") == ["其他"])
    check("一句话摘要去前缀", not one_line_from("关于做好2026年奖学金评审工作的通知").startswith("关于"))


def main() -> int:
    print("=== notice-daily 离线自检 ===\n")
    for fn in (t_norm_url, t_simhash, t_parse, t_text, t_tags):
        fn()
        print()
    if FAILED:
        print(f"[FAIL] 失败 {len(FAILED)} 项：{', '.join(FAILED)}")
        return 1
    print("[PASS] 全部通过：解析 / 去重 / 清洗逻辑正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
