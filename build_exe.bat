@echo off
setlocal
cd /d "%~dp0"

echo Installation des dependances de build (PyInstaller)...
.venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt
if errorlevel 1 goto :error

echo.
echo Compilation de l'executable (peut prendre 1-2 minutes)...
.venv\Scripts\python.exe -m PyInstaller --noconfirm veille.spec
if errorlevel 1 goto :error

echo.
echo Build terminee : dist\StratIA.exe
exit /b 0

:error
echo.
echo ECHEC du build. Voir le detail des erreurs ci-dessus.
exit /b 1
