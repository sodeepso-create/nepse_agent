@echo off
cd /d "D:\MyAi_Assistant\nepse_agent"
".venv\Scripts\python.exe" daily_run.py >> "logs\daily_run.log" 2>&1