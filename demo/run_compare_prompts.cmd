@echo off
rem Compares Alpaca prompt layouts on nyaymitra-v2 (llama-server must be on 8081 with v2).
cd /d "%~dp0.."
"backend\.venv\Scripts\python.exe" demo\compare_prompts.py > demo\.state\compare.log 2>&1
echo done >> demo\.state\compare.log
