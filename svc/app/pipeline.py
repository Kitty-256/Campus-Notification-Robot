"""流水线：入库 → 解析 → 去重 → 摘要 → 打分 → 成文。

所有步骤都是幂等的：同一条 url 重复入库不会产生第二条通知。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from .db import execute, log_fetch, now_str, query, query_one
from .dedup import days_apart, is_dup_title, simhash, url_hash
from .llm import summarize
from .parse import clean_text, find_deadline, guess_tags, one_line_from, parse_date
from .settings import settings

CLUSTER_WINDOW_DAYS = 3
MIN_CONTENT_LEN = 30


def ingest(items: list[dict]) -> dict:
    """把采集结果写进 raw_items。返回 accepted / skipped。"""
    accepted = skipped = 0
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or "").strip()
        if not url or not title:
            skipped += 1
            continue
        uh = url_hash(url)
        if query_one("SELECT id FROM raw_items WHERE url_hash=?", (uh,)):
            skipped += 1
            continue
        content = clean_text(it.get("content")) or None
        # 注意：不要拿正文里第一个日期当发布时间——那通常是截止时间。
        pub = it.get("published_at") or now_str()[:10]
        execute(
            """INSERT INTO raw_items(source, url, url_hash, title, content,
                                    published_at, fetched_at)
               VALUES(?,?,?,?,?,?,?)""",
            (it.get("source") or "unknown", url, uh, title, content, pub, now_str()),
        )
        accepted += 1
    return {"accepted": accepted, "skipped": skipped}


def _recent_notices(days: int = CLUSTER_WINDOW_DAYS) -> list[dict]:
    since = (datetime.strptime(now_str(), "%Y-%m-%d %H:%M:%S")
             - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = query(
        "SELECT id, cluster_id, title, created_at FROM notices WHERE created_at >= ?",
        (since,),
    )
    return [dict(r) for r in rows]


def _urgency(deadline: str | None) -> float:
    if not deadline:
        return 0.3
    try:
        fmt = "%Y-%m-%d %H:%M" if len(deadline) > 10 else "%Y-%m-%d"
        dl = datetime.strptime(deadline[:16] if len(deadline) > 10 else deadline[:10], fmt)
    except ValueError:
        return 0.3
    left = (dl - datetime.strptime(now_str()[:10], "%Y-%m-%d")).days
    if left < 0:
        return 0.05
    if left <= 3:
        return 1.0
    if left <= 7:
        return 0.7
    return 0.45


def process_pending(limit: int = 50) -> dict:
    """处理未处理的原始条目：去重 → 摘要 → 写 notices。"""
    rows = query(
        "SELECT * FROM raw_items WHERE processed=0 ORDER BY id LIMIT ?", (limit,)
    )
    recent = _recent_notices()
    created = dup = dropped = 0

    for row in rows:
        item = dict(row)
        content = item.get("content") or ""
        if len(content) < MIN_CONTENT_LEN and len(item["title"]) < 10:
            # 正文空、标题也短：多半是「更多>>」「闭馆通知」这类，不值得生成
            execute("UPDATE raw_items SET processed=1, note='short_content' WHERE id=?",
                    (item["id"],))
            dropped += 1
            continue

        # ---- L2 标题级去重（L1 已在 ingest 用 url_hash 做掉）
        # 时间窗用「抓取时间」而不是「发布时间」：后者常缺，或被抓成截止时间。
        cluster_id = None
        for n in recent:
            if days_apart(item["fetched_at"], n["created_at"]) <= CLUSTER_WINDOW_DAYS \
                    and is_dup_title(item["title"], n["title"]):
                cluster_id = n["cluster_id"] or n["id"]
                break
        if cluster_id:
            dup += 1
            execute("UPDATE raw_items SET processed=1, note=? WHERE id=?",
                    (f"dup_of_cluster_{cluster_id}", item["id"]))
            continue

        # ---- 摘要：正文为空/过短时不调模型（会诱发编造），直接用标题降级
        title_only = len(content) < MIN_CONTENT_LEN
        if title_only:
            from .llm import fallback_summary
            data = fallback_summary(item["title"], content)
        else:
            data = summarize(item["title"], content, item["url"], item["source"])

        deadline = data.get("deadline") or find_deadline(content)
        tags = data.get("tags") or guess_tags(item["title"], content)
        one_line = data.get("one_line") or one_line_from(item["title"], content)
        score = round(_urgency(deadline), 3)
        # 只有「模型给了结果但自己都不确信」才进人工队列；
        # 降级摘要（没配 Key / 模型挂了）照常发布，否则没 Key 时日报永远是空的。
        degraded = bool(data.get("_degraded"))
        status = "review" if (not degraded and float(data.get("confidence") or 0) < 0.5) \
            else "published"

        nid = execute(
            """INSERT INTO notices(raw_id, cluster_id, title, one_line, who, deadline,
                                   place, tags, source, url, score, confidence, status, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item["id"], None, item["title"], one_line, data.get("who"), deadline,
             data.get("place"), json.dumps(tags, ensure_ascii=False), item["source"],
             item["url"], score, float(data.get("confidence") or 0), status, now_str()),
        )
        execute("UPDATE notices SET cluster_id=? WHERE id=?", (nid, nid))
        execute("UPDATE raw_items SET processed=1, note=? WHERE id=?",
                ("title_only" if title_only else None, item["id"]))
        recent.append({"id": nid, "cluster_id": nid, "title": item["title"],
                       "created_at": now_str()})
        created += 1

    return {"created": created, "dup": dup, "dropped": dropped, "scanned": len(rows)}


def digest(limit: int = 12, day: str | None = None) -> dict:
    day = day or now_str()[:10]
    rows = query(
        """SELECT id, title, one_line, who, deadline, place, tags, url, score
           FROM notices
           WHERE status='published' AND substr(created_at,1,10)=?
           ORDER BY score DESC, id DESC LIMIT ?""",
        (day, limit),
    )
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        items.append(d)
    total = query_one(
        "SELECT COUNT(*) AS c FROM notices WHERE substr(created_at,1,10)=?", (day,)
    )["c"]
    return {"date": day, "total": total, "items": items}


def search(q: str, limit: int = 5) -> dict:
    q = (q or "").strip()
    if not q:
        return {"q": q, "items": []}
    like = f"%{q}%"
    rows = query(
        """SELECT id, title, one_line, deadline, url, tags, created_at
           FROM notices
           WHERE title LIKE ? OR one_line LIKE ? OR tags LIKE ?
           ORDER BY created_at DESC LIMIT ?""",
        (like, like, like, limit),
    )
    return {"q": q, "items": [dict(r) for r in rows]}


def stats() -> dict:
    rows = query(
        """SELECT source,
                  SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS ok_cnt,
                  SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fail_cnt,
                  MAX(ts) AS last_ts
           FROM fetch_log GROUP BY source"""
    )
    return {"sources": [dict(r) for r in rows]}


def subscribe(qq: str, tag: str) -> dict:
    tag = (tag or "").strip() or "其他"
    if not qq:
        return {"ok": False, "msg": "缺少 QQ"}
    execute(
        "INSERT OR IGNORE INTO subscriptions(qq, tag, created_at) VALUES(?,?,?)",
        (qq, tag, now_str()),
    )
    return {"ok": True, "qq": qq, "tag": tag}


def record_delivery(day: str, chat_id: str, count: int, status: str = "ok",
                    error: str | None = None) -> None:
    execute(
        """INSERT INTO deliveries(day, chat_id, count, status, error, created_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(day, chat_id) DO UPDATE SET
             count=excluded.count, status=excluded.status, error=excluded.error""",
        (day, chat_id, count, status, error, now_str()),
    )
