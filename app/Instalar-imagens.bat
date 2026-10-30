@echo off
setlocal
cd /d "%~dp0"
echo Instalando Pillow para criar imagens localmente. Nao exige chave paga.
where py >nul 2>nul
if errorlevel 1 (
 python -m pip install -r requirements-optional.txt
) else (
 py -3 -m pip install -r requirements-optional.txt
)
if errorlevel 1 (
 echo Falha. Confira a conexao e a instalacao do Python.
) else (
 echo Pronto. Feche e abra novamente Iniciar.bat.
)
pause
endlocal
