@echo off
cd /d "%~dp0"
py -3 office_backup.py
if errorlevel 1 pause
