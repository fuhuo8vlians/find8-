@echo off
cd /d "%~dp0"
python oneforall.py --targets url.txt run
pause