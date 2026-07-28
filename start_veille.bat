@echo off
title Veille ENGIE Green - fermer cette fenetre pour arreter l'application
cd /d "%~dp0"
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:5000"
.venv\Scripts\python.exe webapp.py
