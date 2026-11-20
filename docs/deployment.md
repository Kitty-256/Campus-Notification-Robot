# 部署说明（机器人是怎么接起来的）

> 这份文档回答一件事：**别人拿到这个仓库，怎么让它跑在自己的 QQ 机器人上。**
> 注意：机器人本体（AstrBot + SnowLuma 的 1.2GB 运行时）**不进仓库**，原因见第 4 节。

---

## 1. 整体结构

```
┌──────────────┐   OneBot v11    ┌──────────────┐   HTTP    ┌──────────────┐
│ SnowLuma     │ ──────────────▶ │ AstrBot      │ ────────▶ │ notice-svc   │
│ (QQ 协议端)  │  反向 WS:6199   │ (插件宿主)    │  :8000    │ (本仓库)     │
└──────────────┘                 └──────────────┘           └──────┬───────┘
        ▲                                │                        │
        │                                 │                        │ HTTP
   QQ 客户端(QQNT)                  QQ 群(只有绑定的那个群)     学校官网 / LLM API
```

- **notice-svc**：本仓库的 `svc/`，负责采集、解析、去重、摘要、日报。跑在 Python 3.10+。
- **AstrBot**：机器人框架，加载本仓库的 `plugin/astrbot_plugin_notice/` 插件（薄壳，只调 HTTP）。
- **SnowLuma**：把本机 QQ 客户端变成 OneBot v11 接口，AstrBot 通过反向 WebSocket 连它。

## 2. 三步装好插件

```powershell
# ① 起后端（本仓库根目录）
cd D:\校园通知小助手\notice-daily
Copy-Item .env.example .env
start-notice-svc.bat

# ② 把插件装进 AstrBot（AstrBotDir 换成你自己的路径）
powershell -ExecutionPolicy Bypass -File scripts\install_plugin.ps1 `
  -AstrBotDir "C:\Users\你的用户名\Desktop\QQ Robot\qqbot\apps\AstrBot"

# ③ 重启 AstrBot，然后在目标群里发：
#    /绑定推送      → 绑定唯一推送群
#    /今日          → 立刻拉一次当天通知
```

插件配置：AstrBot WebUI → 插件 → 校园通知日报 → 配置。
默认值见 `deploy/astrbot_plugin_notice_config.example.json`，**`push_umo` / `push_group` 留空**，由 `/绑定推送` 自动写入。

## 3. 端口与地址

| 服务 | 端口 | 说明 |
|---|---|---|
| notice-svc | 8000 | 本仓库；插件默认连 `http://127.0.0.1:8000` |
| AstrBot WebUI | 6185 | 管理面板 |
| OneBot 反向 WS | 6199 | AstrBot 监听，SnowLuma 主动连 |
| SnowLuma WebUI | 5099 | 协议端面板 |

全部是**本机回环**，不需要公网 IP、不需要内网穿透。

## 4. 为什么机器人本体不进仓库

| 原因 | 具体 |
|---|---|
| 体积 | 1,269 MB（runtime 579 + apps 372 + cache 192 + dist 125），超过 GitHub 建议上限 |
| 密钥 | `apps/SnowLuma/config/onebot.json` 里有 access token |
| 隐私 | `apps/AstrBot/data/data_v4.db` 22MB，含群号、聊天记录 |
| 登录态 | `apps/SnowLuma/data/` 是 QQ 登录态，等于账号 |

**正确做法**：仓库只放「插件源码 + 部署脚本 + 配置模板」，机器人本体各自在本机搭。

## 5. 各个数字在哪改

| 想改什么 | 改哪里 |
|---|---|
| 推送时间（默认 08:00） | 插件配置 `push_time` |
| 实时推送开关/间隔 | `realtime` / `watch_interval_min`（默认 3 分钟） |
| 只允许某个群 | `allowed_groups`（逗号分隔；留空则靠 `/绑定推送` 锁定） |
| 抓取频率 | `.env` 的 `CRAWL_INTERVAL_MIN`（默认 10 分钟） |
| 信息源 | `svc/config/sources.example.yaml`，改完删掉 `data/sources.yaml` 重启 |
| LLM | `.env` 的 `LLM_API_KEY`（留空则走降级摘要，系统照常跑） |

## 6. 换一台机器要带什么

只带这三样（都在仓库里或可重建）：

1. 代码仓库（`git clone`）；
2. `.env`（自己填，别提交）；
3. `data/notice.db`（可选，历史数据；不要也只会少几天检索结果）。

机器人本体按 `README.md` 或第 2 节重新装一遍即可，插件一条命令就位。
