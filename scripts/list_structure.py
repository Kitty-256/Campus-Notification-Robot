"""看列表页结构：判断用哪个 CSS 选择器、能不能直接抓。

    python scripts/list_structure.py https://informatics.xmu.edu.cn/news_events/tzgg.htm

输出：
1. 页面里「像通知标题」的链家及其 3 层祖先（tag#id.class），用来推选择器；
2. 出现频率最高的容器组合 —— 那通常就是列表项；
3. 结论提示（能用通用采集器 / 需要额外处理）。
"""
from __future__ import annotations

import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"20\d{2}[-./年]\d{1,2}[-./月]\d{1,2}")
SKIP_TAGS = {"script", "style", "head", "meta", "link", "br", "img"}


class Walker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.anchors: list[dict] = []
        self._cur: dict | None = None

    @staticmethod
    def _sig(tag: str, attrs: dict) -> str:
        tid = attrs.get("id")
        cls = (attrs.get("class") or "").split()
        s = tag
        if tid:
            s += f"#{tid}"
        if cls:
            s += "." + ".".join(cls[:3])
        return s

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            return
        d = dict(attrs)
        self.stack.append((tag, d))
        if tag == "a":
            path = [self._sig(t, a) for t, a in self.stack[-4:-1]]
            self._cur = {
                "href": d.get("href", ""),
                "path": " > ".join(path),
                "parent": self._sig(*self.stack[-2]) if len(self.stack) >= 2 else "",
                "ancestors": [(t, a) for t, a in self.stack[:-1]],
                "text": "",
            }

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            return
        if tag == "a" and self._cur is not None:
            self.anchors.append(self._cur)
            self._cur = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["text"] += data


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    url = sys.argv[1]
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            final = r.geturl()
            ctype = r.headers.get("Content-Type", "")
    except Exception as e:                                # noqa: BLE001
        print(f"请求失败：{e}")
        return 1

    enc = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or \
        re.search(rb'charset=["\']?([\w-]+)', body[:2048], re.I)
    if m:
        enc = (m.group(1).decode("ascii", "ignore") if isinstance(m.group(1), bytes)
               else m.group(1))
    for cand in dict.fromkeys([enc, "utf-8", "gbk"]):
        try:
            html = body.decode(cand)
            enc = cand
            break
        except (LookupError, UnicodeDecodeError):
            continue
    else:
        html, enc = body.decode("utf-8", "ignore"), "utf-8"

    print(f"[页面] {url}\n  最终地址：{final}\n  编码：{enc}｜{len(body)/1024:.0f} KB")

    w = Walker()
    w.feed(html)

    # 1) 像标题的链接（长度 + 可能带日期），先把文本规范化
    for a in w.anchors:
        a["text"] = re.sub(r"\s+", " ", a["text"]).strip().lstrip(">").strip()
    cand = [a for a in w.anchors
            if 6 <= len(a["text"]) <= 80 and a["href"]
            and not a["href"].startswith(("javascript:", "#"))]
    print(f"\n[候选条目] 链接总数 {len(w.anchors)}，像标题的 {len(cand)}")

    # 0) 指定选择器时，直接用「tag + class」匹配祖先，打印真实命中
    sel = None
    for arg in sys.argv[1:]:
        if arg.startswith("--sel="):
            sel = arg.split("=", 1)[1].strip()
    if sel:
        tag, classes = sel.split(".")[0], sel.split(".")[1:]
        print(f"\n[按选择器 {sel} 提取]")
        n, shown_urls = 0, set()
        for a in w.anchors:
            hit = any(
                t == tag and all(c in (at.get("class") or "").split() for c in classes)
                for t, at in a["ancestors"]
            )
            if not hit or len(a["text"]) < 6:
                continue
            u = urllib.parse.urljoin(final, a["href"])
            if u in shown_urls:
                continue
            shown_urls.add(u)
            n += 1
            if n <= 8:
                print(f"  {n:>2}. {a['text'][:56]}")
                print(f"      {u[:100]}")
        print(f"  命中 {n} 条")
        return 0

    # 2) 出现最多的父容器
    counter = Counter(a["parent"] for a in cand)
    print("\n[最可能的列表项容器]")
    for sig, n in counter.most_common(6):
        print(f"  {n:>3} 次   {sig}")

    # 3) 每个候选容器的样例
    print("\n[样例]")
    shown = 0
    for sig, _ in counter.most_common(3):
        for a in cand:
            if a["parent"] == sig:
                print(f"  {sig}")
                print(f"    text={a['text'].strip()[:50]}")
                print(f"    href={urllib.parse.urljoin(final, a['href'])[:110]}")
                print(f"    path={a['path']}")
                shown += 1
                break
        if shown >= 3:
            break

    # 4) 结论
    has_date = any(DATE_RE.search(a["text"]) for a in cand)
    print("\n[结论]")
    if counter:
        top_sig, top_n = counter.most_common(1)[0]
        if top_n >= 10:
            sel = top_sig.split(".")[0] if "#" not in top_sig else top_sig
            print(f"  可用通用采集器。item_selector 建议：{top_sig}（命中 {top_n} 条）")
            print(f"  日期在标题文本里：{'是' if has_date else '否（可能要另取，或留空由正文兜）'}")
        else:
            print("  结构不像标准列表（重复项太少），可能需 Playwright 或改选择器")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
