"""LLM 摘要与字段抽取：Schema 约束 + 校验重试 + 降级。

设计原则：
1. 没配 API Key 也能跑（走 fallback_summary），保证日报永远发得出去；
2. 抽出来的 deadline 必须能在原文命中，否则置 null（防幻觉）；
3. 同一正文只花一次钱（llm_cache）。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .db import execute, now_str, query_one
from .parse import clean_text, find_deadline, one_line_from, guess_tags, verify_in_source
from .settings import settings

TAGS = ["竞赛", "奖学金", "讲座", "宣讲会", "选课", "考试", "停课调课", "实习就业", "其他"]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["one_line", "who", "deadline", "place", "actions", "tags", "confidence"],
    "properties": {
        "one_line": {"type": "string", "maxLength": 80},
        "who": {"type": ["string", "null"]},
        "deadline": {"type": ["string", "null"]},
        "place": {"type": ["string", "null"]},
        "actions": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "tags": {"type": "array", "minItems": 1, "items": {"enum": TAGS}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

SYSTEM_PROMPT = """你是厦门大学的学生事务助理。把一条校园通知压缩成「学生能立刻行动」的结构化摘要。

规则（违反任何一条都算失败）：
1. 只使用原文中明确出现的信息，禁止推断、禁止补充常识、禁止编造时间地点；
2. deadline/place/who 必须逐字来自原文，找不到就填 null；
3. 截止时间统一为 "YYYY-MM-DD HH:MM"（北京时间），只有日期则 "YYYY-MM-DD"；
4. one_line 不超过 60 字，说清「是什么 + 谁该做 + 什么时候之前」；
5. actions 最多 3 条，动词开头；
6. tags 只能从枚举中选：竞赛/奖学金/讲座/宣讲会/选课/考试/停课调课/实习就业/其他；
7. 输出必须是单个 JSON 对象，不要解释、不要 markdown 代码块。"""


def _user_prompt(title: str, content: str, url: str, source: str) -> str:
    body = clean_text(content)[:1500]
    return (
        f"【来源】{source}\n【标题】{title}\n【链接】{url}\n"
        f"【正文（最多1500字）】\n{body}\n\n"
        "请输出 JSON，字段：one_line, who, deadline, place, actions, tags, confidence。"
    )


def _cache_key(title: str, content: str) -> str:
    return hashlib.sha1((title + (content or "")[:800]).encode("utf-8")).hexdigest()


def _cached(key: str) -> dict | None:
    row = query_one("SELECT payload FROM llm_cache WHERE k=?", (key,))
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except Exception:
        return None


def _save_cache(key: str, data: dict) -> None:
    execute(
        "INSERT OR REPLACE INTO llm_cache(k, payload, ts) VALUES(?,?,?)",
        (key, json.dumps(data, ensure_ascii=False), now_str()),
    )


def fallback_summary(title: str, content: str) -> dict:
    return {
        "one_line": one_line_from(title, content),
        "who": None,
        "deadline": find_deadline(clean_text(content)),
        "place": None,
        "actions": ["查看原文"],
        "tags": guess_tags(title, content),
        "confidence": 0.0,
        "_degraded": True,
    }


def _validate(data: dict) -> tuple[bool, str]:
    try:
        import jsonschema  # 可选依赖，没装就做宽松校验
    except ImportError:
        if not isinstance(data.get("one_line"), str):
            return False, "one_line 缺失"
        return True, ""
    try:
        jsonschema.validate(data, SCHEMA)
        return True, ""
    except Exception as e:                              # noqa: BLE001
        return False, str(e).split("\n")[0][:200]


def _post_chat(prompt: str) -> str:
    import httpx                       # 延迟导入：没配 Key / 离线跑时不依赖它

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    with httpx.Client(timeout=settings.llm_timeout) as cli:
        r = cli.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def summarize(title: str, content: str, url: str = "", source: str = "") -> dict:
    """返回结构化摘要；任何环节失败都退化为本地规则，不抛异常。"""
    if not settings.llm_api_key:
        return fallback_summary(title, content)

    key = _cache_key(title, content)
    hit = _cached(key)
    if hit is not None:
        return hit

    prompt = _user_prompt(title, content, url, source)
    for _ in range(3):
        try:
            raw = _post_chat(prompt)
        except Exception:                               # noqa: BLE001
            return fallback_summary(title, content)

        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0) if m else raw)
        except Exception:                               # noqa: BLE001
            prompt = "上次输出不是合法 JSON，请只输出符合 schema 的 JSON 对象，不要任何解释。"
            continue

        ok, err = _validate(data)
        if not ok:
            prompt = f"上次输出不符合 schema（{err}），请只输出符合 schema 的 JSON 对象。"
            continue

        # 事实回验：抽出来的时间必须能在原文命中
        body = clean_text(content)
        if data.get("deadline") and not verify_in_source(str(data["deadline"]), body):
            data["deadline"] = None
            data["confidence"] = min(float(data.get("confidence") or 0), 0.4)

        data.setdefault("who", None)
        data.setdefault("place", None)
        data.setdefault("actions", [])
        data.setdefault("tags", guess_tags(title, content))
        data["_degraded"] = False
        _save_cache(key, data)
        return data

    return fallback_summary(title, content)
