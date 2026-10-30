@echo off
setlocal
cd /d "%~dp0"
echo Instalacao gratuita de FFmpeg e FFprobe para videos locais.
where ffmpeg >nul 2>nul
if not errorlevel 1 (
 where ffprobe >nul 2>nul
 if not errorlevel 1 goto pronto
)
where winget >nul 2>nul
if errorlevel 1 goto manual
winget install --id Gyan.FFmpeg --exact --source winget
if errorlevel 1 goto manual
:pronto
echo Feche o escritorio e abra novamente Iniciar.bat para atualizar o PATH.
echo Se nao detectar, reinicie o Windows ou use a instalacao manual do README.
goto fim
:manual
echo Instalacao automatica indisponivel.
echo Abra https://ffmpeg.org/download.html e escolha uma compilacao Windows.
echo Coloque ffmpeg.exe e ffprobe.exe em tools\ffmpeg\bin\ dentro desta pasta.
echo Leia o README para o passo a passo. Nao e necessaria chave de API.
:fim
pause
endlocal
