"""通用 HTML 列表页采集器：一份配置驱动所有源。

策略：
1. 取列表页（按源配置的编码解码，厦大站点常见 gbk）；
2. 用 CSS 选择器取条目，抽 a 标签的 title/href；
3. 只对新链接抓详情页（限量 + 延迟），抽正文。
"""
from __future__ import annotations

import random
import re
import time
from urllib.parse import urljoin

import httpx

from ..parse import clean_text
from ..settings import settings

_BLOCK_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
# 列表页常把日期拼在标题后面（「关于…的通知 2026-11-16」），入库前切掉
_TRAIL_DATE = re.compile(r"\s*(20\d{2})\s*[-./年]\s*\d{1,2}\s*[-./月]\s*\d{1,2}\s*日?\s*$")


def _headers() -> dict:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.xmu.edu.cn/",
    }


def _decode(resp: httpx.Response, encoding: str) -> str:
    raw = resp.content
    if encoding and encoding.lower() != "auto":
        try:
            return raw.decode(encoding, errors="ignore")
        except LookupError:
            pass
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:2048], re.I)
    if m:
        try:
            return raw.decode(m.group(1).decode("ascii"), errors="ignore")
        except (LookupError, UnicodeDecodeError):
            pass
    return raw.decode("utf-8", errors="ignore")


def extract_links(html: str, selector: str | None, base_url: str,
                  limit: int = 30) -> list[dict]:
    """优先用 selectolax + CSS 选择器；没装或没配就退回正则全页链接。"""
    out: list[dict] = []
    seen: set[str] = set()

    def add(href: str, text: str, title: str | None = None) -> None:
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            return
        url = urljoin(base_url, href.strip())
        if not url.startswith("http") or url in seen:
            return
        label = clean_text(title or text).strip()
        label = _TRAIL_DATE.sub("", label).strip()
        if len(label) < 6:      # 「更多>>」「[详情]」这类不要
            return
        seen.add(url)
        out.append({"url": url, "title": label})

    if selector:
        try:
            from selectolax.parser import HTMLParser  # 可选依赖
            tree = HTMLParser(html)
            for node in tree.css(selector)[:limit]:
                a = node.css_first("a") or node
                if getattr(a, "tag", "") != "a":
                    continue
                add(a.attributes.get("href", ""), a.text(strip=True),
                    a.attributes.get("title"))
        except ImportError:
            selector = None

    if not selector:
        for m in _LINK_RE.finditer(html):
            if len(out) >= limit:
                break
            add(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)))
    return out[:limit]


def fetch_list(src: dict) -> list[dict]:
    url = src["list_url"]
    with httpx.Client(headers=_headers(), timeout=20, follow_redirects=True) as cli:
        resp = cli.get(url)
        resp.raise_for_status()
        html = _decode(resp, src.get("encoding", "utf-8"))
    return extract_links(html, src.get("item_selector"), url,
                         limit=int(src.get("limit", 30)))


def fetch_detail(url: str, selector: str | None = None, max_chars: int = 4000) -> str:
    """抓详情页正文。失败返回空串（不影响整批）。"""
    try:
        with httpx.Client(headers=_headers(), timeout=20, follow_redirects=True) as cli:
            resp = cli.get(url)
            resp.raise_for_status()
            html = _decode(resp, "utf-8")
    except Exception:                                   # noqa: BLE001
        return ""

    if selector:
        try:
            from selectolax.parser import HTMLParser
            node = HTMLParser(html).css_first(selector)
            if node:
                return node.text(separator="\n", strip=True)[:max_chars]
        except ImportError:
            pass

    try:
        import trafilatura                            # 可选依赖
        txt = trafilatura.extract(html, url=url, include_comments=False,
                                  include_tables=True, favor_recall=True)
        if txt:
            return txt[:max_chars]
    except Exception:                                   # noqa: BLE001
        pass
    return clean_text(html)[:max_chars]


def collect(src: dict, fresh_only: bool = True) -> list[dict]:
    """采一个源：列表 + （限量）详情正文。"""
    links = fetch_list(src)
    items = []
    for i, link in enumerate(links):
        content = ""
        if src.get("fetch_detail", True) and i < int(src.get("detail_limit", 8)):
            content = fetch_detail(link["url"], src.get("content_selector"))
            time.sleep(random.uniform(settings.crawl_delay_min, settings.crawl_delay_max))
        items.append({
            "source": src["id"],
            "url": link["url"],
            "title": link["title"],
            "content": content,
        })
    return items
