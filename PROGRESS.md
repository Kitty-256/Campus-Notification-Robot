# 施工日志（PROGRESS）

> 每完成一步就更新这四行。断电 / 换会话时，我（或你）读这个文件就能从断点继续。

---

## 当前状态

```
阶段：第一批 —— 仓库骨架已生成，离线自检通过
已完成：仓库结构、svc 全部模块、插件、离线自检(20/20)、离线端到端演练(PASS)、git 首次提交
下一步：装依赖 → 起服务 → 塞假数据 → 群里收到第一条消息（Step 3~4）
已知问题：① docker 不在当前 PATH（机器人可能在别的机器/未启动 Docker Desktop）
         ② 本机 Python 3.14 缺 httpx/fastapi，需装依赖或用 Docker 镜像（3.12）
         ③ 4 个源的选择器与地址全是"待实测"，第一次抓取要逐个核对
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
- [ ] Step 5：实测 jwc 列表页地址与选择器，把 `sources.yaml` 的 `enabled` 打开
- [ ] Step 6~9：其余 3 个源
- [ ] Step 14：配 `LLM_API_KEY`，跑通真摘要
- [ ] Step 26~29：标注集 + 两组实验 + 7 天连续运行

## 已知风险

1. **docker 不可用**：若本机确实没有 Docker，只能在 Python 里跑 svc（需 `pip install -r svc/requirements.txt`），AstrBot 在别处则要改 `svc_base` 为可达地址。
2. **Python 3.14**：fastapi/pydantic 对 3.14 的支持仍在追赶，若安装失败，用 Docker（镜像内是 3.12）。
3. **源选择器**：`svc/config/sources.example.yaml` 里的地址是初始猜测，必须逐个实测。

## 变更记录

- 2026-11-17 第一批：仓库骨架 + 离线自检 + dryrun 通过；git 首次提交
