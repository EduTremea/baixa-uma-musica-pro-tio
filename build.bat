@echo off
REM Gera o BaixadorMP3.exe (rode uma vez, com duplo clique, num Windows com Python 3.10+)
setlocal
cd /d "%~dp0"
title Gerando BaixadorMP3.exe

python --version >nul 2>&1 || (
  echo Python nao encontrado. Instale com:  winget install Python.Python.3.12
  echo Depois feche esta janela e rode o build.bat de novo.
  pause & exit /b 1
)

echo [1/5] Criando ambiente isolado...
if not exist .venv-build python -m venv .venv-build || goto erro
call .venv-build\Scripts\activate.bat

echo [2/5] Instalando bibliotecas (yt-dlp, interface, empacotador)...
python -m pip install --upgrade pip >nul
python -m pip install -U "yt-dlp[default]" customtkinter imageio-ffmpeg mutagen pyinstaller || goto erro

echo [3/5] Preparando o FFmpeg...
if not exist bin mkdir bin
python -c "import imageio_ffmpeg, shutil; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), r'bin\ffmpeg.exe')" || goto erro

echo [4/5] Baixando o Deno (exigido pelo yt-dlp para o YouTube)...
if not exist bin\deno.exe (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' -OutFile deno.zip; Expand-Archive deno.zip -DestinationPath bin -Force; Remove-Item deno.zip" || goto erro
)

echo [5/5] Gerando o executavel (leva alguns minutos)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BaixadorMP3 --icon icone.ico ^
  --add-data "icone.ico;." ^
  --add-binary "bin\ffmpeg.exe;bin" ^
  --add-binary "bin\deno.exe;bin" ^
  --collect-all customtkinter ^
  --collect-all yt_dlp_ejs ^
  baixador_mp3.py || goto erro

echo.
echo Pronto! Executavel gerado em: %cd%\dist\BaixadorMP3.exe
explorer dist
pause
exit /b 0

:erro
echo.
echo Ocorreu um erro. Veja as mensagens acima.
pause
exit /b 1
