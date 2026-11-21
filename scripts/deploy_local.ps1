# 更新并部署到本机机器人：拉最新代码 → 同步插件 → 提示重启
#
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_local.ps1 `
#       -AstrBotDir "C:\Users\你\Desktop\QQ Robot\qqbot\apps\AstrBot"
#
# 做的事：
#   1) git pull（只允许快进，避免把本机临时改动搅进来）
#   2) 把 plugin/ 覆盖安装到 AstrBot
#   3) 打印还需要手工做的两步（重启 AstrBot、重启 notice-svc）
#
# 不做的事：不替你重启进程、不清数据库、不动 data/

param(
    [Parameter(Mandatory = $true)]
    [string]$AstrBotDir,
    [string]$Branch = "main"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  1) 拉取最新代码' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
git fetch origin
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 拉取失败：检查网络或 GitHub 登录状态' -ForegroundColor Red
    exit 1
}
$before = git rev-parse --short HEAD
git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host '[错误] 无法快进合并。本机可能有未提交改动，或历史已分叉。' -ForegroundColor Red
    Write-Host '       先执行 git status 看看，或把本地改动提交/暂存后再试。'
    exit 1
}
$after = git rev-parse --short HEAD
if ($before -eq $after) {
    Write-Host "已经是最新（$after），没有新提交。" -ForegroundColor Yellow
} else {
    Write-Host "已更新：$before → $after" -ForegroundColor Green
    git --no-pager log --oneline "$before..$after" | ForEach-Object { Write-Host "  $_" }
}

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  2) 同步插件到 AstrBot' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install_plugin.ps1') -AstrBotDir $AstrBotDir -Force

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  3) 还需要你手工做两步' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  a) 重启 AstrBot：关掉 AstrBot 窗口，重新双击 start-all.bat（UAC 点“是”）'
Write-Host '     —— 插件代码只有重启后才会重新加载'
Write-Host '  b) 如果这次改动涉及 svc/（后端），再关掉 notice-svc 窗口、重新双击 start-notice-svc.bat'
Write-Host ''
Write-Host '  验证：群里发 /今日，能正常返回就说明新版本在跑。'
