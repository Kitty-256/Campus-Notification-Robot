# notice-daily · 校园通知日报机器人

把厦大各官网的通知聚合成每天一条群消息，由大模型摘要、去重、按相关度排序后推送到 QQ 群。

- 机器人层：沿用现有 **AstrBot + SnowLuma**（不重写），本仓库只新增一个薄壳插件（≤300 行）
- 业务层：**notice-svc**（FastAPI + SQLite），负责采集 / 解析 / 去重 / 摘要 / 排序 / 日报
- 设计目标：4 个信息源、4 条指令、无 Web 后台（MVP），一切复杂功能推迟到 V2

> **机器人怎么接起来**（AstrBot + SnowLuma + 插件）：见 [docs/deployment.md](docs/deployment.md)

详细施工步骤见 `项目文档/校园通知日报机器人_实施手册_v2.0_MVP版.docx`。

---

## 目录结构

```
notice-daily/
├─ docker-compose.yml          # notice-svc（+ 可选 rsshub）
├─ .env.example                # 复制成 .env 后填写
├─ svc/                        # 后端服务
│  ├─ app/main.py              # HTTP 接口
│  ├─ app/pipeline.py          # 入库 → 解析 → 去重 → 摘要
│  ├─ app/dedup.py             # 三级去重（纯函数，可单测）
│  ├─ app/parse.py             # 中文日期 / 截止时间 / 正文清洗（纯函数）
│  ├─ app/llm.py               # 摘要 + Schema 校验 + 降级
│  ├─ app/collect/             # 采集器（通用 HTML / RSS）
│  ├─ app/jobs/crawl.py        # 定时抓取
│  ├─ schema.sql               # 建表
│  ├─ requirements.txt
│  └─ Dockerfile
├─ plugin/astrbot_plugin_notice/   # AstrBot 插件（薄壳）
├─ scripts/selftest.py         # 离线自检（无需任何依赖）
└─ docs/
```

---

## 快速开始（本地，Windows）

### 0. 前置条件

- 已有的 AstrBot + SnowLuma 容器正在跑（`docker ps` 能看到）
- Docker Desktop（可选，纯 Python 跑也行）
- Python 3.10+
- **可选**：要抓信息学院（Vue 渲染的站点）需要 playwright；不装则该源被跳过，其它源照常

```powershell
# 需要信息学院时再装（~400MB）
pip install -r svc\requirements-browser.txt
playwright install chromium --with-deps
```

### 1. 确认网络

`notice-svc` 要和 AstrBot 在同一个 docker network 里：

```powershell
docker network ls                      # 找你 bot 用的网络名，通常是 botnet
docker network create botnet           # 没有就建一个
```

如果已有的网络名不是 `botnet`，改 `docker-compose.yml` 里的 `name:`。

### 2. 准备环境变量

```powershell
cd D:\校园通知小助手\notice-daily
Copy-Item .env.example .env
# 编辑 .env：LLM_API_KEY 可以先空着，服务会走降级摘要（不影响跑通）
```

### 3. 起服务

**Docker 方式：**

```powershell
docker compose up -d --build
docker compose logs -f notice-svc
```

**纯 Python 方式（不用 Docker）：**

```powershell
cd svc
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. 验证链路（先不要接爬虫）

```powershell
# 健康检查
curl http://127.0.0.1:8000/healthz

# 塞一条假通知
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d "{\"source\":\"jwc\",\"url\":\"https://jwc.xmu.edu.cn/info/1000/1234.htm\",\"title\":\"关于2026年国家奖学金评审工作的通知\",\"content\":\"请于12月5日17:00前提交材料。\"}"

# 触发处理（解析+去重+摘要）
curl -X POST http://127.0.0.1:8000/api/admin/process -H "X-Admin-Token: change-me"

# 取日报
curl "http://127.0.0.1:8000/api/digest?limit=12"
```

### 5. 装插件

把 `plugin/astrbot_plugin_notice/` 整个目录拷进 AstrBot 的插件目录（`AstrBot/data/plugins/`），重启 AstrBot，WebUI 里启用。

在目标群发：

```
/绑定推送        → 把本群记成日报推送目标
/今日            → 拉当天日报
/搜索 保研
/订阅 竞赛
```

### 6. 让它每天自动跑

`notice-svc` 内部已带定时任务（默认每小时抓一次、07:30 生成日报），插件到点取数推送。
若机器可能关机，插件启动时会**补推**当天日报（`_catch_up`），不会漏。

---

## 常用接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| POST | `/ingest` | 入库（所有采集渠道的唯一入口） |
| POST | `/api/admin/process` | 手动触发「解析→去重→摘要」，需 `X-Admin-Token` |
| POST | `/api/admin/crawl` | 手动抓一轮所有源，需 `X-Admin-Token` |
| GET | `/api/digest?limit=12` | 当天日报 |
| GET | `/api/search?q=保研&limit=5` | 全文检索 |
| POST | `/api/subscribe` | 订阅标签 `{"qq":"123","tag":"竞赛"}` |
| GET | `/api/stats` | 各源抓取状态 |

## 离线自检

```powershell
# 1) 纯函数自检（零依赖、不联网）：解析 / 去重 / 清洗 / 标签
python scripts\selftest.py

# 2) 端到端演练（零依赖、不联网）：入库 → 去重 → 降级摘要 → 日报 → 检索
python scripts\dryrun.py
```

两个脚本都是纯 stdlib，**不需要装任何依赖**，用来区分「逻辑坏了」还是「网络/选择器坏了」。
`dryrun.py` 会在临时目录建库，不会污染 `data/`。

---

## 合规底线

- 只抓公开页面，遵守 robots.txt；每源每小时 1 次、单源并发 1、随机延迟
- 只存标题、摘要、发布时间、链接；不整站镜像正文
- 不抓需要登录 / 含个人信息 / 需缴费的系统
- 所有推送带原文链接与「模型摘要，以原文为准」尾注
