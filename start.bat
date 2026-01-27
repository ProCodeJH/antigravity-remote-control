@echo off
chcp 65001 > nul
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║           ⚡ Antigravity ULTRA FUSION - Start                    ║
echo ║                 초하이퍼 슈퍼 울트라 융합                            ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

:: Start Backend Server
echo [1/2] 🌐 Starting Backend Server (TEST MODE)...
cd /d "%~dp0backend"
start "Backend Server" cmd /k "set TEST_MODE=true && npm run dev"

:: Wait for backend to start
timeout /t 3 /nobreak > nul

:: Start Agent
echo [2/2] 🖥️ Starting ULTRA Agent...
cd /d "%~dp0agent"
start "ULTRA Agent" cmd /k "python agent.py ws://localhost:8080/ws/relay test-session"

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║                    ✅ All services started!                       ║
echo ╠══════════════════════════════════════════════════════════════════╣
echo ║  Backend:   http://localhost:8080                                 ║
echo ║  Mobile:    Open mobile/index.html in browser                    ║
echo ╠══════════════════════════════════════════════════════════════════╣
echo ║  Connect with:                                                    ║
echo ║    Server URL: ws://localhost:8080/ws/relay                      ║
echo ║    Session ID: test-session                                       ║
echo ╠══════════════════════════════════════════════════════════════════╣
echo ║  ULTRA Features:                                                  ║
echo ║    🎤 Voice Control    📋 Clipboard Sync    ⚡ Macros             ║
echo ║    🔊 Audio Stream     👆 Gestures          🎮 H.264 Codec        ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.
pause
