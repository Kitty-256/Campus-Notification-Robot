# 接口契约（v1）

全组唯一的「接口说明书」。改字段必须：先在群里 @ 全员 → 改这份文档 → 最后改代码。

## 1. 数据流

```
采集器（RSSHub / httpx / Playwright / 人工补录）
        │  POST /ingest  {source,url,title,content,published_at}
        ▼
raw_items（原始快照，url_hash 幂等）
        │  POST /api/admin/process（或定时任务自动）
        ▼
解析 → 去重（L1 url_hash / L2 标题 SimHash）→ 摘要（LLM/降级）→ 打分
        ▼
notices（成品：one_line / deadline / tags / score）
        ▼
GET /api/digest → AstrBot 插件 → 群消息
```

## 2. 关键约定

| 字段 | 类型 | 说明 |
|---|---|---|
| `url` | string | 原文链接，必须可访问；不存正文镜像 |
| `title` | string | 列表页标题，≥6 字（「更多>>」这类会被过滤） |
| `content` | string? | 正文纯文本，截断到 4000 字；为空时标 `short_content` |
| `published_at` | string? | `YYYY-MM-DD`；缺失则用抓取时间 |
| `deadline` | string? | `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM`；**必须能回验命中原文**，否则置 null |
| `tags` | string[] | 枚举：竞赛/奖学金/讲座/宣讲会/选课/考试/停课调课/实习就业/其他 |
| `score` | float | 0~1，当前 = 紧急度（距截止：≤3天 1.0 / ≤7天 0.7 / 其他 0.45） |
| `status` | enum | `published`（可推）/ `review`（低置信度，需人工看） |

## 3. HTTP 接口

| 方法 | 路径 | 入参 | 出参 |
|---|---|---|---|
| GET | `/healthz` | — | `{ok, ts, sources}` |
| POST | `/ingest` | 单个对象或数组 | `{accepted, skipped}` |
| POST | `/api/admin/crawl` | header `X-Admin-Token` | `{sources:[...], ingested, created}` |
| POST | `/api/admin/process` | `limit`, header `X-Admin-Token` | `{created, dup, dropped, scanned}` |
| GET | `/api/digest` | `limit`(1~50), `day` | `{date, total, items:[...]}` |
| GET | `/api/search` | `q`, `limit` | `{q, items:[...]}` |
| POST | `/api/subscribe` | `{qq, tag}` | `{ok, qq, tag}` |
| GET | `/api/stats` | — | `{sources:[{source, ok_cnt, fail_cnt, last_ts}]}` |
| POST | `/api/delivery` | `chat_id, count, status` | `{ok}` |

## 4. 幂等性

- 同一 `url` 重复入库 → `skipped`，不产生第二条；
- 同一天对同一 `chat_id` 重复推送 → `deliveries` 表 upsert，不会产生两条记录；
- `/api/admin/process` 可重复调用，已处理的 `raw_items.processed=1` 不会再处理。

## 5. 失败时的行为（不要静默）

| 环节 | 失败表现 | 兜底 |
|---|---|---|
| 采集 | 源连续 3 次失败 | 记 `fetch_log`，`/api/stats` 可见；不影响其它源 |
| 解析 | 正文 < 30 字 | 标 `short_content`，不生成通知（多为图片型正文） |
| LLM | 超时/额度/JSON 非法 | 降级为「标题 + 首段」，`confidence=0`，仍可推送 |
| 推送 | AstrBot 发送失败 | 插件记日志，日报不落库为已送达，下次定时重试 |
