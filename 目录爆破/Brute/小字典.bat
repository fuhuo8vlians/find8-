@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1 & set "PYTHONIOENCODING=utf-8"

rem 检查并删除 res.json 文件
if exist "res.json" (
    del "res.json"
)

rem 获取当前日期并创建文件夹
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value') do set "datetime=%%i"
set "date_folder=%datetime:~4,2%%datetime:~6,2%"
if not exist "%date_folder%" mkdir "%date_folder%"

rem 执行扫描并处理结果
spray.exe -l url.txt -d dirv2.txt -f "res.json"
python process_data.py "res.json" "res_processed.xlsx"

rem 移动处理后的Excel文件和生成的TXT文件到日期文件夹
if exist "res_processed.xlsx" (
    set "count=1"
    :loop
    set "new_excel_name=res_%date_folder%_processed_!count!.xlsx"
    set "new_txt_name=res_%date_folder%_processed_!count!.txt"
    set "ehole_result_name=ehole_res_%date_folder%_!count!.xlsx"
    if exist "%date_folder%\!new_excel_name!" (
        set /a count+=1
        goto loop
    )
    
    rem 移动Excel文件
    move "res_processed.xlsx" "%date_folder%\!new_excel_name!"
    echo [INFO] Excel文件已归档至：%date_folder%\!new_excel_name!
    
    rem 移动同名TXT文件
    if exist "res_processed.txt" (
        move "res_processed.txt" "%date_folder%\!new_txt_name!"
        echo [INFO] TXT文件已归档至：%date_folder%\!new_txt_name!
        
        rem 调用ehole工具处理移动后的TXT文件
        echo [TASK] 开始执行指纹识别...
        ehole finger -l "%date_folder%\!new_txt_name!" -o "%date_folder%\!ehole_result_name!"
        echo [SUCCESS] 指纹识别结果已保存：%date_folder%\!ehole_result_name!
    ) else (
        echo [WARNING] 未找到TXT文件，跳过ehole处理
    )
) else (
    echo finger process has been done,Good luck ;)
)

rem 新增：处理原始URL列表文件（如果需要）
if exist "url.txt" (
    set "url_result_name=url_ehole_res_%date_folder%.xlsx"
    echo [TASK] 开始处理原始URL列表...
    ehole finger -l "url.txt" -o "%date_folder%\!url_result_name!"
    echo [SUCCESS] 原始URL列表指纹识别结果已保存：%date_folder%\!url_result_name!
) else (
    echo [ERROR] 未找到原始URL列表文件：url.txt
)

pause