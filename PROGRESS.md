# 施工日志（PROGRESS）

> 每完成一步就更新这四行。断电 / 换会话时，我（或你）读这个文件就能从断点继续。

---

## 当前状态

```
阶段：第一批 —— 骨架完成；4 源实测完毕；信息学院改用浏览器渲染
已完成：仓库结构、svc 全部模块、插件、离线自检(20/20)、离线端到端演练(PASS)、
        4 源实测（jwc/xsc/tw 服务端可用；informatics 需 playwright）、git 提交
下一步：装依赖 → 起服务 → 塞假数据 → 群里收到第一条消息（Step 3~4）
已知问题：① docker 不在当前 PATH（机器人可能在别的机器/未启动 Docker Desktop）
         ② 本机 Python 3.14 缺 httpx/fastapi；信息学院还缺 playwright
         ③ 信息学院的浏览器采集器尚未在真机验证过（代码已写好，逻辑待实测）
```

## 关键决策（已定，不要反复推翻）

| 项 | 决定 |
|---|---|
| 机器人方案 | 沿用现有 AstrBot + SnowLuma，不重写；插件 ≤300 行薄壳 |
| 部署形态 | 先本地；云服务器等作业验收前再定（见手册 v2.0 第 1 章） |
| 范围 | 4 源 / 4 指令 / 无 Web 后台（V2 再加） |
| 摘要模型 | 在线 API 为主；没配 Key 时走降级摘要，系统照常跑 |
| 去重 | L1 URL + L2 标题 SimHash（L3 向量留到 V2） |
| 调度 | notice-svc 内定时抓取；插件内定时推送 + 启动补推 |

## 待办（按顺序）

- [ ] Step 3：起 notice-svc（docker compose 或本地 venv），`/healthz` 通
- [ ] Step 4：`/ingest` 塞假数据 → `/api/admin/process` → `/api/digest` 有数据
- [ ] Step 4b：插件装进 AstrBot，群里 `/绑定推送` 拿到 umo
- [ ] Step 4c：`/今日` 在群里返回内容（第一条端到端消息）
- [ ] Step 5：`/api/admin/crawl` 抓真实数据（教务/学工部/团委 三个 html 源应直接可用）
- [ ] Step 5b：装 playwright（可选）后验证信息学院的 browser 源
- [ ] Step 14：配 `LLM_API_KEY`，跑通真摘要
- [ ] Step 26~29：标注集 + 两组实验 + 7 天连续运行

## 断点：明天从这里开始

**开工前**：开一个 PowerShell，`cd D:\校园通知小助手\notice-daily`，然后按顺序：

```powershell
# 1) 确认 Docker 在（SnowLuma / AstrBot 都靠它）
docker ps

# 2) 配置
Copy-Item .env.example .env
notepad .env                                  # 至少把 ADMIN_TOKEN 改掉

# 3) 起服务（二选一）
docker compose up -d --build                  # A. 有 Docker
# 或
cd svc; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 4) 冒烟
curl http://127.0.0.1:8000/healthz
curl -X POST http://127.0.0.1:8000/api/admin/crawl -H "X-Admin-Token: change-me"
curl "http://127.0.0.1:8000/api/digest?limit=10"
```

**判断成功的标准**：第 3 条命令能返回带真实标题的 JSON（教务/学工部/团委 三源）。
拿到之后再把插件拷进 AstrBot、群里 `/绑定推送` + `/今日`。

**如果起不来**：把报错贴给 AI，并同时说明「你是 Docker 还是本地 Python」——两者的排查路径完全不同。

## 明天要先解决的三个未知数

1. **Docker 到底有没有**（当前 PATH 里没有；这台机器可能没装 Docker Desktop）
2. **真实抓取能不能过**：3 个 html 源的选择器已实测，但 `generic.collect()` 首次跑真实站点的编码/详情页可能还要微调
3. **plugins 装进 AstrBot 后能不能拿到 umo**（`/绑定推送` 一步）

## 已知风险

1. **docker 不可用**：若本机确实没有 Docker，只能在 Python 里跑 svc（需 `pip install -r svc/requirements.txt`），AstrBot 在别处则要改 `svc_base` 为可达地址。
2. **Python 3.14**：fastapi/pydantic 对 3.14 的支持仍在追赶，若安装失败，用 Docker（镜像内是 3.12）。
3. **源选择器**：`svc/config/sources.example.yaml` 里的地址是初始猜测，必须逐个实测。

## 变更记录

- 2026-11-17 第一批：仓库骨架 + 离线自检 + dryrun 通过；git 首次提交
