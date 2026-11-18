# notice-svc 启动器：任何失败都会停住窗口并把原因打出来
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = Join-Path $root 'svc'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'svc.log'

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  notice-svc  校园通知日报后端' -ForegroundColor Cyan
Write-Host ('  目录: ' + $root)
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# 1) Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host '[错误] PATH 里找不到 python。' -ForegroundColor Red
    Write-Host '       请安装 Python 3.10+ 安装时勾选 Add python.exe to PATH'
    Read-Host '按回车键退出'
    exit 1
}
Write-Host ('[1/3] Python: ' + $py.Source)
python -V

# 2) 依赖
$deps = & python -c "import fastapi, uvicorn, httpx, selectolax, yaml; print('ok')" 2>&1
if ($deps -notmatch 'ok') {
    Write-Host ''
    Write-Host '[错误] 依赖没装全。执行下面两条命令后再试：' -ForegroundColor Red
    Write-Host ('       cd ' + $root)
    Write-Host '       pip install -r svc\requirements.txt'
    Write-Host ''
    Write-Host ('       实际报错: ' + $deps)
    Read-Host '按回车键退出'
    exit 1
}
Write-Host '[2/3] 依赖检查通过'

# 3) 端口
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host '[提示] 8000 端口已被占用，可能服务已经在跑：' -ForegroundColor Yellow
    Write-Host '       http://127.0.0.1:8000/healthz'
    Write-Host '       若打不开，先关掉占用进程再重新双击。'
    Write-Host ''
}
Write-Host '[3/3] 启动中……'
Write-Host '       健康检查: http://127.0.0.1:8000/healthz'
Write-Host '       今日日报: http://127.0.0.1:8000/api/digest'
Write-Host ('       日志文件: ' + $log)
Write-Host '       Ctrl+C 停止'
Write-Host '------------------------------------------------------------'

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 |
    Tee-Object -FilePath $log -Append

Write-Host '------------------------------------------------------------'
Write-Host 'notice-svc 已退出。上面的报错就是原因，也已写入 logs\svc.log' -ForegroundColor Yellow
Read-Host '按回车键退出'
