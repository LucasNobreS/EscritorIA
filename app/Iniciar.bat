@echo off
setlocal
cd /d "%~dp0"
title EscritorIA v0.45.0
echo Iniciando nesta pasta: %cd%
echo Mantenha esta janela aberta. Use a aba aberta automaticamente.
where py >nul 2>nul
if not errorlevel 1 (
 py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
 if not errorlevel 1 goto usar_py
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto usar_python
echo Python 3.10 ou superior nao encontrado. Abra Primeiro-acesso.bat.
pause
exit /b 1
:usar_py
py -3 server.py
goto resultado
:usar_python
python server.py
:resultado
if errorlevel 1 (
 echo Nao foi possivel iniciar. Confira a mensagem acima.
 pause
)
endlocal
