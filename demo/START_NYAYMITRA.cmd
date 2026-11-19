@echo off
rem Double-click to start everything (v2 model) and keep it running.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_demo.ps1" %*
pause
