@echo off
chcp 65001 >nul
title Facebook Group Crawler

echo.
echo  ===================================
echo   Facebook Group Crawler
echo  ===================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [LOI] Python chua duoc cai dat.
    echo  Tai tai: https://python.org
    pause & exit /b 1
)

echo  Kiem tra thu vien...
pip install -r requirements.txt -q

echo.
echo  Khoi dong server tai http://localhost:5000
echo  Nhan Ctrl+C de dung.
echo.

start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:19876"

python app.py
pause
