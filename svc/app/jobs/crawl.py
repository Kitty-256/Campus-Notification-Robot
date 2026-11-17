"""采集调度：跑一轮所有源 → 入库 → 处理。

刻意串行 + 随机延迟：对学校服务器要克制，这既是合规要求，也能少触发反爬。
"""
from __future__ import annotations

import random
import time

from .. import db
from ..collect import generic, rss
from ..pipeline import ingest, process_pending
from ..settings import settings


def load_sources() -> list[dict]:
    """源配置优先从 YAML 读；读不到就退回数据库里已登记的源。"""
    path = settings.sources_file
    try:
        import yaml
        from pathlib import Path
        if Path(path).exists():
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
            out = []
            for s in data:
                if not s.get("enabled", True):
                    continue
                out.append(s)
                db.upsert_source(s["id"], s["list_url"], s.get("item_selector"),
                                 s.get("encoding", "utf-8"), s.get("kind", "html"))
            if out:
                return out
    except Exception:                                    # noqa: BLE001
        pass

    rows = db.query("SELECT * FROM sources WHERE enabled=1")
    return [dict(r) for r in rows]


def crawl_all() -> dict:
    result = {"sources": [], "ingested": 0, "created": 0}
    for src in load_sources():
        sid = src["id"]
        try:
            items = rss.collect(src) if src.get("kind") == "rss" else generic.collect(src)
            got = ingest(items)
            db.log_fetch(sid, True, len(items))
            result["sources"].append({"id": sid, "n": len(items), "ok": True,
                                      "accepted": got["accepted"]})
            result["ingested"] += got["accepted"]
        except Exception as e:                           # noqa: BLE001
            db.log_fetch(sid, False, 0, str(e)[:200])
            result["sources"].append({"id": sid, "ok": False, "err": str(e)[:120]})
        time.sleep(random.uniform(settings.crawl_delay_min, settings.crawl_delay_max))

    proc = process_pending()
    result["created"] = proc["created"]
    result["processed"] = proc
    return result
