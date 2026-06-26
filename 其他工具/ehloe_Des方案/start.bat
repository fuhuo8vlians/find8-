@echo off
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value') do set "datetime=%%i"
set "date_folder=%datetime:~4,2%%datetime:~6,2%"
if not exist "%date_folder%" mkdir "%date_folder%"

set "count=1"
:loop
set "output_file=%date_folder%\res_%date_folder%_%count%.xlsx"
if exist "%output_file%" (
    set /a count+=1
    goto loop
)

ehole finger -l url.txt -o "%output_file%"
    