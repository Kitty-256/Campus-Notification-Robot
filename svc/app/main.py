"""notice-svc：采集 + 解析 + 去重 + 摘要 + 日报。

设计约束：所有能力都是 HTTP 接口，AstrBot 插件只做「调接口 + 排版 + 发送」。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db, pipeline
from .jobs.crawl import crawl_all
from .settings import BASE_DIR, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("notice-svc")

app = FastAPI(title="notice-svc", version="1.0.0")


# ---------------------------------------------------------------- 数据模型
class IngestItem(BaseModel):
    source: str = "manual"
    url: str
    title: str
    content: str | None = None
    published_at: str | None = None


class SubscribeBody(BaseModel):
    qq: str = Field(..., min_length=3)
    tag: str = "其他"


# ---------------------------------------------------------------- 后台任务
async def _scheduler() -> None:
    """每 CRAWL_INTERVAL_MIN 分钟抓一轮；启动时先跑一次。"""
    interval = max(5, settings.crawl_interval_min) * 60
    while True:
        try:
            res = await asyncio.to_thread(crawl_all)
            log.info("crawl done: ingested=%s created=%s",
                     res.get("ingested"), res.get("created"))
        except Exception as e:                            # noqa: BLE001
            log.exception("crawl failed: %s", e)
        await asyncio.sleep(interval)


def _ensure_sources_file() -> None:
    """首次启动时把示例源配置复制成正式配置，免得一上来就报找不到文件。"""
    from pathlib import Path
    target = Path(settings.sources_file)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    example = BASE_DIR / "config" / "sources.example.yaml"
    if example.exists():
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("已从示例生成源配置：%s", target)


@app.on_event("startup")
async def _startup() -> None:
    db.init_db()
    _ensure_sources_file()
    log.info("db ready at %s", settings.db_path)
    asyncio.create_task(_scheduler())


# ---------------------------------------------------------------- 基础
@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "ts": db.now_str(), "sources": len(_sources_safe())}


def _sources_safe() -> list:
    try:
        rows = db.query("SELECT id FROM sources WHERE enabled=1")
        return [dict(r) for r in rows]
    except Exception:                                     # noqa: BLE001
        return []


def _check_admin(token: str | None) -> None:
    if (token or "") != settings.admin_token:
        raise HTTPException(status_code=403, detail="bad admin token")


# ---------------------------------------------------------------- 采集入口
@app.post("/ingest")
def ingest_endpoint(items: list[IngestItem] | IngestItem) -> dict:
    """所有渠道的统一入口：RSSHub / Playwright / changedetection / 人工补录。"""
    lst = items if isinstance(items, list) else [items]
    try:
        return pipeline.ingest([i.model_dump() for i in lst])
    except Exception as e:                                # noqa: BLE001
        log.exception("ingest failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@app.post("/api/admin/crawl")
def admin_crawl(x_admin_token: str | None = Header(default=None)) -> dict:
    _check_admin(x_admin_token)
    return crawl_all()


@app.post("/api/admin/process")
def admin_process(limit: int = 50,
                  x_admin_token: str | None = Header(default=None)) -> dict:
    _check_admin(x_admin_token)
    return pipeline.process_pending(limit=limit)


# ---------------------------------------------------------------- 查询
@app.get("/api/digest")
def api_digest(limit: int = Query(default=12, ge=1, le=50),
               day: str | None = None) -> dict:
    return pipeline.digest(limit=limit, day=day)


@app.get("/api/search")
def api_search(q: str = "", limit: int = Query(default=5, ge=1, le=20)) -> dict:
    return pipeline.search(q, limit=limit)


@app.post("/api/subscribe")
def api_subscribe(body: SubscribeBody) -> dict:
    return pipeline.subscribe(body.qq, body.tag)


@app.get("/api/stats")
def api_stats() -> dict:
    return pipeline.stats()


@app.post("/api/delivery")
def api_delivery(chat_id: str, count: int = 0, status: str = "ok",
                 error: str | None = None) -> dict:
    """插件推送成功后回报，用于统计「连续 N 天送达」。"""
    pipeline.record_delivery(db.today_str(), chat_id, count, status, error)
    return {"ok": True}
