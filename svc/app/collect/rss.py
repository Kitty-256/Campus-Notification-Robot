"""RSS 源采集：站上本来就有 RSS，或走自建 RSSHub。"""
from __future__ import annotations

import httpx

from ..settings import settings


def collect(src: dict) -> list[dict]:
    url = src["list_url"]
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": settings.user_agent}) as cli:
        xml = cli.get(url).text

    try:
        import feedparser
    except ImportError:                                  # 没装就返回空，不炸整轮
        return []

    feed = feedparser.parse(xml)
    items = []
    for e in feed.entries[: int(src.get("limit", 30))]:
        items.append({
            "source": src["id"],
            "url": e.get("link", ""),
            "title": (e.get("title") or "").strip(),
            "content": e.get("summary", "") or e.get("description", ""),
            "published_at": (e.get("published") or "")[:10] or None,
        })
    return [i for i in items if i["url"] and i["title"]]
