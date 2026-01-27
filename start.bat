@echo off
echo ========================================
echo   Antigravity Remote Control - Startup
echo ========================================
echo.

REM Start Backend
echo [1/3] Starting Backend Server...
start "Backend Server" cmd /k "cd /d %~dp0backend && npm install && npm run dev"
timeout /t 3 /nobreak >nul

REM Start Agent
echo [2/3] Starting PC Agent...
start "PC Agent" cmd /k "cd /d %~dp0agent && pip install -r requirements.txt && python agent.py"
timeout /t 2 /nobreak >nul

REM Start Mobile Server
echo [3/3] Starting Mobile PWA Server...
start "Mobile PWA" cmd /k "cd /d %~dp0mobile && npx -y serve . -l 3000"

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo Backend:  http://localhost:8080
echo Mobile:   http://localhost:3000
echo.
echo Press any key to exit...
pause >nul
