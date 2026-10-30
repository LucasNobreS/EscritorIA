@echo off
setlocal
cd /d "%~dp0"
title Gerar aplicativo EscritorIA
where py >nul 2>nul
if not errorlevel 1 (
 py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
 if not errorlevel 1 goto usar_py
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto usar_python
echo Python 3.10 ou superior nao encontrado. Instale e tente novamente.
pause
exit /b 1
:usar_py
py -3 build_windows.py
goto resultado
:usar_python
python build_windows.py
:resultado
if errorlevel 1 (
 echo Nao foi possivel gerar. Envie gerar-app.log, se existir, para diagnostico.
 pause
 exit /b 1
)
pause
endlocal
