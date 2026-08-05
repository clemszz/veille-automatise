"""Configuration centrale de la veille hebdomadaire ENGIE Green."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import truststore

# Fait utiliser à Python le magasin de certificats natif de Windows (celui
# que PowerShell/le navigateur utilisent déjà) au lieu du bundle certifi
# embarqué. Nécessaire derrière un proxy d'entreprise avec inspection TLS
# (certificat racine d'entreprise absent du bundle certifi). Doit être
# appelé avant toute requête HTTPS.
truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402

# Une fois figé en .exe par PyInstaller (voir build_exe.bat), le process
# décompresse le code dans un dossier temporaire à chaque lancement :
# Path(__file__).parent pointerait alors vers ce dossier jetable, pas vers le
# dossier où se trouve réellement l'exe — on perdrait le .env, les PDF
# déposés, l'archive et le cache à chaque redémarrage. sys.executable, lui,
# pointe toujours vers l'emplacement réel de l'exe (voir sys.frozen, positionné
# par PyInstaller). En mode développement (script .py lancé directement),
# sys.frozen n'existe pas : le comportement habituel est inchangé.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "5000"))

INBOX_GREENUNIVERS = BASE_DIR / "inbox_greenunivers"
# PDF de communication interne/officielle ENGIE (envoyés par le service Comm) :
# file d'attente séparée de GreenUnivers, toujours priorité P1 et thème parmi
# ENGIE/ENGIE R&B/ACTU GENERALE ENERGIE (voir summarize_mistral.classify_comm_notes,
# main.build_draft).
INBOX_COMM = BASE_DIR / "inbox_comm"
COMM_SOURCE_LABEL = "Communication ENGIE"
ARCHIVE_DIR = BASE_DIR / "archive"

# Classeur de suivi manuel préexistant (un onglet, une ligne par actu classée
# par thème). En développement : le dossier parent de stratia/, tel
# que déposé par l'utilisateur. Dans le paquet distribué à un collègue (voir
# build_exe.bat) : à côté de l'exe, dans le même dossier — plus simple à livrer
# qu'une arborescence à deux niveaux. Surchargeable via .env (TRACKER_XLSX_PATH)
# si un collègue préfère pointer vers un classeur situé ailleurs.
_default_tracker_dir = BASE_DIR if getattr(sys, "frozen", False) else BASE_DIR.parent
TRACKER_XLSX_PATH = Path(os.getenv("TRACKER_XLSX_PATH") or (_default_tracker_dir / "Veille_marché_ENR.xlsx"))
TRACKER_SHEET_NAME = "Suivi veille"
# Colonnes 1-indexées telles qu'observées dans le classeur existant.
TRACKER_COL_THEMES = 1       # acteur (ex. "EDF") ou "DIVERS/ <sujet>"
TRACKER_COL_DATE = 2
TRACKER_THEME_COLUMNS = {    # thème Excel -> n° de colonne
    "EOLIEN": 3,
    "AGRIVOLTAÏSME": 4,
    "SOLAIRE": 5,
    "BATTERIES / STOCKAGE": 6,
    "HYBRIDE": 7,
    "HYDROELECTRIQUE": 8,
    "PARTAGE DE LA VALEUR": 9,
    "REPOWERING": 10,
    "DIVERS": 11,
}
TRACKER_LIENS_COLUMNS = [12, 13, 14, 15, 16]  # 5 colonnes "LIENS" successives

# Mots-clés utilisés comme pré-filtre grossier avant l'appel Mistral (réduit le
# volume envoyé au modèle). Le filtrage fin (inclusion/exclusion/priorité) est
# fait par Mistral selon le brief complet dans summarize_mistral.py.
INCLUDE_KEYWORDS = [
    "éolien", "eolien", "éolienne", "offshore", "off-shore", "en mer",
    "stockage", "batterie", "bess",
    "hydroélectri", "hydroelectri", "hydraulique", "step", "pompage-turbinage",
    "barrage",
    "solaire", "photovolta", "centrale pv", "parc pv", "mwc", "gwc",
    "agrivolta", "agri-pv", "agripv",
]
EXCLUDE_HINT_KEYWORDS = [
    "ombrière", "ombriere", "petit pv", "petit solaire",
    "toiture résidentielle", "particulier", "autoconsommation individuelle",
]


def get_period(run_date: date | None = None) -> tuple[date, date]:
    """Période couverte : du vendredi précédent au jeudi (jour J), soit 7 jours
    se terminant le jour d'exécution (prévu chaque jeudi)."""
    run_date = run_date or date.today()
    start = run_date - timedelta(days=6)
    return start, run_date
