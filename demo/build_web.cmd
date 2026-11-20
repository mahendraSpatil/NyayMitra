@echo off
rem Builds the web version of the committed app (HEAD, not uncommitted edits) into demo\.state\webclient\client\build\web
cd /d "%~dp0.."
set LOG=%~dp0.state\web_build.log
echo start %DATE% %TIME% > "%LOG%"
if exist demo\.state\webclient rmdir /s /q demo\.state\webclient
mkdir demo\.state\webclient
git archive HEAD client | tar -x -C demo\.state\webclient >> "%LOG%" 2>&1
cd demo\.state\webclient\client
call flutter --version >> "%LOG%" 2>&1
call flutter pub get >> "%LOG%" 2>&1
call flutter build web --release >> "%LOG%" 2>&1
echo exit=%ERRORLEVEL% >> "%LOG%"
