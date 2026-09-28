@echo off
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Setup done. Next:
echo   python main.py init-db
echo   python main.py collect --history
echo   python main.py analyze NABIL
