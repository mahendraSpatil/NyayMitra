@echo off
rem Runs the full backend test suite and saves the log to demo\.state\pytest.log.
cd /d "%~dp0.."
if not exist "demo\.state" mkdir "demo\.state"
echo starting > "demo\.state\pytest.log"
docker compose up -d >> "demo\.state\pytest.log" 2>&1
timeout /t 5 >nul
cd backend
".venv\Scripts\python.exe" -m alembic upgrade head >> "..\demo\.state\pytest.log" 2>&1
".venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider >> "..\demo\.state\pytest.log" 2>&1
echo exit=%ERRORLEVEL% >> "..\demo\.state\pytest.log"
