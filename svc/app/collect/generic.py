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

from ..parse import clean_article, clean_text
from ..settings import settings

_BLOCK_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
# 列表页常把日期拼在标题后面（「关于…的通知 2026-11-16」）：切掉，同时留作发布时间
_TRAIL_DATE = re.compile(
    r"\s*(20\d{2})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})\s*日?\s*$")
# 标题前面有时带箭头/序号（厦大部分列表是「> 关于…」），切掉
_LEAD_NOISE = re.compile(r"^[\s>›»·•\-—–\|]+")
# 只收「文章型」链接：导航、栏目首页一律不要。可在源配置里用 url_hint 覆盖
DEFAULT_URL_HINT = re.compile(r"(/info/|content\.jsp|wbnewsid|/article/|/detail)", re.I)
# 这些词开头的多半是导航/栏目入口
NAV_WORDS = ("返回", "更多", "首页", "上一页", "下一页", "English", "EN", "登录",
             "学院概况", "联系我们", "友情链接", "版权所有", "学生组织简介")


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
                  limit: int = 30, url_hint: str | None = None,
                  same_host: bool = True) -> list[dict]:
    """优先用 selectolax + CSS 选择器；没装或没配就退回正则全页链接。

    两道过滤缺一不可：
    - URL 过滤：只留文章型链接（/info/、content.jsp…），挡掉导航与栏目首页
    - 标题过滤：去掉「> 」前缀、切掉日期、排除导航词与冒号结尾的分区标题
    """
    out: list[dict] = []
    seen: set[str] = set()
    hint = re.compile(url_hint, re.I) if url_hint else DEFAULT_URL_HINT
    from urllib.parse import urlsplit
    base_host = urlsplit(base_url).netloc.lower()

    def add(href: str, text: str, title: str | None = None) -> None:
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            return
        url = urljoin(base_url, href.strip())
        if not url.startswith("http") or url in seen:
            return
        if same_host and urlsplit(url).netloc.lower() != base_host:
            return                      # 跳去别的站（如校园新闻）多半不是本栏目通知
        if not hint.search(url):
            return                      # 导航 / 栏目首页 / 锚点
        label = clean_text(title or text).strip()
        label = _LEAD_NOISE.sub("", label)
        # 列表页常把发布日期拼在标题后面，切掉的同时把它留下来当发布时间
        pub = None
        m = _TRAIL_DATE.search(label)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            pub = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            label = label[: m.start()].strip()
        label = label.rstrip("：:，,、 ")
        if len(label) < 8:
            return
        if any(label.startswith(w) for w in NAV_WORDS):
            return
        seen.add(url)
        out.append({"url": url, "title": label, "published_at": pub})

    if selector:
        try:
            from selectolax.parser import HTMLParser  # 可选依赖
            tree = HTMLParser(html)
            for node in tree.css(selector)[: max(limit * 2, 40)]:
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
                         limit=int(src.get("limit", 30)),
                         url_hint=src.get("url_hint"),
                         same_host=bool(src.get("same_host_only", True)))


def fetch_detail(url: str, selector: str | None = None, max_chars: int = 4000) -> str:
    """抓详情页正文。失败返回空串（不影响整批）。"""
    try:
        with httpx.Client(headers=_headers(), timeout=20, follow_redirects=True) as cli:
            resp = cli.get(url)
            resp.raise_for_status()
            html = _decode(resp, "utf-8")
    except Exception:                                   # noqa: BLE001
        return ""

    def _finish(txt: str) -> str:
        return clean_article(txt)[:max_chars]

    if selector:
        try:
            from selectolax.parser import HTMLParser
            node = HTMLParser(html).css_first(selector)
            if node:
                got = _finish(node.text(separator="\n", strip=True))
                if len(got) >= 50:          # 选择器抓到的是整页模板时，交给通用抽取再试
                    return got
        except ImportError:
            pass

    try:
        import trafilatura                            # 可选依赖
        txt = trafilatura.extract(html, url=url, include_comments=False,
                                  include_tables=True, favor_recall=True)
        if txt:
            return _finish(txt)
    except Exception:                                   # noqa: BLE001
        pass
    return _finish(clean_text(html))


def collect(src: dict, fresh_only: bool = True) -> list[dict]:
    """采一个源：列表 + （限量）详情正文。

    fresh_only=True 时跳过库里已有的链接——稳态下每小时只有 1~3 条新通知，
    这样既能把 detail_limit 开大（首轮补齐正文），又不会每小时都去打扰学校服务器。
    """
    from ..db import url_exists          # 延迟导入，避免循环依赖

    links = fetch_list(src)
    limit = int(src.get("detail_limit", 8))
    items = []
    for link in links:
        if fresh_only and url_exists(link["url"]):
            continue
        content = ""
        if src.get("fetch_detail", True):
            content = fetch_detail(link["url"], src.get("content_selector"))
            time.sleep(random.uniform(settings.crawl_delay_min, settings.crawl_delay_max))
        items.append({
            "source": src["id"],
            "url": link["url"],
            "title": link["title"],
            "content": content,
            "published_at": link.get("published_at"),
        })
        if len(items) >= limit:
            break
    return items
