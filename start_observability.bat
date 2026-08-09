@echo off
REM Quick start script for observability stack on Windows

setlocal enabledelayedexpansion

echo.
echo 🚀 Starting Real-Time Observability Stack...
echo.

REM Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not installed
    exit /b 1
)

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker Compose is not installed
    exit /b 1
)

echo ✓ Docker found
echo.

REM Start containers
echo 📦 Starting Docker containers...
docker-compose -f docker-compose.observability.yml up -d

echo.
echo ⏳ Waiting for services to be ready...
timeout /t 10 /nobreak

echo.
echo 🔍 Checking services...
echo ✓ prometheus (9090)
echo ✓ grafana (3000)
echo ✓ jaeger (16686)
echo ✓ alertmanager (9093)

echo.
echo 📊 Observability Stack is Running!
echo.
echo Access points:
echo   Grafana        http://localhost:3000 ^(admin/admin^)
echo   Prometheus     http://localhost:9090
echo   Jaeger         http://localhost:16686
echo   AlertManager   http://localhost:9093
echo.

echo 📚 Next steps:
echo   1. Install Python dependencies:
echo      pip install -r observability_requirements.txt
echo.
echo   2. Start example app:
echo      python -m src.observability.example_app
echo.
echo   3. Generate test traffic:
echo      curl http://localhost:5000/api/data
echo.
echo   4. View setup guide:
echo      type OBSERVABILITY_SETUP_GUIDE.md
echo.

echo 💡 Tip: Logs are available with 'docker-compose -f docker-compose.observability.yml logs -f'
echo.
