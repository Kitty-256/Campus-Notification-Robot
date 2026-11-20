# 一键把本仓库的插件装进 AstrBot
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_plugin.ps1 `
#       -AstrBotDir "C:\Users\你\Desktop\QQ Robot\qqbot\apps\AstrBot"
#
# 只做三件事：检查路径 → 复制 plugin/ → 提醒重启。不会碰 AstrBot 的其他文件。

param(
    [Parameter(Mandatory = $true)]
    [string]$AstrBotDir,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root 'plugin\astrbot_plugin_notice'

if (-not (Test-Path $src)) {
    Write-Host "[错误] 找不到插件源目录：$src" -ForegroundColor Red
    exit 1
}

$pluginRoot = Join-Path $AstrBotDir 'data\plugins'
if (-not (Test-Path $pluginRoot)) {
    Write-Host "[错误] 这个路径下没有 data\plugins，确认 AstrBotDir 指向 AstrBot 根目录：" -ForegroundColor Red
    Write-Host "       $AstrBotDir"
    Write-Host "       正确示例：...\qqbot\apps\AstrBot"
    exit 1
}

$dst = Join-Path $pluginRoot 'astrbot_plugin_notice'
if (Test-Path $dst) {
    if (-not $Force) {
        Write-Host "[提示] 目标已存在，将先删除再安装（旧版会被替换）。" -ForegroundColor Yellow
    }
    Remove-Item -LiteralPath $dst -Recurse -Force
}
Copy-Item -LiteralPath $src -Destination $dst -Recurse
Remove-Item -LiteralPath (Join-Path $dst '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host "[完成] 插件已安装到：" -ForegroundColor Green
Write-Host "       $dst"
Get-ChildItem -LiteralPath $dst -File | ForEach-Object { Write-Host "       - $($_.Name)" }
Write-Host ''
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host '  1) 重启 AstrBot（关掉窗口，重新双击 start-all.bat）'
Write-Host '  2) AstrBot WebUI -> 插件 -> 确认「校园通知日报」已启用'
Write-Host '  3) 在目标 QQ 群发 /绑定推送，再发 /今日'
