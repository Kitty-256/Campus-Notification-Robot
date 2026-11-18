"""回填发布时间：把列表页上的日期补进 raw_items.published_at。

背景：/今日 现在按「发布时间」倒序；但历史条目的 published_at 在入库时被写成了
      抓取当天（当时还没从列表页取日期）。这个脚本重新读一遍各源的列表页，
      按 URL 对齐，把真实发布日期覆盖上去。

判定条件：published_at 为空，或等于抓取日期（说明只是占位值）。
只 UPDATE，不新增通知 → 不会触发群推送。

    python scripts/backfill_published.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "svc"))

from app.collect import browser, generic          # noqa: E402
from app.db import execute, init_db, query        # noqa: E402
from app.jobs.crawl import load_sources           # noqa: E402
from app.parse import find_publish_date            # noqa: E402


def list_links(src: dict) -> list[dict]:
    if src.get("kind") == "browser":
        s = dict(src)
        s["fetch_detail"] = False          # 只要列表，不抓正文
        s["limit"] = int(s.get("limit", 20))
        return browser.collect(s)
    return generic.fetch_list(src)


def main() -> int:
    init_db()
    total = 0
    for src in load_sources():
        try:
            links = list_links(src)
        except Exception as e:                          # noqa: BLE001
            print(f"- {src['id']} 取列表失败：{str(e)[:80]}")
            continue
        hit = 0
        for link in links:
            pub = link.get("published_at")
            if not pub:
                continue
            rows = query(
                """SELECT id FROM raw_items
                   WHERE url=?
                     AND (published_at IS NULL OR published_at=''
                          OR published_at = substr(fetched_at,1,10))""",
                (link["url"],),
            )
            for r in rows:
                execute("UPDATE raw_items SET published_at=? WHERE id=?", (pub, r["id"]))
                hit += 1
        print(f"- {src['id']}: 列表 {len(links)} 条，回填 {hit} 条")
        total += hit
        time.sleep(1)

    # 第二遍：列表页没有日期的（首页卡片型），从已存的正文里找「发布时间：」
    print("\n--- 从已存正文里找发布时间（不发请求）---")
    rows = query(
        """SELECT id, content FROM raw_items
           WHERE (published_at IS NULL OR published_at=''
                  OR published_at = substr(fetched_at,1,10))
             AND length(coalesce(content,'')) > 50""")
    hit2 = 0
    for r in rows:
        pub = find_publish_date(r["content"] or "")
        if pub:
            execute("UPDATE raw_items SET published_at=? WHERE id=?", (pub, r["id"]))
            hit2 += 1
    total += hit2
    print(f"  从正文补到 {hit2} 条（共检查 {len(rows)} 条）")

    left = query("SELECT COUNT(*) c FROM raw_items "
                 "WHERE published_at IS NULL OR published_at=''")[0]["c"]
    print(f"\n完成：回填 {total} 条；仍无发布时间的 {left} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
