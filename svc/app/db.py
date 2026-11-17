"""SQLite 访问层：连接、建表、便捷查询。

刻意不引 ORM —— SQLite + 原生 SQL 在这个体量下更透明，也更好在答辩时解释。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .settings import BASE_DIR, settings

_local = threading.local()


def now_str() -> str:
    """统一用「本地时间 + 固定偏移」的 ISO 字符串，避免 naive/aware 混用。"""
    return (datetime.utcnow() + timedelta(hours=settings.tz_offset_hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def today_str() -> str:
    return now_str()[:10]


def get_conn() -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        path = Path(settings.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = get_conn()
    conn.executescript(schema)
    conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(get_conn().execute(sql, tuple(params)).fetchall())


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    conn = get_conn()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.lastrowid if cur.lastrowid is not None else cur.rowcount


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("tags",):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                d[k] = []
    return d


def upsert_source(sid: str, list_url: str, item_selector: str | None,
                  encoding: str = "utf-8", kind: str = "html") -> None:
    execute(
        """INSERT INTO sources(id, list_url, item_selector, encoding, kind)
           VALUES(?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             list_url=excluded.list_url,
             item_selector=excluded.item_selector,
             encoding=excluded.encoding,
             kind=excluded.kind""",
        (sid, list_url, item_selector, encoding, kind),
    )


def log_fetch(source: str, ok: bool, n: int = 0, err: str | None = None) -> None:
    execute(
        "INSERT INTO fetch_log(source, ok, n, err, ts) VALUES(?,?,?,?,?)",
        (source, 1 if ok else 0, n, err, now_str()),
    )
