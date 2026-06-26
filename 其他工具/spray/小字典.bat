@echo off
rem 检查并删除 res.json 文件
if exist "res.json" (
    del "res.json"
)

for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value') do set "datetime=%%i"
set "date_folder=%datetime:~4,2%%datetime:~6,2%"
if not exist "%date_folder%" mkdir "%date_folder%"

spray.exe -l url.txt -d dirv2.txt   -f "res.json"

python process_data.py "res.json" "res_processed.xlsx"

if exist "res_processed.xlsx" (
    set "count=1"
    :loop
    set "new_file_name=res_%date_folder%_processed_%count%.xlsx"
    if exist "%date_folder%\%new_file_name%" (
        set /a count+=1
        goto loop
    )
    move "res_processed.xlsx" "%date_folder%\%new_file_name%"
) 

pause