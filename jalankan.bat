@echo off
title Screener Saham IDX
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Belum terpasang. Klik dua kali "install.bat" dulu.
  pause
  exit /b 1
)
echo Membuka screener di browser... (biarkan jendela ini terbuka, tutup untuk berhenti)
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8501"
.venv\Scripts\python.exe -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
pause
