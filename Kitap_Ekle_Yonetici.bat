@echo off
title Sonsuz Okumalar - Kitap Yonetim Paneli
echo ========================================================
echo    Sonsuz Okumalar - Kitap Yonetim Paneli Baslatiliyor
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] GitHub kontrol ediliyor, online eklenen yeni kitaplar var mi?...
git fetch origin main --quiet >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    git pull origin main --quiet >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] GitHub ile senkronize edildi.
    ) else (
        echo [!] Otomatik birlestirme yapilamadi.
    )
) else (
    echo [i] Internet baglantisi yok. Cevrimdisi modda devam ediliyor.
)

echo.
echo [2/2] Yonetim paneli tarayicinizda aciliyor: http://localhost:5000
echo.
start "" "http://localhost:5000"
python yonetici.py
pause
