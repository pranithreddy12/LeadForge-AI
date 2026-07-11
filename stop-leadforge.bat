@echo off
setlocal
title LeadForge AI - Stop
cd /d "%~dp0"

echo Stopping LeadForge containers ^(your data is kept^)...
docker compose down
echo.
echo Done. Run start-leadforge.bat to bring it back up.
timeout /t 3 /nobreak >nul
endlocal
