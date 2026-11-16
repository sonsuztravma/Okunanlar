@echo off
title Sonsuz Okumalar - Kutuphane
echo ========================================================
echo    Sonsuz Okumalar - Sesli ve Akademik Kutuphane
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] GitHub kontrol ediliyor, yeni kitaplar var mi?...
git fetch origin main --quiet >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    git pull origin main --quiet >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Kutuphane GitHub ile senkronize edildi.
    ) else (
        echo [!] Otomatik birlestirme yapilamadi.
    )
) else (
    echo [i] Internet baglantisi yok. Cevrimdisi aciliyor.
)

echo.
echo [2/2] Kutuphane varsayilan tarayicinizda aciliyor...
start "" "%~dp0index.html"
exit
