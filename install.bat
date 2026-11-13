@echo off
title Install Screener Saham IDX
cd /d "%~dp0"

set "PY=py -3"
%PY% --version >nul 2>nul && goto ada_python
set "PY=python"
%PY% --version >nul 2>nul && goto ada_python
echo Python tidak ditemukan.
echo Pasang dari https://www.python.org/downloads/ dan centang "Add Python to PATH".
pause
exit /b 1

:ada_python
echo Memakai: %PY%
echo [1/3] Membuat lingkungan Python (.venv)...
%PY% -m venv .venv || goto gagal
echo [2/3] Memperbarui pip...
.venv\Scripts\python.exe -m pip install --upgrade pip || goto gagal
echo [3/3] Memasang paket (beberapa menit)...
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto gagal

echo.
echo Instalasi selesai. Klik dua kali "jalankan.bat" untuk membuka screener.
pause
exit /b 0

:gagal
echo.
echo Instalasi GAGAL. Salin pesan error di atas dan kirimkan untuk dibantu.
pause
exit /b 1
