@echo off
title Sonsuz Okumalar - Kitap Duzenleyici ve Format Yoneticisi
echo ========================================================
echo   Sonsuz Okumalar - Kitap Duzenleyici Baslatiliyor
echo   (Google Drive, Telegram, Anna's Archive Duzenleme)
echo ========================================================
echo.

cd /d "%~dp0"

echo [*] Calibre ve Python ortami kontrol ediliyor...
where "C:\Program Files\Calibre2\ebook-convert.exe" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Calibre donusturucu algilandi.
) else (
    echo [i] Calibre varsayilan dizinde bulunamadi (Donusturme haric diger tum ozellikler calisir).
)

echo.
echo [*] Web Sunucusu baslatiliyor (Tarayici otomatik acilacaktir)...
echo.
python kitap_duzenleyici.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Sunucu baslatilamadi. Hata kodu: %ERRORLEVEL%
    pause
)
