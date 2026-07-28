"""Onglet "Résumés PDF" de la webapp : dépôt de PDF en vrac, résumé + titre
générés automatiquement par Mistral, dans la même nomenclature que la veille
hebdomadaire ("[THEME] Titre" / résumé / "Source : ..."), SANS le filtrage
in_scope/priorité de la veille classique (voir main.build_draft) — ici
l'utilisateur garde la main sur la sélection des articles en choisissant quoi
déposer, Mistral se contente de rédiger, pas de juger.

Réutilise sources/manual_notes.py pour l'extraction PDF/gestion de la file
d'attente (mêmes fonctions que l'onglet "Veille automatique", juste pointées
vers un dossier de dépôt et un dossier d'archive différents pour ne pas
mélanger les deux workflows), et cache.py pour éviter de re-payer un appel
Mistral à chaque régénération de l'aperçu avant validation.
"""
import html
from datetime import date
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

import cache as article_cache
from cache import article_key
from config import ARCHIVE_DIR, INBOX_PDF_SOLO, PDF_SOLO_ARCHIVE_SUBDIR, PDF_SOLO_CACHE_PATH
from main import _format_date_fr
from sources import manual_notes
from summarize_mistral import summarize_solo


def list_pending() -> list[dict]:
    return manual_notes.list_pending(INBOX_PDF_SOLO)


def delete_pending(filename: str) -> bool:
    return manual_notes.delete_pending(INBOX_PDF_SOLO, filename)


def add_web_note(url: str = "", text: str = "") -> None:
    manual_notes.add_web_note(INBOX_PDF_SOLO, url=url, text=text)


def _source_line_for_note(note: dict) -> str:
    is_pdf = any(f.suffix.lower() == ".pdf" for f in note.get("_files", []))
    if note["source"] == "GreenUnivers" and is_pdf:
        return "Source : (GreenUnivers -voir pdf)"
    if note.get("url"):
        return f"Source : {note['source']} — {note['url']}"
    return f"Source : {note['source']} (texte collé, pas de lien)"


def generate_entries(progress_cb=None) -> list[dict]:
    """Lit les PDF/notes en attente, résume les nouveaux via Mistral (les
    autres sont relus depuis le cache local, pour pouvoir régénérer l'aperçu
    après ajout d'un PDF sans renvoyer les précédents à Mistral). Renvoie les
    entrées prêtes à afficher/copier/archiver, chacune gardant une référence
    à sa note d'origine (_note) pour l'archivage.

    `progress_cb`, s'il est fourni, est appelé avec (pct:int, message:str)
    pour la barre de progression de la webapp (voir webapp.py)."""
    def _progress(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)

    _progress(20, "Lecture des PDF/liens déposés…")
    notes = manual_notes.fetch(INBOX_PDF_SOLO)
    for n in notes:
        n["key"] = article_key(n)

    cache = article_cache.load(PDF_SOLO_CACHE_PATH)
    new_notes = [n for n in notes if n["key"] not in cache]
    if new_notes:
        _progress(55, f"Résumé Mistral de {len(new_notes)} document(s)…")
        results = summarize_solo(new_notes)
        cache.update(results)
        article_cache.save(cache, PDF_SOLO_CACHE_PATH)

    entries = []
    for n in notes:
        r = cache.get(n["key"])
        if not r:
            continue
        entries.append({
            "theme": r.get("theme") or "AUTRE",
            "title": r.get("title") or n.get("title", ""),
            "summary": r.get("summary") or "",
            "source_line": _source_line_for_note(n),
            "_note": n,
        })
    _progress(100, "Terminé")
    return entries


def format_entries_text(entries: list[dict]) -> str:
    """Assemble le texte au même format par bloc que main._format_draft
    ("[THEME] Titre" / résumé / "Source : ..."), directement compatible avec
    le parseur d'intégration Excel (tracker_excel.parse_draft_text) et avec un
    simple copier-coller vers Teams/mail."""
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"[{e['theme']}] {e['title']}")
        lines.append(e["summary"])
        lines.append(e["source_line"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def archive_processed(entries: list[dict], run_date: date | None = None) -> None:
    """Déplace les PDF/notes traités vers archive/pdf_solo/<date>/, séparé de
    archive/greenunivers/<date>/ (utilisé par l'onglet "Veille automatique")
    pour garder une trace distincte de ce qui est passé par quel workflow."""
    run_date = run_date or date.today()
    notes = [e["_note"] for e in entries]
    manual_notes.archive_processed(notes, run_date, ARCHIVE_DIR, subdir=PDF_SOLO_ARCHIVE_SUBDIR)


def _build_summary_pdf_bytes(entries: list[dict], run_date: date) -> bytes:
    """Génère, en mémoire, les 1-2 premières pages du PDF final : les résumés
    dans la même nomenclature que le texte ("[THEME] Titre" + résumé),
    mises en page avec reportlab (texte qui s'enchaîne naturellement sur
    plusieurs pages si besoin, pas de limite forcée à 1 page)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        "SoloHeader", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=15, spaceAfter=14,
    )
    title_style = ParagraphStyle(
        "SoloEntryTitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=3,
    )
    body_style = ParagraphStyle(
        "SoloEntryBody", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=13, spaceAfter=2,
    )

    story = [Paragraph(html.escape(f"Résumés PDF — {_format_date_fr(run_date)}"), header_style)]
    for e in entries:
        story.append(Paragraph(html.escape(f"[{e['theme']}] {e['title']}"), title_style))
        story.append(Paragraph(html.escape(e["summary"]), body_style))
    if not entries:
        story.append(Spacer(1, 1))

    doc.build(story)
    return buf.getvalue()


def _iter_source_pdf_paths(entries: list[dict]):
    """Ne renvoie que les fichiers PDF d'origine (pas les .meta.json, pas de
    fichier pour une note .txt/.md déposée à la main — il n'y a alors rien à
    compiler pour cette entrée, seul son résumé apparaît sur la 1ère page)."""
    for e in entries:
        for f in e["_note"].get("_files", []):
            if isinstance(f, Path) and f.suffix.lower() == ".pdf" and f.exists():
                yield f


def build_combined_pdf(entries: list[dict], run_date: date | None = None) -> bytes:
    """PDF unique : la page de résumés (voir _build_summary_pdf_bytes) suivie
    de tous les PDF sources déposés, compilés à la suite dans l'ordre
    d'affichage des entrées. Ne consomme/n'archive rien : à appeler autant de
    fois que voulu avant de cliquer "Valider"."""
    run_date = run_date or date.today()
    writer = PdfWriter()

    summary_bytes = _build_summary_pdf_bytes(entries, run_date)
    for page in PdfReader(BytesIO(summary_bytes)).pages:
        writer.add_page(page)

    for pdf_path in _iter_source_pdf_paths(entries):
        for page in PdfReader(str(pdf_path)).pages:
            writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
