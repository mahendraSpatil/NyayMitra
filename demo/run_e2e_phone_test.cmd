@echo off
rem End-to-end test through the public tunnel address, like a phone would.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set /p URL=<demo\.state\url.txt
"backend\.venv\Scripts\python.exe" demo\e2e_phone_test.py %URL% D:\nyaymitra\ocr_test_docs > demo\.state\e2e.log 2>&1
echo exit=%ERRORLEVEL% >> demo\.state\e2e.log
