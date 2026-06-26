@echo off
cd /d "%~dp0"
echo [*] Starting InfoCollector in Web Server Mode...
echo [*] Access: http://localhost:5500
python app.py --web
pause
