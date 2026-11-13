@echo off
chcp 65001 > nul
title Sonsuz Okumalar - Kitap Yonetim Paneli
echo ========================================================
echo    Sonsuz Okumalar - Kitap Yonetim Paneli Baslatiliyor
echo ========================================================
echo.
echo Tarayiciniz aciliyor: http://localhost:5000
echo.
start "" "http://localhost:5000"
python yonetici.py
pause
