# 开机自检：一条命令看清机器人链路是否就绪
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$botDir = 'C:\Users\28221\Desktop\QQ Robot\qqbot'

function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(800) -and $client.Connected) { return $true }
        return $false
    } catch { return $false } finally { $client.Close() }
}

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  校园通知日报  开机自检' -ForegroundColor Cyan
Write-Host ('  ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

$rows = @()

# 1) QQ
$qq = Get-Process QQ -ErrorAction SilentlyContinue
$rows += [pscustomobject]@{
    项目 = '1. QQ 客户端'
    状态 = if ($qq) { 'OK' } else { '未运行' }
    说明 = if ($qq) { "PID=$($qq[0].Id)" } else { '先登录 QQNT' }
}

# 2) notice-svc：以接口是否真能返回为准
$svcOk = $false
$svcInfo = '未启动'
if (Test-Port 8000) {
    try {
        $h = Invoke-RestMethod 'http://127.0.0.1:8000/healthz' -TimeoutSec 4
        $d = Invoke-RestMethod 'http://127.0.0.1:8000/api/digest?limit=50' -TimeoutSec 8
        $svcOk = $true
        $svcInfo = "信息源 $($h.sources) 个，今日可推 $($d.total) 条"
    } catch { $svcInfo = '端口在监听，但接口无响应' }
}
$rows += [pscustomobject]@{
    项目 = '2. 后端 :8000'
    状态 = if ($svcOk) { 'OK' } else { '未就绪' }
    说明 = $svcInfo
}

# 3) AstrBot
$astrOk = Test-Port 6185
$rows += [pscustomobject]@{
    项目 = '3. AstrBot :6185'
    状态 = if ($astrOk) { 'OK' } else { '未运行' }
    说明 = if ($astrOk) { 'WebUI 可访问' } else { '双击 start-all.bat' }
}

# 4) 反向 WS
$wsOk = Test-Port 6199
$rows += [pscustomobject]@{
    项目 = '4. OneBot WS :6199'
    状态 = if ($wsOk) { 'OK' } else { '未监听' }
    说明 = 'AstrBot 侧监听端口'
}

# 5) SnowLuma
$snowOk = Test-Port 5099
$rows += [pscustomobject]@{
    项目 = '5. SnowLuma :5099'
    状态 = if ($snowOk) { 'OK' } else { '未运行' }
    说明 = if ($snowOk) { '协议端在线' } else { '需管理员权限启动' }
}

$rows | Format-Table -AutoSize

$ready = $svcOk -and $astrOk -and $snowOk -and $qq
if ($ready) {
    Write-Host '结论：全部就绪。到点会自动推送，你不用再发任何指令。' -ForegroundColor Green
    Write-Host '      想立刻看一眼内容，可以在群里发 /今日。'
} else {
    Write-Host '结论：还没全部就绪，按下面顺序补齐：' -ForegroundColor Yellow
    if (-not $qq) { Write-Host '  - 登录 QQ（不是网页版，是 QQNT 客户端）' }
    if (-not $svcOk) { Write-Host ('  - 双击 ' + (Join-Path $root 'start-notice-svc.bat')) }
    if (-not $astrOk -or -not $snowOk) {
        Write-Host ('  - 双击 ' + (Join-Path $botDir 'start-all.bat') + '，UAC 点「是」')
    }
}
Write-Host ''
Read-Host '按回车键关闭'
