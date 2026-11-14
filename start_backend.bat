@echo off
setlocal enabledelayedexpansion
title Inclusive ATS Backend (127.0.0.1:8001)

echo ============================================================================
echo   INCLUSIVE ATS & JOB MATCHING SYSTEM (SDG 10) - WINDOWS LAUNCHER
echo ============================================================================
echo.

cd /d "%~dp0"

:: 1. Detect Python executable (virtualenv or system Python)
set "PY_CMD=python"
if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    echo [INFO] Using virtual environment: venv\Scripts\python.exe
) else if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    echo [INFO] Using virtual environment: .venv\Scripts\python.exe
) else (
    echo [INFO] Using system Python
)

:: 2. Pre-check Port 8001 availability
netstat -ano -p tcp | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo ============================================================================
    echo   [ERROR] PORT CONFLICT: Port 8001 is already in use by another application.
    echo ============================================================================
    echo   Please stop the process using port 8001, or run with a custom port:
    echo     set PORT=8002 ^& %PY_CMD% main.py
    echo.
    pause
    exit /b 1
)

:: 3. Launch Canonical Backend
echo.
echo [INFO] Starting backend service on http://127.0.0.1:8001 ...
echo [IMPORTANT] KEEP THIS TERMINAL WINDOW OPEN while using the application.
echo             Closing this window will stop the local backend server.
echo.

%PY_CMD% -u main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Backend server stopped unexpectedly with exit code %errorlevel%.
    pause
)
