"""浏览器渲染采集器（T2）：给 JS 渲染的站点用，比如信息学院。

为什么需要它：信息学院的通知列表由 Vue + axios 在浏览器里渲染，
直接抓 HTML 只能拿到导航栏（实测 137 个 <a> 里 0 条文章）。
所以这里起一个无头 Chromium，等页面渲染完再取链接。

依赖：playwright（可选）。
    pip install playwright
    playwright install chromium --with-deps
没装也不会崩——这个源会被跳过并打一条警告，其它源照常抓。
"""
from __future__ import annotations

import re

from ..settings import settings

# 标题过滤：太短的多是「更多>>」「首页」，太长的多半是整段正文
NAV_WORDS = ("更多", "首页", "登录", "English", "EN", "搜索", "返回", "上一篇", "下一篇",
             "学院概况", "联系我们", "友情链接", "版权所有")
ARTICLE_HINT = re.compile(r"(/info/|content\.jsp|wbnewsid|/article/|/news/\d|\.htm)", re.I)


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def collect(src: dict) -> list[dict]:
    if not available():
        raise RuntimeError("未安装 playwright，跳过该源（pip install playwright 后重试）")

    from playwright.sync_api import sync_playwright

    url = src["list_url"]
    limit = int(src.get("limit", 20))
    items: list[dict] = []
    seen: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(locale="zh-CN", user_agent=settings.user_agent,
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception:                                # noqa: BLE001
            # 有些站永远不 idle（轮询/长连接），退一步只等 DOM
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

        # 不依赖具体 CSS 选择器：取所有链接，标题优先取卡片里的标题元素。
        # 信息学院这类站点的 <a> 包住整张卡片（日期 + 标题 + 摘要），
        # 直接读 innerText 会超过 80 字被过滤，所以先找 h1~h6 / .title。
        anchors = page.eval_on_selector_all(
            "a[href]",
            """els => els.map(e => {
                   const h = e.querySelector('h1,h2,h3,h4,h5,h6,.title');
                   const raw = h ? h.innerText
                                 : (e.getAttribute('title') || e.innerText || '');
                   return { href: e.href || '', text: (raw || '').trim() };
               })""",
        )
        browser.close()

    for a in anchors:
        href = (a.get("href") or "").strip()
        text = re.sub(r"\s+", " ", a.get("text") or "").strip()
        if not href or href in seen:
            continue
        if not ARTICLE_HINT.search(href):
            continue
        if not (8 <= len(text) <= 80):
            continue
        if any(w in text for w in NAV_WORDS):
            continue
        seen.add(href)
        items.append({"source": src["id"], "url": href, "title": text})
        if len(items) >= limit:
            break

    # 详情页大多是服务端渲染的（WebPlus），用普通 httpx 抓正文即可，
    # 这样浏览器只负责「拿到列表」，正文与截止时间走轻量路径。
    if src.get("fetch_detail", True) and items:
        import time

        from .generic import fetch_detail
        n = int(src.get("detail_limit", 8))
        for it in items[:n]:
            try:
                it["content"] = fetch_detail(it["url"], src.get("content_selector"))
            except Exception:                          # noqa: BLE001
                it["content"] = ""
            time.sleep(settings.crawl_delay_min)

    return items
