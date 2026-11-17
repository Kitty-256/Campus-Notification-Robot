# 运行手册（排错用）

## 一、启动顺序

```powershell
# 1. 网络（只需一次）
docker network create botnet

# 2. 配置
Copy-Item .env.example .env   # 填 LLM_API_KEY（可空）

# 3. 起服务
docker compose up -d --build
docker compose logs -f notice-svc

# 4. 冒烟
curl http://127.0.0.1:8000/healthz
```

## 二、报错 → 原因 → 处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `network botnet not found` | 网络名不对 | `docker network ls` 看实际名字，改 compose |
| 容器起了但 `/healthz` 超时 | 端口被占 | `netstat -ano | findstr :8000`，改端口 |
| `database is locked` | 并发写 | 已开 WAL；仍出现就降低 `CRAWL_INTERVAL_MIN` |
| 抓回来标题是乱码 | 编码 | `sources.yaml` 里 `encoding: gbk` |
| `ModuleNotFoundError: selectolax` | 依赖没装 | `pip install -r svc/requirements.txt` |
| `/api/digest` 一直空 | 没有 `published` 通知 | 先 `/ingest` 塞一条假数据，再 `process` |
| 通知全进 `review` | 没配 LLM Key（降级 confidence=0） | 正常现象；配了 Key 就会进 `published` |
| 插件报 `Cannot connect to host notice-svc` | 不在同一 docker 网络 | 两个 compose 都要 `external: true` 同一个网络 |
| 群里 `/今日` 无响应 | 插件没启用 / 命令被别的插件抢 | AstrBot WebUI 插件页确认启用；日志搜 `[notice]` |
| `/绑定推送` 没反应 | 私聊场景无群 umo | 在群里发一次 |
| 多行消息挤成一行 | aiocqhttp strip | 已加 `\u200b`；仍不行改成每行一个 Plain |
| 早上 07:30 没收到 | 机器当时关机 | 开机后插件会自动补推（看日志 `补推`） |

## 三、日常检查

```powershell
# 各源最近是否成功
curl http://127.0.0.1:8000/api/stats

# 今天推了几条、推没推
sqlite3 data/notice.db "select * from deliveries order by id desc limit 5;"

# 最近 20 条通知
sqlite3 data/notice.db "select id,status,deadline,one_line from notices order by id desc limit 20;"
```

## 四、备份

```powershell
sqlite3 data/notice.db ".backup 'data/backup-$(Get-Date -Format yyyyMMdd).db'"
```

## 五、上线前 6 项检查

- [ ] `/healthz` 正常
- [ ] 4 个源至少 3 个能抓到正确标题
- [ ] `/api/digest` 有当天数据
- [ ] 群里 `/今日` `/搜索` `/订阅` `/帮助` 全部可用
- [ ] 07:30 定时推送实测一次（把 `push_time` 改成 2 分钟后）
- [ ] 重启容器后不重复推送、能自动补齐
