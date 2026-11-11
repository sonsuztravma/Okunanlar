@echo off
chcp 65001 > nul
title Sonsuz Okumalar - Kütüphaneyi Aç
echo ========================================================
echo    Sonsuz Okumalar - Sesli ve Akademik Kütüphane
echo ========================================================
echo.
echo Kütüphane varsayılan tarayıcınızda açılıyor...
echo.
start "" "%~dp0index.html"
exit
