"""三级去重：URL 归一化 → 标题 SimHash → （可选）向量余弦。

前两级纯 Python 实现，无第三方依赖；第三级留给 V2。
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

TRACKING = re.compile(r"^(utm_\w+|t|from|spm|share|_t)$", re.I)
STOP = re.compile(r"(关于|通知|公告|开展|做好|组织|转发|的|等)")


def norm_url(url: str) -> str:
    """去掉追踪参数、统一协议与尾斜杠。"""
    if not url:
        return ""
    url = url.strip()
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    q = "&".join(
        kv for kv in p.query.split("&")
        if kv and not TRACKING.match(kv.split("=")[0])
    )
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower() or "http", p.netloc.lower(), path, q, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(norm_url(url).encode("utf-8")).hexdigest()


def _features(title: str) -> list[str]:
    t = STOP.sub("", title or "")
    # 去掉年份与数字：「2026年国家奖学金评审」和「国家奖学金评审」应当判为同一条
    t = re.sub(r"(20\d{2})\s*年?", "", t)
    t = re.sub(r"\d+", "", t)
    t = re.sub(r"[\s\W_]+", "", t)
    if not t:
        return []
    if len(t) == 1:
        return [t]
    return [t[i:i + 2] for i in range(len(t) - 1)]


def simhash(title: str, bits: int = 64) -> int:
    """64 位 SimHash，特征为中文 2-gram。"""
    feats = _features(title)
    if not feats:
        return 0
    v = [0] * bits
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin((a or 0) ^ (b or 0)).count("1")


def is_dup_title(a: str, b: str, threshold: int = 3) -> bool:
    """标题级判重。短标题（<8 字）不启用，避免「讲座通知」吞掉一堆不同讲座。"""
    ta, tb = (a or "").strip(), (b or "").strip()
    if len(ta) < 8 or len(tb) < 8:
        return norm_url(ta) == norm_url(tb) and bool(ta)
    return hamming(simhash(ta), simhash(tb)) <= threshold


def days_apart(ts1: str | None, ts2: str | None) -> int:
    """两个 'YYYY-MM-DD...' 字符串相差的天数；解析失败返回 999。"""
    import datetime as _dt
    def _d(s: str | None):
        if not s:
            return None
        try:
            return _dt.datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    d1, d2 = _d(ts1), _d(ts2)
    if not d1 or not d2:
        return 999
    return abs((d1 - d2).days)
