# 协作规范（团队必读）

> 这份文件是给 7 个人看的操作手册。目标是：任何人 clone 下来 30 分钟能跑起来，
> 任何人 push 之前不会被别人的改动打断，出了事能一眼看出是谁改的。

---

## 1. 分支模型

| 分支 | 用途 | 谁能直接推 |
|---|---|---|
| `main` | 可演示、可答辩的稳定版 | **没有人**，只能通过 PR 合入 |
| `dev` | 集成分支，日常汇总 | 组长（P1） |
| `feat/<模块>-<简述>` | 个人开发，如 `feat/collect-jwc` | 本人 |

流程：

```bash
git checkout dev && git pull
git checkout -b feat/collect-jwc
# 写代码、本地跑通
git add -A && git commit -m "feat(collect): 接入教务处列表页"
git push -u origin feat/collect-jwc
# 到 GitHub 上开 PR → 目标分支 dev → 至少 1 人 review → 合并
```

每周日由组长把 `dev` 合到 `main`，并在 `PROGRESS.md` 记一笔。

## 2. 提交信息

```
<类型>(<模块>): <一句话说明>

类型：feat 新功能 / fix 修 bug / docs 文档 / refactor 重构 / chore 杂务 / test 测试
模块：collect 采集 / parse 解析 / dedup 去重 / ai 摘要 / bot 插件 / api 接口 / docs 文档
```

例：`fix(dedup): 短标题不启用 SimHash，避免误合并`

## 3. PR 检查清单

- [ ] 本地 `python scripts/selftest.py` 与 `python scripts/dryrun.py` 都通过
- [ ] 没有把 `.env`、`data/`、日志提交上来
- [ ] 改了数据模型或接口 → 同步更新 `docs/contract.md`
- [ ] 新增/修改信息源 → 同步更新 `docs/sources.md` 与 `svc/config/sources.example.yaml`
- [ ] PR 描述写清：改了什么 / 怎么验证 / 影响谁

## 4. 谁负责哪块

| 目录 | 负责人 | 说明 |
|---|---|---|
| `svc/app/collect/` | P2 / P3 | 采集器与路由 |
| `svc/app/parse.py`、`dedup.py` | P3 / P5 | 纯函数，改动必须自带测试 |
| `svc/app/llm.py`、`prompts` | P4 | 提示词与 Schema |
| `svc/app/pipeline.py`、`api` | P1 | 流水线主链路 |
| `plugin/` | P6 | AstrBot 插件（薄壳，不得超过 300 行） |
| `scripts/`、`docs/` | 全员 | 工具与文档 |

改了别人负责的文件先在群里说一声。

## 5. 本地环境

```powershell
git clone <仓库地址> notice-daily
cd notice-daily
Copy-Item .env.example .env      # 填 ADMIN_TOKEN，LLM_API_KEY 可空
pip install -r svc\requirements.txt
python scripts\selftest.py       # 应 20/20 通过
python scripts\dryrun.py         # 应 PASS
start-notice-svc.bat             # 或 python -m uvicorn app.main:app --port 8000
```

**密钥永远不进仓库**：`.env` 已在 `.gitignore` 里；需要新增密钥时，先加到 `.env.example`（占位值），
再在群里发真实值（或单独用私聊/密码管理器）。

## 6. 数据与隐私

- `data/notice.db` 只在本机，不进仓库；
- 提交评测样本前先脱敏（QQ 号、姓名）；
- 抓取内容只用于课程演示，不外发、不镜像整站。
