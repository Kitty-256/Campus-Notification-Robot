"""纯函数：正文清洗、中文日期解析、截止时间抽取与回验。

这一层没有任何第三方依赖，可以离线单测（scripts/selftest.py）。
"""
from __future__ import annotations

import html as html_mod
import re
from datetime import datetime

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_WS_RE = re.compile(r"[ \t\u3000]+")
_NL_RE = re.compile(r"\n{3,}")

# 2026年11月20日 / 2026-11-20 / 2026.11.20，可选带时间
DATE_RE = re.compile(
    r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?"
    r"(?:\s*(\d{1,2})\s*[:：时]\s*(\d{2})?)?"
)
# 11月20日（缺年份）
DATE_NO_YEAR_RE = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:\s*(\d{1,2})[:：](\d{2}))?")

DEADLINE_HINTS = ("截止", "之前", "前完成", "前提交", "前报名", "报名截止", "申请截止", "提交截止", "止于")
# 日期后面紧跟「前」也算截止（注意排除「前往」「前来」这种动词）
DEADLINE_TAIL_RE = re.compile(r"^\s*[（(]?\s*(?:前|之前|以前|截止)(?!往|来)")
REPORT_HINTS = ("发布", "印发", "公示", "公布", "会议", "成立", "获得")


def clean_text(raw: str | None) -> str:
    """HTML → 干净文本。去脚本、去标签、解实体、压空白。"""
    if not raw:
        return ""
    s = _SCRIPT_RE.sub(" ", raw)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|tr|h\d)>", "\n", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = html_mod.unescape(s)
    s = s.replace("\r", "")
    s = _WS_RE.sub(" ", s)
    s = _NL_RE.sub("\n\n", s)
    return "\n".join(line.strip() for line in s.split("\n")).strip()


def clean_article(text: str) -> str:
    """把详情页文本裁成「正文」：去掉导航、面包屑、页脚、上下篇。

    厦大各站的正文容器常常把整页模板也包进去（实测 #vsb_content 会带上
    「首页 概况 信息公开 …」），所以做一次通用裁剪，而不是依赖精确选择器。
    """
    if not text:
        return ""
    s = text.replace("\ufeff", "").replace("\u3000", " ")

    # 1) 面包屑之后才是正文
    m = re.search(r"当前位置[:：]", s)
    if m:
        s = s[m.end():]
    s = re.sub(r"^\s*(首页)?\s*[>>›]{1,3}\s*", "", s)

    # 2) 丢掉页脚与操作项
    s = re.split(r"(上一篇|下一篇|上一条|下一条|返回列表|返回顶部|版权所有|打印本页)", s)[0]

    lines = []
    for raw_line in s.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if len(line) <= 6:                       # 「首页」「概况」「学籍学务」这类导航
            continue
        if re.fullmatch(r"[\d\s\-—/.:：年月日时]+", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _mk(y: int, mo: int, d: int, hh: str | None, mm: str | None) -> str | None:
    try:
        if hh is not None:
            h = int(hh)
            m = int(mm) if mm else 0
            if h == 24:                 # 「24:00」是当天结束，按 23:59 记
                h, m = 23, 59
            elif h > 23:
                h, m = 23, 59
            dt = datetime(int(y), int(mo), int(d), h, m)
            return dt.strftime("%Y-%m-%d %H:%M")
        dt = datetime(int(y), int(mo), int(d))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def parse_date(text: str, default_year: int | None = None) -> str | None:
    """取正文里第一个像日期的串（用于"发布时间"）。"""
    if not text:
        return None
    m = DATE_RE.search(text)
    if m:
        return _mk(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
    m = DATE_NO_YEAR_RE.search(text)
    if m and default_year:
        return _mk(default_year, m.group(1), m.group(2), m.group(3), m.group(4))
    return None


PUBLISH_HINTS = ("发布时间", "发布日期", "发布于", "发文日期", "更新日期", "时间：")
PUBLISH_RE = re.compile(
    r"(?:发布时间|发布日期|发布于|发文日期|更新日期)\s*[:：]?\s*"
    r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")


def find_publish_date(text: str) -> str | None:
    """从详情页正文里找「发布时间：2026年10月16日」这类标记。"""
    if not text:
        return None
    m = PUBLISH_RE.search(text)
    if not m:
        return None
    return _mk(m.group(1), m.group(2), m.group(3), None, None)


def find_deadline(text: str, default_year: int | None = None) -> str | None:
    """找"截止类"日期：日期前面有「截止/之前」，或后面紧跟「前/之前/截止」。

    宁可返回 None，也不返回一个错的时间 —— 这是防幻觉的第一道闸。
    """
    if not text:
        return None
    for m in DATE_RE.finditer(text):
        before = text[max(0, m.start() - 24): m.start()]
        after = text[m.end(): m.end() + 10]
        if any(k in before for k in DEADLINE_HINTS) or DEADLINE_TAIL_RE.match(after):
            got = _mk(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            if got:
                return got
    if default_year:
        for m in DATE_NO_YEAR_RE.finditer(text):
            before = text[max(0, m.start() - 24): m.start()]
            after = text[m.end(): m.end() + 10]
            if any(k in before for k in DEADLINE_HINTS) or DEADLINE_TAIL_RE.match(after):
                got = _mk(default_year, m.group(1), m.group(2), m.group(3), m.group(4))
                if got:
                    return got
    return None


def verify_in_source(deadline: str | None, text: str) -> bool:
    """LLM 抽出来的时间必须能在原文里命中，否则视为幻觉。"""
    if not deadline or not text:
        return False
    try:
        y, mo, d = deadline[:10].split("-")
    except ValueError:
        return False
    pat = rf"{int(y)}\s*[年\-/.]\s*0?{int(mo)}\s*[月\-/.]\s*0?{int(d)}"
    return re.search(pat, text) is not None


def guess_tags(title: str, text: str = "") -> list[str]:
    """关键词兜底打标（LLM 可用时以 LLM 为准）。"""
    blob = f"{title} {text[:300]}"
    table = [
        ("竞赛", ("竞赛", "大赛", "比赛", "挑战赛", "数学建模", "创新创业")),
        ("奖学金", ("奖学金", "助学金", "评奖", "评优", "国奖", "励志")),
        ("讲座", ("讲座", "报告会", "学术报告", "论坛", "沙龙")),
        ("宣讲会", ("宣讲", "招聘", "双选", "企业", "实习")),
        ("选课", ("选课", "退课", "课程", "教学安排")),
        ("考试", ("考试", "考核", "补考", "缓考", "四六级")),
        ("停课调课", ("调课", "停课", "补课", "教室调整")),
        ("实习就业", ("就业", "实习", "派遣", "三方", "档案")),
    ]
    for tag, keys in table:
        if any(k in blob for k in keys):
            return [tag]
    return ["其他"]


def one_line_from(title: str, text: str = "", limit: int = 60) -> str:
    """降级摘要：标题优先，标题太短则补正文第一句。"""
    t = re.sub(r"\s+", " ", title).strip()
    # 去掉标题套话：关于 / 做好 / 举办 / 印发 …（长词优先，否则「关于做好」只吃到「关于」）
    t = re.sub(r"^(?:关于|转发)?(?:开展|做好|举办|组织|印发|发布|公示)?", "", t).strip()
    t = re.sub(r"的?(?:通知|公告|公示|函|决定)$", "", t).strip()
    if len(t) < 8 and text:
        first = re.split(r"[。！？\n]", clean_text(text))[0]
        if first and first not in t:
            t = f"{t}：{first}" if t else first
    return (t[:limit] + "…") if len(t) > limit else t
