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

        # 不依赖具体 CSS 选择器：把页面上所有链接取回来，再用启发式筛标题
        anchors = page.eval_on_selector_all(
            "a",
            """els => els.map(e => ({
                   href: e.href || '',
                   text: (e.getAttribute('title') || e.innerText || '').trim()
               }))""",
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

    return items
