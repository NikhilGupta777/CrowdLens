@echo off
title CrowdLens Launcher
color 0A

echo.
echo  =============================================
echo   CROWDLENS - Starting Servers...
echo  =============================================
echo.

:: Set project root to the folder where this .bat lives
set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%

echo  [1/2] Starting Backend (FastAPI on port 8080)...
start "CrowdLens Backend" cmd /k "cd /d "%ROOT%" && .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload"

echo  [2/2] Starting Frontend (Vite on port 5173)...
start "CrowdLens Frontend" cmd /k "cd /d "%ROOT%\artifacts\company-ai" && pnpm run dev"

:: Wait 4 seconds for servers to boot, then open browser
echo.
echo  Waiting for servers to start...
timeout /t 4 /nobreak >nul

echo  Opening browser...
start "" "http://localhost:5173/"

echo.
echo  =============================================
echo   Both servers are running!
echo   Backend  : http://127.0.0.1:8080
echo   Frontend : http://localhost:5173
echo  =============================================
echo.
echo  Close the two server windows to stop the servers.
pause
