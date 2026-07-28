"""Cache locale des classifications Mistral, par article.

But : quand on régénère après avoir juste ajouté/retiré 1 PDF GreenUnivers,
on ne renvoie à Mistral QUE les articles jamais vus (nouveaux) — les autres
(déjà classés, y compris ceux jugés hors périmètre) sont relus depuis ce
cache local, sans appel API ni consommation de tokens.

Clé stable par article : l'URL pour les sources publiques (Tecsol/PV
Magazine), le nom de fichier pour les PDF/notes GreenUnivers.
"""
import json
from pathlib import Path

from config import BASE_DIR

CACHE_PATH = BASE_DIR / ".cache" / "articles.json"


def load(path: Path = CACHE_PATH) -> dict:
    """path : permet de réutiliser ce module pour un autre cache que celui de
    la veille hebdo (ex. PDF_SOLO_CACHE_PATH pour l'onglet "Résumés PDF",
    voir pdf_solo.py) sans dupliquer la logique de lecture/écriture."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - un cache corrompu ne doit pas bloquer la veille
        return {}


def save(cache: dict, path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def article_key(article: dict) -> str:
    url = article.get("url")
    if url:
        return url
    files = article.get("_files")
    if files:
        return f"greenunivers:{files[0].name}"
    return f"greenunivers:{article.get('title', '')}"
