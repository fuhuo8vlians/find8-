@echo off
cd /d "%~dp0"
echo [*] Installing dependencies...
pip install -r requirements.txt -q
echo.
echo [*] Starting find8威廉斯 v1.0...
echo [*] Access: http://localhost:5500
python app.py
pause
