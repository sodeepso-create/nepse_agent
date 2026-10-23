@echo off
title NEPSE AI Report
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python report.py --commentary
echo.
echo ==================================================
echo Report generated! You can close this window.
echo ==================================================
pause