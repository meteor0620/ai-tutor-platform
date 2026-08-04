@echo off
REM 停止 AI教辅智学平台后端
cd /d "%~dp0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
)
echo 后端已停止
