# 启动 AI教辅智学平台（MaxKB + Vue3 门户）
# 用法：右键 → 用 PowerShell 运行

Write-Host "=== 启动 AI教辅智学平台 ===" -ForegroundColor Cyan

# 1. 启动 Docker Desktop（如果没运行）
$docker = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "[1/4] 启动 Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Start-Sleep -Seconds 30
}
Write-Host "[1/4] Docker 检查完成" -ForegroundColor Green

# 2. 确保 MaxKB 容器运行
docker ps --filter name=maxkb | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker 未就绪，请稍后重试" -ForegroundColor Red
    exit 1
}
$maxkb = docker ps --filter name=maxkb --format "{{.Names}}"
if (-not $maxkb) {
    Write-Host "[2/4] 启动 MaxKB 容器..." -ForegroundColor Yellow
    docker run -d --name=maxkb --restart=always -p 8080:8080 1panel/maxkb
    Start-Sleep -Seconds 30
}
Write-Host "[2/4] MaxKB 运行中 (http://localhost:8080)" -ForegroundColor Green

# 3. 启动后端（FastAPI，8001）
Write-Host "[3/4] 启动后端服务..." -ForegroundColor Yellow
$backendDir = "E:\AI教辅智学平台\meteor-master\meteor-master\后端"
$beAlive = $false
try {
    $check = Invoke-RestMethod -Uri "http://localhost:8001/" -TimeoutSec 5
    $beAlive = $true
} catch {}
if (-not $beAlive) {
    Start-Process -FilePath "$backendDir\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8001" -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput "$backendDir\backend.log" -RedirectStandardError "$backendDir\backend.err.log"
    Start-Sleep -Seconds 5
}
Write-Host "[3/4] 后端运行中 (http://localhost:8001)" -ForegroundColor Green

# 4. 启动门户（Vue3）
Write-Host "[4/4] 启动门户开发服务器..." -ForegroundColor Yellow
$portDir = "E:\AI教辅智学平台\meteor-master\meteor-master\门户"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev > vite-dev.log 2>&1" -WorkingDirectory $portDir -WindowStyle Hidden
Start-Sleep -Seconds 10

Write-Host "" -ForegroundColor Green
Write-Host "=== 启动完成 ===" -ForegroundColor Cyan
Write-Host "MaxKB 管理后台: http://localhost:8080  (账号/密码见后端/.env)"
Write-Host "后端 API:        http://localhost:8001"
Write-Host "学生门户界面:    http://localhost:5173"
Write-Host "浏览器打开上述地址即可使用" -ForegroundColor Green
