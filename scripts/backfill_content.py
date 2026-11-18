"""回填正文：给「只抓到标题」的旧条目补正文，并就地更新对应通知的截止时间/标签。

背景：浏览器源（信息学院）最初只取列表，条目入库时没有正文，生成的是一句话通知。
后来给浏览器源加了详情抓取，但那只对「新条目」生效，已入库的旧条目不会自动补。

这个脚本只做 UPDATE，不新增通知 → **不会触发实时推送**，不会在群里刷屏。

    python scripts/backfill_content.py            # 默认只处理 browser 源
    python scripts/backfill_content.py --all      # 处理所有缺正文的条目
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "svc"))

from app.collect.generic import fetch_detail          # noqa: E402
from app.db import execute, init_db, query           # noqa: E402
from app.parse import find_deadline, guess_tags      # noqa: E402

ONLY_BROWSER = "--all" not in sys.argv
MIN_LEN = 50


def main() -> int:
    init_db()
    sql = """SELECT r.id, r.source, r.url, r.title, n.id AS nid
             FROM raw_items r JOIN notices n ON n.raw_id = r.id
             WHERE length(coalesce(r.content,'')) < ?"""
    params: list = [MIN_LEN]
    if ONLY_BROWSER:
        sql += " AND r.source LIKE 'informatics%'"
    sql += " ORDER BY r.id DESC"
    rows = query(sql, params)
    print(f"待补正文的条目：{len(rows)} 条")

    year = int(time.strftime("%Y"))
    done = 0
    for r in rows:
        txt = fetch_detail(r["url"])
        if not txt or len(txt) < MIN_LEN:
            print(f"  - 跳过（正文太短）：{r['title'][:36]}")
            continue
        dl = find_deadline(txt, default_year=year)
        tags = guess_tags(r["title"], txt)
        execute("UPDATE raw_items SET content=? WHERE id=?", (txt, r["id"]))
        execute(
            """UPDATE notices SET deadline=COALESCE(NULLIF(deadline,''), ?),
                                  tags=?, one_line=COALESCE(NULLIF(one_line,''), ?)
               WHERE id=?""",
            (dl, __import__("json").dumps(tags, ensure_ascii=False),
             r["title"][:60], r["nid"]),
        )
        done += 1
        print(f"  + {r['title'][:36]}  ({len(txt)} 字" + (f"，截止 {dl}" if dl else "") + ")")
        time.sleep(1)

    print(f"\n完成：{done} 条补上正文（未新增通知，不会触发群推送）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
