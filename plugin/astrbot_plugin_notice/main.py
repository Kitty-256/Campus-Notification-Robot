"""AstrBot 插件：校园通知日报（薄壳）。

硬约束：本文件不出现任何抓网页、提示词、数据库访问的代码。
它只做三件事：拼 URL 调 notice-svc、把 JSON 排版成消息、调 send_message。
"""
from __future__ import annotations

import asyncio
import datetime

import aiohttp

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

ZWSP = "\u200b"          # aiocqhttp 发送 plain 时会 strip 首尾空白，用它护住排版
DEFAULT_SVC = "http://notice-svc:8000"


@register("astrbot_plugin_notice", "xmu-ai-team", "校园通知日报", "1.0.0")
class NoticePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------ 生命周期
    async def initialize(self) -> None:
        self._task = asyncio.create_task(self._daily_loop())
        logger.info("[notice] 插件已启动，推送时间=%s", self._push_time())

    async def terminate(self) -> None:
        if self._task:
            self._task.cancel()

    # ------------------------------------------------------------ 基础工具
    @property
    def svc(self) -> str:
        v = (self.config.get("svc_base") or "").strip() or DEFAULT_SVC
        return v.rstrip("/")

    def _push_time(self) -> str:
        t = (self.config.get("push_time") or "07:30").strip()
        parts = t.split(":")
        if len(parts) != 2:
            return "07:30"
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    async def _get(self, path: str, **params) -> dict:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(self.svc + path, params=params) as r:
                r.raise_for_status()
                return await r.json()

    async def _post(self, path: str, **params) -> dict:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(self.svc + path, params=params) as r:
                r.raise_for_status()
                return await r.json()

    async def _kv_get(self, key: str, default: str = "") -> str:
        try:
            return await self.get_kv_data(key, default) or default
        except Exception:                                  # noqa: BLE001
            return default

    async def _kv_put(self, key: str, value: str) -> None:
        try:
            await self.put_kv_data(key, value)
        except Exception as e:                             # noqa: BLE001
            logger.warning("[notice] KV 写入失败: %s", e)

    # ------------------------------------------------------------ 排版
    def _fmt(self, data: dict) -> str:
        items = data.get("items") or []
        if not items:
            return "今天暂时没有新通知。"
        lines = [f"📌 今日通知（{len(items)} 条 / 共 {data.get('total', '?')} 条）", ""]
        for i, it in enumerate(items, 1):
            head = it.get("one_line") or it.get("title") or ""
            dl = it.get("deadline")
            tail = f"｜截止 {str(dl)[:16]}" if dl else ""
            lines.append(f"{i}. {head}{tail}")
            if it.get("url"):
                lines.append(f"   {it['url']}")
        lines += ["", "回复 /搜索 关键词 查历史；摘要由模型生成，以原文为准。"]
        return ZWSP + "\n".join(lines) + ZWSP

    def _fmt_search(self, kw: str, data: dict) -> str:
        items = data.get("items") or []
        if not items:
            return f"没找到与「{kw}」相关的通知。"
        lines = [f"🔍 「{kw}」找到 {len(items)} 条：", ""]
        for it in items:
            lines.append(f"· {it.get('title') or it.get('one_line')}")
            if it.get("url"):
                lines.append(f"  {it['url']}")
        return ZWSP + "\n".join(lines) + ZWSP

    # ------------------------------------------------------------ 指令
    @filter.command("今日")
    async def cmd_today(self, event: AstrMessageEvent):
        try:
            data = await self._get("/api/digest", limit=12)
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] /api/digest 失败: %s", e)
            yield event.plain_result("日报服务暂时不可用，稍后再试。")
            return
        yield event.plain_result(self._fmt(data))

    @filter.command("搜索")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str = ""):
        kw = (keyword or "").strip()
        if not kw:
            yield event.plain_result("用法：/搜索 保研")
            return
        try:
            data = await self._get("/api/search", q=kw, limit=5)
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] /api/search 失败: %s", e)
            yield event.plain_result("检索服务暂时不可用，稍后再试。")
            return
        yield event.plain_result(self._fmt_search(kw, data))

    @filter.command("订阅")
    async def cmd_subscribe(self, event: AstrMessageEvent, tag: str = ""):
        t = (tag or "").strip()
        if not t:
            yield event.plain_result("用法：/订阅 竞赛（可选：竞赛/奖学金/讲座/宣讲会/选课/考试）")
            return
        try:
            await self._post("/api/subscribe", qq=str(event.get_sender_id()), tag=t)
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] /api/subscribe 失败: %s", e)
            yield event.plain_result("订阅失败，稍后再试。")
            return
        yield event.plain_result(f"已订阅「{t}」，之后只推这类通知。")

    @filter.command("帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "可用指令：\n"
            "/今日 —— 今天的通知\n"
            "/搜索 关键词 —— 查历史通知\n"
            "/订阅 竞赛 —— 订阅某类通知\n"
            "/绑定推送 —— 把本群设为日报推送目标（管理员）\n"
            "摘要由模型生成，请以原文为准。"
        )

    @filter.command("绑定推送")
    async def cmd_bind(self, event: AstrMessageEvent):
        umo = getattr(event, "unified_msg_origin", None)
        if not umo:
            yield event.plain_result("拿不到本会话标识，请在群内使用。")
            return
        await self._kv_put("push_umo", umo)
        logger.info("[notice] push_umo 已绑定为 %s", umo)
        yield event.plain_result(f"已把本群设为日报推送目标：\n{umo}")

    # ------------------------------------------------------------ 定时推送
    async def _daily_loop(self) -> None:
        await asyncio.sleep(15)                 # 等 AstrBot 适配器完全就绪
        try:
            await self._catch_up()
        except Exception as e:                  # noqa: BLE001
            logger.warning("[notice] 补推失败: %s", e)

        while True:
            try:
                target = self._next_run()
                await asyncio.sleep(max(30, (target - datetime.datetime.now()).total_seconds()))
                await self._push_daily()
            except asyncio.CancelledError:
                raise
            except Exception as e:              # noqa: BLE001
                logger.error("[notice] 定时推送异常: %s", e)
                await asyncio.sleep(300)        # 出错后等 5 分钟再来，避免刷屏

    def _next_run(self) -> datetime.datetime:
        hh, mm = (int(x) for x in self._push_time().split(":"))
        now = datetime.datetime.now()
        tgt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if tgt <= now:
            tgt += datetime.timedelta(days=1)
        return tgt

    async def _catch_up(self) -> None:
        """今天该推的还没推（比如机器刚开机），立刻补一次。"""
        day = datetime.date.today().isoformat()
        if await self._kv_get(f"delivered_{day}"):
            return
        now = datetime.datetime.now()
        hh, mm = (int(x) for x in self._push_time().split(":"))
        if (now.hour, now.minute) < (hh, mm):
            return                              # 还没到点，等定时任务
        await self._push_daily()

    async def _push_daily(self) -> None:
        umo = (self.config.get("push_umo") or "").strip() or await self._kv_get("push_umo")
        if not umo:
            logger.warning("[notice] 未绑定推送目标，跳过（在群里发 /绑定推送）")
            return

        data = await self._get("/api/digest", limit=12)
        if not data.get("items"):
            logger.info("[notice] 今天没有通知，不推送")
            return

        await self.context.send_message(umo, self._fmt(data))
        day = datetime.date.today().isoformat()
        await self._kv_put(f"delivered_{day}", "1")
        try:
            await self._post("/api/delivery", chat_id=str(umo),
                             count=len(data["items"]), status="ok")
        except Exception:                                  # noqa: BLE001
            pass
        logger.info("[notice] 日报已推送：%s 条 → %s", len(data["items"]), umo)
