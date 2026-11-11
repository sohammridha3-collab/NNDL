@echo off
title Inclusive ATS Backend (Port 8001)
echo =======================================================
echo Starting Inclusive ATS Backend on http://127.0.0.1:8001
echo =======================================================
cd /d "%~dp0"
python main.py
pause
