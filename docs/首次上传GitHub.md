# 第一次把项目传到 GitHub（小白版）

> 面向没怎么用过 GitHub 的同学。全过程 ≈ 20 分钟，不需要命令行基础。
> 命令行版在最后一节，想学的可以看。

---

## 第 0 步：注册账号（已有可跳过）

打开 <https://github.com/signup>，用**学校邮箱**注册（以后能白嫖 GitHub 学生包）。
注册完去邮箱点验证链接，然后在 `Settings → Password and authentication` 里打开 2FA（会给你一个恢复码，抄下来存好）。

## 第 1 步：装 GitHub Desktop（推荐给小白）

下载 <https://desktop.github.com/> → 安装 → 打开 → `Sign in to GitHub.com` → 浏览器里授权。

> 为什么用它：不用记命令、不用配 Token，图形界面能看清"改了什么、要提交什么"。

## 第 2 步：把本地仓库加进来

1. GitHub Desktop 菜单：`File → Add local repository…`
2. 选择 `D:\校园通知小助手\notice-daily`
3. 如果弹出 "not a Git repository"，说明选错了目录——要选到有 `.git` 文件夹的那层。

加好之后，左侧会列出 `History`（已有的 20 次提交），右上角有个 `Publish repository` 按钮。

## 第 3 步：发布到 GitHub

1. 点右上角 `Publish repository`
2. Name 填 `notice-daily`
3. **取消勾选** `Keep this code private`（想先私有就保留勾选，答辩后再改公开）
4. 点 `Publish repository`

等进度条走完，去 <https://github.com/你的用户名/notice-daily> 就能看到了，历史提交都在。

## 第 4 步：把 7 个人拉进来

在网页上：仓库 → `Settings` → 左侧 `Collaborators` → `Add people` → 输入对方的 GitHub 用户名或邮箱 → 邀请。
对方邮箱里会收到邀请，接受后就有写权限。

## 第 5 步：保护主分支（重要）

仓库 → `Settings` → `Branches` → `Add branch protection rule`：

- Branch name pattern 填 `main`
- 勾 `Require a pull request before merging`
- 勾 `Require approvals`，数量填 `1`

这样谁都不能直接改 `main`，必须走"提 PR → 有人看过 → 再合并"。答辩版本不会被误改。

## 第 6 步：队友第一次拉代码

1. 装 GitHub Desktop → 登录 → `File → Clone repository` → 选 `notice-daily` → 选个本地目录
2. 打开一个 PowerShell，进到那个目录，装依赖：

```powershell
Copy-Item .env.example .env
pip install -r svc\requirements.txt
python scripts\selftest.py     # 应该 20/20 通过
python scripts\dryrun.py       # 应该 PASS
```

3. 想本地跑起来看效果：双击 `start-notice-svc.bat`，然后浏览器打开 <http://127.0.0.1:8000/api/digest>

## 第 7 步：日常协作流程（每次改代码都这样）

```
① 左上角 Current Branch → New branch → 起名 feat/你的模块
② 改代码
③ 左下角填 Summary（一句话说清改了什么）→ 点 Commit to feat/...
④ 右上角 Push origin
⑤ 网页上会提示 Compare & pull request → 点进去 → 写描述 → Create pull request
⑥ 等一个人点 Approve → Merge pull request
⑦ 回到 Desktop：Current Branch 切回 main → Fetch origin → Pull origin
```

## 千万不要做的事

| 别做 | 为什么 |
|---|---|
| 手动把 `.env`、`data/` 加进提交 | 里面是密钥和真实抓取数据，传上去就公开了（已被 `.gitignore` 挡住，别用 `Add file → Upload files` 绕过） |
| 直接改 `main` | 会覆盖别人的改动，第 5 步的分支保护就是为了防这个 |
| 提交几百 MB 的 `notice.db`、`.docx` | 仓库会变得很慢，而且历史里删不掉 |
| 两个人在同一个分支上改同一段代码 | 会产生冲突（conflict），新手很难解。各开各的 `feat/` 分支 |

## 附：命令行版（可选）

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"

cd D:\校园通知小助手\notice-daily
git remote add origin https://github.com/<你的用户名>/notice-daily.git
git push -u origin main
```

HTTPS 推送时密码要填 **Personal Access Token**（GitHub → Settings → Developer settings →
Personal access tokens → Tokens (classic) → Generate new token → 勾 `repo` → 复制保存，只显示一次）。
