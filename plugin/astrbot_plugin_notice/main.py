"""AstrBot 插件：校园通知日报（薄壳）。

硬约束：
1. 本文件不出现任何抓网页、提示词、数据库访问的代码；只调 notice-svc 的 HTTP 接口。
2. **默认拒绝**：没有授权群就一个字都不发。
   - 配置里给了 `allowed_groups` → 只有这些群能用指令、能收日报；
   - 配置为空 → 只有 `/绑定推送` 能用（第一次绑定），绑定后只有那个群被授权；
   - 任何情况下都不会往私聊、也不会往第二个群推送。
"""
from __future__ import annotations

import asyncio
import datetime

import aiohttp

import astrbot.api.message_components as Comp  # noqa: F401  （保留给后续合并转发用）
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

ZWSP = "\u200b"          # aiocqhttp 发送 plain 时会 strip 首尾空白，用它护住排版
DEFAULT_SVC = "http://127.0.0.1:8000"


@register("astrbot_plugin_notice", "xmu-ai-team", "校园通知日报", "1.2.0")
class NoticePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------ 生命周期
    async def initialize(self) -> None:
        self._tasks = []
        if self._realtime():
            self._tasks.append(asyncio.create_task(self._realtime_loop()))
        if self._daily_summary():
            self._tasks.append(asyncio.create_task(self._daily_loop()))
        allowed = await self._allowed_groups()
        logger.info("[notice] 插件已启动｜实时=%s（每 %s 分钟）｜日报=%s（%s）｜授权群=%s",
                    self._realtime(), self._watch_interval(), self._daily_summary(),
                    self._push_time(), allowed or "（未授权，等待 /绑定推送）")

    async def terminate(self) -> None:
        for t in getattr(self, "_tasks", []):
            t.cancel()

    # ------------------------------------------------------------ 开关
    def _realtime(self) -> bool:
        v = self.config.get("realtime")
        return True if v is None else str(v).strip().lower() in ("1", "true", "yes", "on", "是")

    def _daily_summary(self) -> bool:
        v = self.config.get("daily_summary")
        return False if v is None else str(v).strip().lower() in ("1", "true", "yes", "on", "是")

    def _watch_interval(self) -> int:
        try:
            return max(2, int(self.config.get("watch_interval_min") or 10))
        except (TypeError, ValueError):
            return 10

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
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            return "07:30"

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

    # ------------------------------------------------------------ 授权（默认拒绝）
    def _config_groups(self) -> set[str]:
        raw = str(self.config.get("allowed_groups") or "")
        return {x.strip() for x in raw.replace("，", ",").split(",") if x.strip()}

    async def _allowed_groups(self) -> set[str]:
        groups = self._config_groups()
        if groups:
            return groups
        bound = await self._kv_get("push_group")
        return {bound} if bound else set()

    async def _authorized(self, event: AstrMessageEvent, *, allow_bootstrap: bool = False) -> bool:
        """群号白名单校验。没有白名单时，只有 allow_bootstrap 的指令能过。"""
        gid = str(event.get_group_id() or "")
        if not gid:                                   # 私聊一律不处理
            return False
        allowed = await self._allowed_groups()
        if not allowed:
            return allow_bootstrap
        return gid in allowed

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
        if not await self._authorized(event):
            logger.warning("[notice] 未授权群发起 /今日，已忽略：%s", event.get_group_id())
            return
        try:
            data = await self._get("/api/digest", limit=12)
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] /api/digest 失败: %s", e)
            yield event.plain_result("日报服务暂时不可用，稍后再试。")
            return
        yield event.plain_result(self._fmt(data))

    @filter.command("搜索")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str = ""):
        if not await self._authorized(event):
            logger.warning("[notice] 未授权群发起 /搜索，已忽略：%s", event.get_group_id())
            return
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
        if not await self._authorized(event):
            return
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
        if not await self._authorized(event, allow_bootstrap=True):
            return
        yield event.plain_result(
            "可用指令：\n"
            "/今日 —— 今天的通知\n"
            "/搜索 关键词 —— 查历史通知\n"
            "/订阅 竞赛 —— 订阅某类通知\n"
            "/绑定推送 —— 把本群设为日报推送目标（每个机器人只允许一个群）\n"
            "摘要由模型生成，请以原文为准。"
        )

    @filter.command("绑定推送")
    async def cmd_bind(self, event: AstrMessageEvent):
        gid = str(event.get_group_id() or "")
        umo = getattr(event, "unified_msg_origin", None)
        if not gid or not umo:
            return                                  # 私聊里不响应，避免误绑
        bound = await self._kv_get("push_group")
        if bound and bound != gid and not self._config_groups():
            logger.warning("[notice] 拒绝重新绑定：已绑定 %s，请求来自 %s", bound, gid)
            return                                  # 已绑定别的群 → 静默拒绝
        await self._kv_put("push_umo", umo)
        await self._kv_put("push_group", gid)
        logger.info("[notice] 已绑定推送群 %s，umo=%s", gid, umo)
        yield event.plain_result(f"已把本群设为日报推送目标（群 {gid}）。\n之后只会往这个群发通知。")

    async def _send(self, umo: str, text: str) -> None:
        """主动发消息必须传 MessageChain（AstrBot 4.x 的 send_message 签名要求）。"""
        await self.context.send_message(umo, MessageChain().message(text))

    # ------------------------------------------------------------ 实时推送
    async def _realtime_loop(self) -> None:
        """每 N 分钟问一次后端「有没有新通知」，有就立刻发到群里。

        开机补抓：后端刚启动时会立刻抓一轮（夜里关机期间的新通知就在这一轮进来），
        但抓取要几十秒，所以启动后先密集检查几次，把「开机后一并补推」做顺。
        """
        await asyncio.sleep(15)                 # 等适配器就绪
        for gap in (0, 20, 40, 90, 180):        # 前 ~5 分钟密集检查
            if gap:
                await asyncio.sleep(gap)
            try:
                await self._push_new()
            except asyncio.CancelledError:
                raise
            except Exception as e:              # noqa: BLE001
                logger.error("[notice] 开机补推异常: %s", e)

        while True:
            try:
                await self._push_new()
            except asyncio.CancelledError:
                raise
            except Exception as e:              # noqa: BLE001
                logger.error("[notice] 实时推送异常: %s", e)
            await asyncio.sleep(self._watch_interval() * 60)

    async def _push_new(self) -> None:
        umo = await self._target_umo()
        if not umo:
            return

        last = int(await self._kv_get("last_notice_id", "0") or 0)
        data = await self._get("/api/new", after_id=last, limit=20)
        max_id = int(data.get("max_id") or last)
        items = data.get("items") or []

        if last == 0:
            # 第一次运行：只从「当前最新」开始，不把历史通知全推一遍
            await self._kv_put("last_notice_id", str(max_id))
            logger.info("[notice] 实时推送初始化，起点 id=%s", max_id)
            return
        if not items:
            return

        if len(items) > 3:
            text = self._fmt_batch(items)
        else:
            text = "\n\n".join(self._fmt_single(it) for it in items)

        await self._send(umo, text)
        await self._kv_put("last_notice_id", str(max_id))
        logger.info("[notice] 实时推送 %s 条新通知 → %s", len(items), umo)

    async def _target_umo(self) -> str:
        """取已验证的推送目标；不满足条件返回空串（一个字都不发）。"""
        umo = (self.config.get("push_umo") or "").strip() or await self._kv_get("push_umo")
        if not umo or "GroupMessage" not in umo:
            return ""
        allowed = await self._allowed_groups()
        gid = str(self.config.get("push_group") or await self._kv_get("push_group"))
        if not gid or (allowed and gid not in allowed):
            return ""
        return umo

    SRC_NAME = {"jwc": "教务处", "xsc": "学生工作部", "tw": "校团委",
                "informatics": "信息学院·科创", "informatics_jczd": "信息学院·奖助",
                "cxw": "本科生创新网",
                "xaxq": "翔安校区"}

    def _fmt_single(self, it: dict) -> str:
        src = self.SRC_NAME.get(it.get("source"), it.get("source") or "通知")
        lines = [f"📢 新通知｜{src}", it.get("one_line") or it.get("title") or ""]
        if it.get("deadline"):
            lines.append(f"⏰ 截止 {str(it['deadline'])[:16]}")
        tags = it.get("tags") or []
        if tags and tags[0] != "其他":
            lines.append("🏷 " + "/".join(tags))
        if it.get("url"):
            lines.append(it["url"])
        return "\n".join(lines)

    def _fmt_batch(self, items: list) -> str:
        lines = [f"📢 新通知 {len(items)} 条", ""]
        for i, it in enumerate(items, 1):
            dl = f"（截止 {str(it['deadline'])[:16]}）" if it.get("deadline") else ""
            lines.append(f"{i}. {it.get('one_line') or it.get('title')}{dl}")
        lines += ["", "详情见 /今日；摘要由模型生成，以原文为准。"]
        # aiocqhttp 会 strip 首尾空白，用零宽空格护住排版
        return ZWSP + "\n".join(lines) + ZWSP

    # ------------------------------------------------------------ 定时推送
    async def _daily_loop(self) -> None:
        """到点自动推；错过（关机/服务没起）则在启动或下一轮补推；失败 30 分钟后重试。

        这一段就是「不需要人每天发 /今日」的全部实现。
        """
        await asyncio.sleep(15)                 # 等 AstrBot 适配器完全就绪
        while True:
            try:
                if await self._should_push_now():
                    ok = await self._push_daily()
                    if not ok:
                        logger.warning("[notice] 本次推送未成功，30 分钟后重试")
                        await asyncio.sleep(1800)
                        continue
                target = self._next_run()
                await asyncio.sleep(max(30, (target - datetime.datetime.now()).total_seconds()))
            except asyncio.CancelledError:
                raise
            except Exception as e:              # noqa: BLE001
                logger.error("[notice] 定时推送异常: %s", e)
                await asyncio.sleep(300)

    async def _should_push_now(self) -> bool:
        """今天到点了吗、还没推过吗。两个条件都满足才推（幂等，重启不会重复）。"""
        day = datetime.date.today().isoformat()
        if await self._kv_get(f"delivered_{day}"):
            return False
        hh, mm = (int(x) for x in self._push_time().split(":"))
        now = datetime.datetime.now()
        return (now.hour, now.minute) >= (hh, mm)

    def _next_run(self) -> datetime.datetime:
        hh, mm = (int(x) for x in self._push_time().split(":"))
        now = datetime.datetime.now()
        tgt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if tgt <= now:
            tgt += datetime.timedelta(days=1)
        return tgt

    async def _catch_up(self) -> None:
        """兼容保留：等价于「到点且没推过就推一次」。"""
        if await self._should_push_now():
            await self._push_daily()

    async def _push_daily(self) -> bool:
        """只往「已绑定的那一个群」发；任何条件不满足就一个字都不发。

        返回 True = 已处理完（推成功，或本来没内容/没绑定这类不需要重试的情况）；
        返回 False = 可以重试（后端没起、发送失败）。
        """
        umo = (self.config.get("push_umo") or "").strip() or await self._kv_get("push_umo")
        if not umo:
            logger.warning("[notice] 未绑定推送群，跳过（在目标群发 /绑定推送）")
            return True
        if "GroupMessage" not in umo:            # 防御：非群会话绝不推送
            logger.warning("[notice] umo 不是群会话，拒绝推送：%s", umo)
            return True

        allowed = await self._allowed_groups()
        gid = str(self.config.get("push_group") or await self._kv_get("push_group"))
        if allowed and not gid:
            logger.warning("[notice] 配置了授权群但未绑定推送群，拒绝推送")
            return True
        if allowed and gid and gid not in allowed:
            logger.warning("[notice] 推送群 %s 不在授权名单 %s 内，拒绝推送", gid, allowed)
            return True

        try:
            data = await self._get("/api/digest", limit=12)
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] 取日报失败（后端没起？）: %s", e)
            return False
        if not data.get("items"):
            logger.info("[notice] 今天没有通知，不推送")
            return True

        try:
            await self._send(umo, self._fmt(data))
        except Exception as e:                             # noqa: BLE001
            logger.error("[notice] 发送失败: %s", e)
            return False

        day = datetime.date.today().isoformat()
        await self._kv_put(f"delivered_{day}", "1")
        try:
            await self._post("/api/delivery", chat_id=str(umo),
                             count=len(data["items"]), status="ok")
        except Exception:                                  # noqa: BLE001
            pass
        logger.info("[notice] 日报已推送：%s 条 → %s", len(data["items"]), umo)
        return True
