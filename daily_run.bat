@echo off
cd /d "D:\MyAi_Assistant\nepse_agent"
call .venv\Scripts\activate.bat
python daily_run.py >> logs\daily_run.log 2>&1