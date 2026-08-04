@echo off
REM 启动 AI教辅智学平台门户 (Vite :5173)
cd /d "%~dp0"
if not exist "node_modules" (
  echo [ERROR] 依赖未安装，请先运行 npm install
  exit /b 1
)
start "AI门户" /min cmd /c "npm run dev > vite-dev.log 2>&1"
echo 门户已启动: http://localhost:5173
