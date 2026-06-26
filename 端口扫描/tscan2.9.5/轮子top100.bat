@echo off
chcp 65001 >nul 2>&1
echo === TscanClient v2.9.5 Top100 ===
if exist port.txt del /F /Q port.txt
if exist url.txt del /F /Q url.txt
python 2.py
python ppp.py
if exist res.json del /F /Q res.json
if exist res_processed.txt del /F /Q res_processed.txt
if exist res_processed.xlsx del /F /Q res_processed.xlsx
start python 1.py
pause