@echo off
chcp 65001 >nul
setlocal
title Create SitGuard shortcut
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_shortcut.ps1"
echo.
echo Done. Shortcut created on Desktop.
echo.
pause
