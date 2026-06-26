@echo off
cd /d "%~dp0"
echo [*] Starting find8威廉斯 v1.0 in Web Server Mode...
echo [*] Access: http://localhost:5500
python app.py --web
pause
