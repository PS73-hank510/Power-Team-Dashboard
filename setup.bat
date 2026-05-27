@echo off
echo === Power Systems Monitoring Dashboard — First-time Setup ===
echo.
python -m venv venv
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11+ and try again.
    pause
    exit /b 1
)
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
echo.
echo === Setup complete ===
echo Run the dashboard with: python main.py
echo Or double-click run.bat
pause
