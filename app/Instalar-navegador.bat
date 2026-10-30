@echo off
setlocal
cd /d "%~dp0"
echo Instalando componente gratuito de navegacao para o codigo-fonte.
echo No app Windows compilado, o Chromium ja vem incluido.
where py >nul 2>nul
if errorlevel 1 goto python
py -3 -m pip install playwright==1.64.1
if errorlevel 1 goto falha
py -3 -m playwright install chromium --no-shell
if errorlevel 1 goto falha
goto pronto
:python
python -m pip install playwright==1.64.1
if errorlevel 1 goto falha
python -m playwright install chromium --no-shell
if errorlevel 1 goto falha
:pronto
echo Pronto. Reinicie o escritorio pelo mesmo Python usado nesta instalacao.
pause
exit /b 0
:falha
echo Falha na instalacao. Confira Python e internet; leia o README.
pause
exit /b 1
