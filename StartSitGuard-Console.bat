@echo off
rem SitGuard 命令行启动（排障用，会保留控制台输出）
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"
cd /d "%HERE%"
"%PY%" main.py %*
