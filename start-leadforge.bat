@echo off
setlocal
title LeadForge AI - Start
cd /d "%~dp0"

echo ==================================================
echo    LeadForge AI - starting up...
echo ==================================================
echo.

REM ---- 1. Make sure the Docker engine is running ----
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

echo Docker is not running. Launching Docker Desktop...
if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
) else (
    echo.
    echo   Could not find Docker Desktop at the default path.
    echo   Please start Docker Desktop manually, then run this file again.
    echo.
    pause
    exit /b 1
)

echo Waiting for the Docker engine to come up ^(this can take a minute^)...
set /a tries=0
:wait_docker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a tries+=1
if %tries% geq 40 (
    echo   Docker did not start in time. Open Docker Desktop manually and re-run.
    pause
    exit /b 1
)
goto wait_docker

:docker_ready
echo Docker is ready.
echo.

REM ---- 2. Start the containers ----
echo Starting containers ^(docker compose up -d^)...
docker compose up -d
if errorlevel 1 (
    echo.
    echo   Failed to start the containers - see the error above.
    pause
    exit /b 1
)
echo.

REM ---- 3. Wait for the web app (first run builds the frontend, ~1 min) ----
echo Waiting for the web app to be ready...
set /a tries=0
:wait_web
timeout /t 4 /nobreak >nul
curl -s -o nul http://localhost:3001
if not errorlevel 1 goto web_ready
set /a tries+=1
if %tries% geq 45 (
    echo   Web app is taking longer than usual - opening anyway.
    goto web_ready
)
goto wait_web

:web_ready
echo.
echo ==================================================
echo    LeadForge is up!
echo      Web app :  http://localhost:3001/today
echo      Backend :  http://localhost:8001
echo.
echo    To stop it later, run:  stop-leadforge.bat
echo ==================================================
start "" http://localhost:3001/today
timeout /t 3 /nobreak >nul
endlocal
