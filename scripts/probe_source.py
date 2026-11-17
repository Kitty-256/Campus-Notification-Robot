"""探源工具：检查一个站点是否可抓、栏目路径在哪、编码是什么。

    python scripts/probe_source.py https://informatics.xmu.edu.cn/
    python scripts/probe_source.py https://informatics.xmu.edu.cn/ --try tzgg.htm,tzgg/,xwdt.htm

它会：
1. 请求给定地址，报告状态码、最终跳转地址、编码、体积；
2. 从页面里挑出「通知/公告/新闻/公示」相关链接，给出绝对地址；
3. 依次尝试候选栏目路径，告诉你哪个 200 且像列表页。

只做只读探测，不写入、不频繁请求（每次调用间隔 1 秒）。
"""
from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
KEYWORDS = ("通知", "公告", "公示", "新闻", "动态", "tzgg", "xwdt", "ggtz", "news")


def fetch(url: str, timeout: int = 15) -> tuple[int, str, bytes, str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, url, b"", ""
    except Exception as e:                              # noqa: BLE001
        print(f"    ! 请求失败：{type(e).__name__}: {e}")
        return 0, url, b"", ""


def decode(body: bytes, ctype: str) -> tuple[str, str]:
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    else:
        m2 = re.search(rb'charset=["\']?([\w-]+)', body[:2048], re.I)
        enc = m2.group(1).decode("ascii", "ignore") if m2 else ""
    for cand in ([enc] if enc else []) + ["utf-8", "gbk"]:
        try:
            return body.decode(cand), cand
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "ignore"), "utf-8?"


def links(html: str, base: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for href, text in LINK_RE.findall(html):
        label = TAG_RE.sub("", text).strip()
        label = re.sub(r"\s+", " ", label)
        if not label or len(label) > 40:
            continue
        low = (href + label).lower()
        if not any(k in low for k in KEYWORDS):
            continue
        url = urllib.parse.urljoin(base, href.strip())
        if url in seen:
            continue
        seen.add(url)
        out.append((label, url))
    return out[:25]


def probe(url: str) -> None:
    print(f"\n[探测] {url}")
    code, final, body, ctype = fetch(url)
    if not body:
        print(f"    状态码：{code or '无响应'}（失败）")
        return
    html, enc = decode(body, ctype)
    print(f"    状态码：{code}｜最终地址：{final}")
    print(f"    编码：{enc}｜体积：{len(body)/1024:.0f} KB｜类型：{ctype or '未知'}")
    n_a = len(LINK_RE.findall(html))
    print(f"    页面链接数：{n_a}")
    cands = links(html, final)
    if cands:
        print("    疑似栏目入口：")
        for label, u in cands:
            print(f"      · {label[:26]:<26} {u}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    target = args[0]
    probe(target)

    extra = []
    for a in sys.argv[1:]:
        if a.startswith("--try="):
            extra = [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
    if extra:
        print("\n[候选栏目路径]")
        base = target.rstrip("/")
        for path in extra:
            time.sleep(1)
            u = f"{base}/{path.lstrip('/')}"
            code, final, body, ctype = fetch(u)
            size = len(body) / 1024 if body else 0
            flag = "OK" if code == 200 and size > 2 else f"-- {code}"
            print(f"    {flag:<6} {u}  →  {final if final != u else ''} {size:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
