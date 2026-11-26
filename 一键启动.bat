@echo off
setlocal
chcp 65001 >nul
title Retouch Desk
pushd "%~dp0"
if errorlevel 1 goto :failed
if exist "release\RetouchDesk\RetouchDesk.exe" (
  start "" "release\RetouchDesk\RetouchDesk.exe"
  popd
  exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\start.ps1"
if errorlevel 1 goto :failed
popd
exit /b 0
:failed
echo.
echo [启动失败] 请查看上方错误信息。也可直接运行 release\RetouchDesk\RetouchDesk.exe。
pause
popd
exit /b 1
