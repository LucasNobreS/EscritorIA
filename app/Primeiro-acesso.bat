@echo off
setlocal
cd /d "%~dp0"
title EscritorIA - Primeiro acesso
echo EscritorIA - Preparar primeiro acesso
echo.
where py >nul 2>nul
if not errorlevel 1 (
 py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
 if not errorlevel 1 goto pronto
)
where python >nul 2>nul
if not errorlevel 1 (
 python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
 if not errorlevel 1 goto pronto
)
echo Instale Python 3.10 ou superior no site oficial.
echo Durante a instalacao, marque Add Python to PATH.
echo Depois feche esta janela e abra Primeiro-acesso.bat novamente.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
:pronto
echo Python encontrado. Criando atalho na area de trabalho...
powershell -NoProfile -File "%~dp0Criar-atalho.ps1"
if errorlevel 1 echo Nao foi possivel criar o atalho. Voce pode usar Iniciar.bat normalmente.
echo.
echo A janela do servidor precisa continuar aberta enquanto voce joga.
call "%~dp0Iniciar.bat"
endlocal
