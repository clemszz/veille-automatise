"""Intégration de la veille validée (texte final, potentiellement corrigé à
la main par l'utilisateur) dans le classeur Excel de suivi manuel préexistant
(Veille_marché_ENR.xlsx, onglet "Suivi veille") : une ligne par actualité,
rangée dans la bonne colonne thème + acteur/sujet, avec les liens sources.

Le texte est parsé au format produit par main._format_draft (bloc par actu :
"[THEME] Titre" / résumé / "Source : ..."), donc robuste à un simple
copier-coller même après édition manuelle du contenu (titres/résumés
modifiés, actus ajoutées/supprimées) tant que la structure des blocs est
conservée.
"""
import re
import shutil
from copy import copy
from datetime import date, datetime
from pathlib import Path

import openpyxl

from config import (
    TRACKER_COL_DATE,
    TRACKER_COL_THEMES,
    TRACKER_LIENS_COLUMNS,
    TRACKER_SHEET_NAME,
    TRACKER_THEME_COLUMNS,
    TRACKER_XLSX_PATH,
)
from summarize_mistral import classify_for_tracker

_ENTRY_HEADER_RE = re.compile(r"^\[(?P<theme>[^\]]+)\]\s*(?P<title>.+)$")
_URL_RE = re.compile(r"https?://\S+")


def parse_draft_text(text: str) -> list[dict]:
    """Repère chaque actu par sa ligne d'en-tête "[THEME] Titre" et la clôt à
    la ligne "Source : ...", indépendamment des lignes vides (il n'y en a pas
    forcément entre un titre de section "Priorité 1 :" et la première actu).
    Toute ligne hors de cette structure (en-tête "Veille hebdo — ...", titres
    de section, actu sans "Source :" en fin) est silencieusement ignorée
    plutôt que de faire planter l'intégration sur un texte édité à la main."""
    entries = []
    current = None  # {"theme_tag", "title", "summary_lines"}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = _ENTRY_HEADER_RE.match(line)
        if header:
            current = {
                "theme_tag": header.group("theme").strip(),
                "title": header.group("title").strip(),
                "summary_lines": [],
            }
            continue
        if line.lower().startswith("source") and current is not None:
            entries.append({
                "theme_tag": current["theme_tag"],
                "title": current["title"],
                "summary": " ".join(current["summary_lines"]).strip(),
                "source_line": line,
            })
            current = None
            continue
        if current is not None:
            current["summary_lines"].append(line)
    return entries


def extract_links(source_line: str) -> list[str]:
    return _URL_RE.findall(source_line)


LIENS_PLACEHOLDER = "intégrer lien pdf"


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def _copy_row_style(ws, template_row: int, target_row: int, max_col: int) -> None:
    """Reprend la mise en forme (police, surlignage, alignement, bordures,
    format de nombre) de template_row sur target_row, colonne par colonne,
    pour que les lignes ajoutées se fondent dans le classeur existant plutôt
    que d'apparaître avec le style par défaut d'openpyxl."""
    for col in range(1, max_col + 1):
        src = ws.cell(row=template_row, column=col)
        dst = ws.cell(row=target_row, column=col)
        dst.font = copy(src.font)
        dst.fill = copy(src.fill)
        dst.border = copy(src.border)
        dst.alignment = copy(src.alignment)
        dst.number_format = src.number_format
    src_height = ws.row_dimensions[template_row].height
    if src_height:
        ws.row_dimensions[target_row].height = src_height


def append_entries(
    entries: list[dict], run_date: date, excel_path: Path = TRACKER_XLSX_PATH
) -> list[dict]:
    """entries : dicts avec title/summary/source_line/links/excel_theme/
    acteur/sujet_divers (voir integrate_draft_text). Sauvegarde le classeur
    avant modification (fichier tenu à la main depuis des années, une
    corruption serait coûteuse à rattraper), ajoute une ligne par entrée à la
    fin de l'onglet (mise en forme reprise de la dernière ligne existante),
    puis sauvegarde. Retourne les lignes ajoutées pour affichage/vérification
    par l'utilisateur."""
    if not excel_path.exists():
        raise FileNotFoundError(f"Classeur introuvable : {excel_path}")

    _backup(excel_path)

    wb = openpyxl.load_workbook(excel_path)
    if TRACKER_SHEET_NAME not in wb.sheetnames:
        raise RuntimeError(f"Onglet '{TRACKER_SHEET_NAME}' introuvable dans {excel_path.name}")
    ws = wb[TRACKER_SHEET_NAME]

    template_row = ws.max_row
    max_col = ws.max_column
    added = []
    row = template_row + 1
    for e in entries:
        _copy_row_style(ws, template_row, row, max_col)

        acteur = e.get("acteur")
        sujet = e.get("sujet_divers")
        theme_label = acteur or (f"DIVERS/ {sujet}" if sujet else "DIVERS")
        ws.cell(row=row, column=TRACKER_COL_THEMES, value=theme_label)
        ws.cell(row=row, column=TRACKER_COL_DATE, value=run_date)

        theme_col = TRACKER_THEME_COLUMNS.get(e["excel_theme"], TRACKER_THEME_COLUMNS["DIVERS"])
        ws.cell(row=row, column=theme_col, value=f"{e['title']}\n{e['summary']}")

        links = e.get("links") or []
        if links:
            for link, col in zip(links, TRACKER_LIENS_COLUMNS):
                ws.cell(row=row, column=col, value=link)
        else:
            ws.cell(row=row, column=TRACKER_LIENS_COLUMNS[0], value=LIENS_PLACEHOLDER)

        added.append({
            "row": row, "theme_label": theme_label, "excel_theme": e["excel_theme"],
            "title": e["title"], "links": links,
        })
        row += 1

    wb.save(excel_path)
    return added


def integrate_draft_text(
    text: str, run_date: date, excel_path: Path = TRACKER_XLSX_PATH
) -> list[dict]:
    """Point d'entrée unique utilisé par la web app : parse le texte collé,
    classe chaque actu (thème Excel + acteur/sujet) via Mistral, puis ajoute
    les lignes au classeur. Renvoie la liste vide si rien d'exploitable n'a
    été trouvé dans le texte (au lieu de planter), pour laisser l'appelant
    afficher un message clair plutôt qu'une erreur serveur."""
    parsed = parse_draft_text(text)
    if not parsed:
        return []

    classifications = classify_for_tracker(
        [{"title": p["title"], "summary": p["summary"]} for p in parsed]
    )
    combined = [
        {**p, **c, "links": extract_links(p["source_line"])}
        for p, c in zip(parsed, classifications)
    ]
    return append_entries(combined, run_date, excel_path)
