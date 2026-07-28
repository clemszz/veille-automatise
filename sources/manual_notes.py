"""Lecture des notes/PDF GreenUnivers déposés dans inbox_greenunivers/.

GreenUnivers est un contenu réservé aux abonnés dont les CGU interdisent les
requêtes automatisées vers le site. Le scraping/login automatisé est donc
exclu (voir README). Le PDF, lui, est exporté manuellement par la personne
abonnée (Ctrl+P depuis son propre accès) puis déposé ici — soit directement
dans ce dossier, soit via la mini app web (webapp.py). Le pipeline en
extrait le texte pour générer un résumé factuel ; le PDF original n'est
jamais republié/attaché dans la synthèse envoyée sur Teams (le webhook Teams
ne le permet de toute façon pas simplement), il sert uniquement de matière
première locale à la génération du résumé.

Types de fichiers reconnus par article :
- <slug>.pdf                : le PDF exporté (titre auto-deviné depuis le texte extrait)
- <slug>.meta.json (option) : {"title": "...", "url": "..."} pour forcer le titre/lien
- <slug>.txt / .md          : note texte libre (titre/lien/contexte à la main)
"""
import hashlib
import json
import re
import secrets
import shutil
from datetime import date, datetime
from pathlib import Path

from pypdf import PdfReader
from werkzeug.utils import secure_filename

from web_scrape import domain_label, fetch_url_text

TEXT_EXTENSIONS = {".txt", ".md"}

_DATE_LINE_RE = re.compile(r"^\d{1,2}\s+\S+\s+\d{4}$")
_URL_LINE_RE = re.compile(r"[\w.-]+\.(?:com|fr|net|org)/\S+")
_CREDIT_LINE_RE = re.compile(
    r"^(@|\(c\)|©)|(?i:unsplash|shutterstock|istock|getty|adobe stock)"
)


def _extract_pdf_text(path: Path, max_chars: int = 6000, max_pages: int | None = None) -> str:
    try:
        reader = PdfReader(str(path))
        pages = reader.pages[:max_pages] if max_pages else reader.pages
        parts = [page.extract_text() or "" for page in pages]
        return "\n".join(parts).strip()[:max_chars]
    except Exception as exc:  # noqa: BLE001 - un PDF corrompu ne doit pas bloquer tout le run
        return f"[Erreur d'extraction PDF ({exc})]"


def _load_meta(pdf_path: Path) -> dict:
    meta_path = pdf_path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def guess_title_from_pdf(path: Path) -> str | None:
    """Devine le vrai titre de l'article depuis le texte de la 1ère page,
    plutôt que depuis le nom de fichier exporté par le navigateur (qui
    tronque à 60 caractères, perd les accents/apostrophes et laisse des
    résidus type "nbsp"). Ces exports GreenUnivers ont toujours l'URL de
    l'article juste après le titre : on la repère et on remonte jusqu'au
    titre en sautant la ligne de date et l'éventuel crédit photo. Renvoie
    None si rien d'exploitable n'est trouvé (police du PDF sans accents
    correctement encodés, structure inattendue, etc.) pour laisser
    l'appelant retomber sur un autre indice de titre."""
    text = _extract_pdf_text(path, max_chars=2000, max_pages=1)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    url_idx = next((i for i, line in enumerate(lines) if _URL_LINE_RE.search(line)), None)
    if not url_idx:
        return None

    start = 1 if _DATE_LINE_RE.match(lines[0]) else 0
    while start < url_idx and (
        _CREDIT_LINE_RE.search(lines[start]) or len(lines[start].split()) <= 4
    ):
        start += 1

    title = re.sub(r"\s+", " ", " ".join(lines[start:url_idx])).strip()
    if not title or "�" in title:
        return None
    return title[:150]


def guess_title_fallback(text: str, fallback: str) -> str:
    """Pas de titre saisi à la main : on prend la première ligne un peu
    substantielle du texte extrait comme indice de titre. Ce n'est qu'un
    indice transmis à Mistral (qui rédige de toute façon son propre titre
    dans la synthèse finale), pas besoin d'une extraction parfaite."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 8:
            return line[:150]
    return fallback


def list_pending(inbox_dir: Path) -> list[dict]:
    """Aperçu léger des PDF/notes en attente pour affichage + suppression
    dans l'UI (webapp.py). Extraction limitée à la 1ère page d'un PDF
    (rapide, juste pour deviner un titre) — le texte complet n'est lu qu'au
    moment de la génération réelle, voir fetch()."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for f in sorted(inbox_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()
        if suffix == ".pdf":
            meta = _load_meta(f)
            title = meta.get("title") or guess_title_from_pdf(f) or guess_title_fallback(
                _extract_pdf_text(f, max_chars=1500, max_pages=1), fallback=f.stem
            )
        elif suffix in TEXT_EXTENSIONS:
            meta = _load_meta(f)
            title = meta.get("title") or f.stem
        else:
            continue
        items.append({
            "filename": f.name,
            "title": title,
            "size_kb": round(f.stat().st_size / 1024, 1),
        })
    return items


def delete_pending(inbox_dir: Path, filename: str) -> bool:
    """Supprime un fichier en attente (+ son .meta.json s'il existe). Refuse
    tout nom qui sortirait du dossier inbox (traversal) ou qui ne correspond
    pas exactement à un fichier existant dedans."""
    target = (inbox_dir / filename).resolve()
    if inbox_dir.resolve() not in target.parents:
        return False
    if not target.exists() or not target.is_file():
        return False
    meta_path = target.with_suffix(".meta.json")
    target.unlink()
    if meta_path.exists():
        meta_path.unlink()
    return True


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def pending_urls(inbox_dir: Path) -> set[str]:
    """URLs déjà en attente dans inbox_dir (notes .txt accompagnées d'un
    .meta.json portant une "url"), pour détecter un doublon avant d'ajouter
    un nouveau lien à scraper — voir add_web_note ci-dessous."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    urls = set()
    for f in inbox_dir.glob("*.meta.json"):
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        url = meta.get("url", "")
        if url:
            urls.add(_normalize_url(url))
    return urls


def pending_pdf_hashes(inbox_dir: Path) -> set[str]:
    """Empreinte (sha256) de chaque PDF déjà en attente dans inbox_dir, pour
    détecter un doublon de contenu avant d'accepter un nouveau dépôt — voir
    webapp._save_uploaded_pdfs. Indépendant du nom de fichier (deux exports
    du même article portent rarement le même nom)."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    hashes = set()
    for f in inbox_dir.iterdir():
        if f.is_file() and f.suffix.lower() == ".pdf":
            hashes.add(hashlib.sha256(f.read_bytes()).hexdigest())
    return hashes


def add_web_note(inbox_dir: Path, url: str = "", text: str = "") -> None:
    """Ajoute à la file d'attente (n'importe lequel des deux onglets, selon
    inbox_dir) un lien à scraper ou un texte collé à la main, pour les
    sources qui ne sont pas un PDF GreenUnivers (article en accès libre,
    post LinkedIn copié...). Écrit un .txt + un .meta.json, repris tel quel
    par fetch()/list_pending() ci-dessus ("source"/"url" surchargeables via
    meta, au lieu du "GreenUnivers" par défaut)."""
    url = url.strip()
    text = text.strip()
    if not url and not text:
        raise ValueError("Il faut au moins un lien ou un texte collé.")

    if url:
        if _normalize_url(url) in pending_urls(inbox_dir):
            raise ValueError("Ce lien est déjà dans la file d'attente.")
        scraped = fetch_url_text(url)
        content = scraped["text"]
        title = scraped["title"] or url
        source = domain_label(url)
    else:
        content = text
        title = guess_title_fallback(content, fallback="Texte collé")
        source = "Texte collé"

    if not content:
        raise ValueError("Aucun texte exploitable trouvé (page vide ou non accessible).")

    inbox_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = secure_filename(title)[:60] or "note"
    unique = secrets.token_hex(3)
    base_name = f"{stamp}_{slug}_{unique}"

    (inbox_dir / f"{base_name}.txt").write_text(content, encoding="utf-8")
    (inbox_dir / f"{base_name}.meta.json").write_text(
        json.dumps({"title": title, "url": url, "source": source}, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch(inbox_dir: Path) -> list[dict]:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    notes = []

    for f in sorted(inbox_dir.iterdir()):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()

        if suffix == ".pdf":
            meta = _load_meta(f)
            text = _extract_pdf_text(f)
            related = [f]
            meta_path = f.with_suffix(".meta.json")
            if meta_path.exists():
                related.append(meta_path)
            notes.append({
                "source": "GreenUnivers",
                "title": meta.get("title") or guess_title_from_pdf(f) or guess_title_fallback(text, fallback=f.stem),
                "url": meta.get("url", ""),
                "date": "",
                "excerpt": text[:1500],
                "content": text,
                "_files": related,
            })

        elif suffix in TEXT_EXTENSIONS:
            text = f.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                meta = _load_meta(f)
                related = [f]
                meta_path = f.with_suffix(".meta.json")
                if meta_path.exists():
                    related.append(meta_path)
                notes.append({
                    # Par défaut "GreenUnivers" (note tapée à la main pour
                    # l'onglet "Veille automatique", voir README section 3) ;
                    # surchargeable via .meta.json pour une source externe
                    # scrapée/collée dans l'onglet "Résumés PDF" (voir
                    # pdf_solo.add_web_note).
                    "source": meta.get("source") or "GreenUnivers",
                    "title": meta.get("title") or f.stem,
                    "url": meta.get("url", ""),
                    "date": "",
                    "excerpt": text[:1500],
                    "content": text[:1500],
                    "_files": related,
                })

    return notes


def archive_processed(
    notes: list[dict], run_date: date, archive_root: Path, subdir: str = "greenunivers"
) -> None:
    """Déplace les notes/PDF traités vers archive/<subdir>/<date>/ pour ne pas
    les repasser la semaine suivante, tout en gardant une trace. Le
    .meta.json qui accompagne un PDF (titre/lien forcés) n'a plus d'utilité
    une fois la veille générée : on le supprime plutôt que de l'archiver, pour
    ne garder que le PDF dans l'archive. `subdir` permet de séparer les PDF
    de la veille filtrée (in_scope/priorité) de ceux de l'onglet "Résumés PDF"
    (pas de filtrage, voir pdf_solo.py) sans dupliquer cette fonction."""
    dest_dir = archive_root / subdir / run_date.isoformat()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for note in notes:
        for src in note.get("_files", []):
            if not src.exists():
                continue
            if src.suffix.lower() == ".json":
                src.unlink()
            else:
                shutil.move(str(src), str(dest_dir / src.name))
