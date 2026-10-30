@echo off
setlocal
cd /d "%~dp0"
set "ATELIE_STATE_ROOT=%~dp0"
call "%~dp0app\Primeiro-acesso.bat"
exit /b %errorlevel%
