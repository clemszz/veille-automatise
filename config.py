"""Configuration centrale de la veille hebdomadaire ENGIE Green."""
import os
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

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "5000"))

INBOX_GREENUNIVERS = BASE_DIR / "inbox_greenunivers"
ARCHIVE_DIR = BASE_DIR / "archive"

# Onglet "Résumés PDF" (webapp) : dépôt de PDF sans filtrage in_scope/priorité
# ni fusion avec Tecsol/PV Magazine — l'utilisateur choisit déjà les PDF en
# les déposant, seuls titre/résumé sont automatisés. Dossiers séparés de ceux
# de l'onglet "Veille automatique" pour ne pas mélanger les deux workflows.
INBOX_PDF_SOLO = BASE_DIR / "inbox_pdf_solo"
PDF_SOLO_ARCHIVE_SUBDIR = "pdf_solo"
PDF_SOLO_CACHE_PATH = BASE_DIR / ".cache" / "pdf_solo.json"

# Classeur de suivi manuel préexistant (un onglet, une ligne par actu classée
# par thème) : le dossier parent de veille-engie-green/, déposé par l'utilisateur.
TRACKER_XLSX_PATH = BASE_DIR.parent / "Veille_marché_ENR.xlsx"
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
