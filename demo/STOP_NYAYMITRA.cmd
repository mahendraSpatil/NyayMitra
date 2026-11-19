@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_demo.ps1"
timeout /t 3 >nul
