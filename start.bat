@echo off
REM Claude Code Karma - Start Backend (port 8000) and Frontend (port 5199)

set BACKEND_PORT=8000
set FRONTEND_PORT=5199

echo Starting Claude Code Karma...
echo.

REM Function to kill process on port
call :killPort %BACKEND_PORT% "Backend"
call :killPort %FRONTEND_PORT% "Frontend"

REM Start Backend on port 8000
echo [1/2] Starting Backend on port %BACKEND_PORT%...
start "Backend-API" cmd /k "cd /d %~dp0api && uvicorn main:app --reload --port %BACKEND_PORT%"

REM Wait a bit for backend to start
timeout /t 3 /nobreak > nul

REM Start Frontend on port 5199
echo [2/2] Starting Frontend on port %FRONTEND_PORT%...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --port %FRONTEND_PORT%"

echo.
echo ========================================
echo   Backend: http://localhost:%BACKEND_PORT%
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo ========================================
echo.
goto :eof

:killPort
set PORT=%1
set NAME=%2
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo   - Killing %NAME% process on port %PORT% (PID: %%a)
    taskkill //F //PID %%a > nul 2>&1
)
goto :eof
