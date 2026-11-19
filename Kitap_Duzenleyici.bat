@echo off
title Sonsuz Okumalar - Kitap Duzenleyici ve Format Yoneticisi
echo ========================================================
echo   Sonsuz Okumalar - Kitap Duzenleyici Baslatiliyor
echo   (Google Drive, Telegram, Anna's Archive Duzenleme)
echo ========================================================
echo.

cd /d "%~dp0"

echo [*] Web Sunucusu baslatiliyor: http://127.0.0.1:5050
echo (Tarayiciniz otomatik acilacaktir...)
echo.
python kitap_duzenleyici.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Sunucu baslatilamadi. Hata kodu: %ERRORLEVEL%
    pause
)
