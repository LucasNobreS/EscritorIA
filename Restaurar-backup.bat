@echo off
setlocal
cd /d "%~dp0"
set "ATELIE_STATE_ROOT=%~dp0"
call "%~dp0app\Restaurar-backup.bat"
exit /b %errorlevel%
