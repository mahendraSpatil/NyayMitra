@echo off
rem Law questions with and without RELEVANT LAW, straight to llama-server (8081).
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
"backend\.venv\Scripts\python.exe" demo\law_check.py > demo\.state\law_check.log 2>&1
echo exit=%ERRORLEVEL% >> demo\.state\law_check.log
