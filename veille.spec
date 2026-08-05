# -*- mode: python ; coding: utf-8 -*-
# Génère un .exe unique (voir build_exe.bat) à partir de webapp.py — le point
# d'entrée est la webapp Flask, pas main.py (qui est le CLI batch pour le
# Planificateur de tâches, sans intérêt pour un collègue qui utilise l'app
# depuis un navigateur).
from PyInstaller.utils.hooks import collect_data_files

# reportlab embarque ses métriques de polices standard (AFM) sous forme de
# fichiers data, pas de code Python : sans ça, la génération du PDF combiné
# planterait une fois figé en exe (fichiers introuvables dans le paquet).
datas = collect_data_files("reportlab")

a = Analysis(
    ["webapp.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StratIA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Fenêtre console conservée : fermer cette fenêtre arrête l'application
    # (même logique que start_veille.bat), et les erreurs y restent visibles
    # pour un rattrapage/support à distance plutôt qu'un plantage silencieux.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icône affichée dans l'Explorateur/la barre des tâches avant de lancer
    # l'exe (voir assets/icon.ico, même logo que le favicon/hero de la webapp).
    icon="assets/icon.ico",
)
