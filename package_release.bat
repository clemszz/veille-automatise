@echo off
setlocal
cd /d "%~dp0"

call "%~dp0build_exe.bat"
if errorlevel 1 exit /b 1

set PKGDIR=dist_package\StratIA

if exist "%PKGDIR%" rmdir /s /q "%PKGDIR%"
mkdir "%PKGDIR%"

copy /y dist\StratIA.exe "%PKGDIR%\" >nul
copy /y .env "%PKGDIR%\" >nul
copy /y LISEZMOI.txt "%PKGDIR%\" >nul

echo.
echo Compression en zip...
powershell -NoProfile -Command "Compress-Archive -Path '%PKGDIR%\*' -DestinationPath 'dist_package\StratIA.zip' -Force"
if errorlevel 1 exit /b 1

echo.
echo ============================================================
echo Paquet pret : dist_package\StratIA.zip
echo.
echo ATTENTION : ce zip contient ta cle API Mistral en clair dans
echo le fichier .env (choix "cle partagee entre collegues"). Ne le
echo diffuse qu'aux personnes concernees (mail interne, partage
echo reseau interne) -- jamais sur un depot public ou un outil web
echo externe.
echo ============================================================
