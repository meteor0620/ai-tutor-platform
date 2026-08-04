@echo off
REM 启动 AI教辅智学平台后端 (FastAPI :8001)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] 虚拟环境不存在，请先运行 install.bat
  exit /b 1
)
start "AI后端" /min ".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8001
echo 后端已启动: http://localhost:8001
