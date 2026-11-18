@echo off
chcp 65001 >nul
title notice-svc - 校园通知日报
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONPATH=svc"

echo ============================================================
echo   notice-svc  校园通知日报后端
echo   http://127.0.0.1:8000/healthz
echo   Ctrl+C 停止
echo ============================================================
echo.

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo notice-svc 已退出。按任意键关闭。
pause >nul
