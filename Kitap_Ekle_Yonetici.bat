@echo off
chcp 65001 > nul
title Sonsuz Okumalar - Kitap Yönetim Paneli
echo ========================================================
echo    Sonsuz Okumalar - Kitap Yönetim Paneli Başlatılıyor
echo ========================================================
echo.
echo Tarayıcınız açılıyor: http://localhost:5000
echo.
start http://localhost:5000
python yonetici.py
pause
