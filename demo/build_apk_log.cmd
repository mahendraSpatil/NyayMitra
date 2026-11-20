@echo off
rem Builds the release APK from the committed app (HEAD) and logs to .state\apk_build.log
cd /d "%~dp0.."
set LOG=%~dp0.state\apk_build.log
echo start %DATE% %TIME% > "%LOG%"
if exist demo\.state\apkclient rmdir /s /q demo\.state\apkclient
mkdir demo\.state\apkclient
git archive HEAD client | tar -x -C demo\.state\apkclient >> "%LOG%" 2>&1
cd demo\.state\apkclient\client
call flutter pub get >> "%LOG%" 2>&1
call flutter build apk --release >> "%LOG%" 2>&1
echo exit=%ERRORLEVEL% >> "%LOG%"
