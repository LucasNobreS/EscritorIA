@echo off
cd /d "%~dp0"
echo Instalando Pillow para textos, logo e motion SaaS locais.
py -3 -m pip install Pillow
if errorlevel 1 (
 echo Nao foi possivel instalar Pillow. Confira a instalacao do Python e sua conexao.
 pause
 exit /b 1
)
call "%~dp0Instalar-video.bat"
