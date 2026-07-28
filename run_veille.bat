@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
for /f "usebackq" %%d in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"`) do set LOGDATE=%%d
set LOGFILE=logs\run_%LOGDATE%.log
echo ==== %date% %time% ==== >> "%LOGFILE%"
python main.py >> "%LOGFILE%" 2>&1
endlocal
