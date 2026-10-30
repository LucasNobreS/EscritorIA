@echo off
setlocal
cd /d "%~dp0app"
py -3 build_windows.py --installer
set "BUILD_RESULT=%errorlevel%"
if not "%BUILD_RESULT%"=="0" pause
exit /b %BUILD_RESULT%
