"""Orchestrateur de la veille hebdomadaire ENGIE Green.

Deux façons de l'utiliser :
- CLI (`python main.py` / `run_veille.bat`) : génère ET envoie/archive en une
  fois. Pratique pour une automatisation future (Planificateur de tâches).
- webapp.py : sépare génération (aperçu) et envoi (après validation
  manuelle) en réutilisant build_draft() / deliver_and_archive() ci-dessous.
"""
import sys
from dataclasses import dataclass, field
from datetime import date

import cache as article_cache
from cache import article_key
from config import ARCHIVE_DIR, INBOX_GREENUNIVERS, get_period
from filter_keywords import prefilter
from sources import manual_notes, pvmagazine, tecsol
from summarize_mistral import classify_articles, classify_greenunivers_notes, find_duplicate_groups


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    detail: str = ""  # message d'erreur si ok=False


@dataclass
class Draft:
    text: str
    period_label: str
    run_date: date
    notes: list[dict] = field(default_factory=list)  # notes/PDF GreenUnivers utilisés, pour archivage différé
    source_status: list[SourceStatus] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)  # forme structurée de `text`, pour l'édition dans la webapp

    @property
    def warnings(self) -> list[str]:
        """Messages à afficher bien en vue dans l'UI : source en échec ou
        source revenue vide (peut cacher un vrai problème, ex. anti-bot)."""
        out = []
        for s in self.source_status:
            if not s.ok:
                out.append(f"{s.name} : échec de récupération ({s.detail}) — source ignorée cette semaine.")
            elif s.count == 0:
                out.append(f"{s.name} : aucun article récupéré cette semaine (à vérifier si inhabituel).")
        return out


def build_draft(run_date: date | None = None, progress_cb=None) -> Draft:
    """Récupère les sources, filtre, appelle Mistral. Ne modifie rien de
    façon irréversible : les notes/PDF GreenUnivers ne sont PAS archivés ici
    (voir deliver_and_archive), pour pouvoir régénérer un aperçu sans perdre
    les fichiers déposés tant qu'ils n'ont pas été effectivement utilisés.

    `progress_cb`, s'il est fourni, est appelé avec (pct:int, message:str) à
    chaque grande étape — utilisé par la webapp pour afficher une vraie barre
    de progression pendant les 10-30 s de génération (voir webapp.py).

    Les notes/PDF GreenUnivers ne passent PAS par le même jugement de
    PÉRIMÈTRE que les sources scrapées (Tecsol/PV Magazine) : la sélection
    est déjà faite par l'utilisateur au moment du dépôt (voir README
    section 3), donc chaque PDF GreenUnivers est automatiquement
    in_scope=true. Mistral juge en revanche réellement leur PRIORITÉ P1/P2
    (voir classify_greenunivers_notes) : un PDF GreenUnivers n'est pas
    forcément P1, ex. un article sur les résultats financiers d'un groupe
    étranger reste P2."""
    def _progress(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)

    run_date = run_date or date.today()
    start, end = get_period(run_date)
    period_label = f"du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"
    print(f"[veille] Période couverte : {period_label}")

    raw_articles = []
    source_status = []
    fetchers = (("Tecsol Quotidien", tecsol.fetch), ("PV Magazine France", pvmagazine.fetch))
    for i, (label, fetch_fn) in enumerate(fetchers):
        _progress(5 + i * 15, f"Récupération {label}…")
        print(f"[veille] Récupération {label}...")
        try:
            batch = fetch_fn(start, end)
            print(f"[veille]   -> {len(batch)} articles publiés")
            raw_articles.extend(batch)
            source_status.append(SourceStatus(name=label, ok=True, count=len(batch)))
        except Exception as exc:  # noqa: BLE001 - une source en panne ne doit pas bloquer les autres
            print(f"[veille]   -> ÉCHEC ({exc}). On continue avec les autres sources.")
            source_status.append(SourceStatus(name=label, ok=False, detail=str(exc)))

    _progress(35, "Pré-filtrage par mots-clés…")
    candidates = prefilter(raw_articles)
    print(f"[veille] {len(candidates)} articles retenus après pré-filtre mots-clés")

    _progress(45, "Lecture des PDF/liens déposés…")
    print("[veille] Lecture des notes/PDF GreenUnivers (inbox_greenunivers/)...")
    notes = manual_notes.fetch(INBOX_GREENUNIVERS)
    print(f"[veille]   -> {len(notes)} élément(s) déposé(s)")

    for a in candidates:
        a["key"] = article_key(a)
    for a in notes:
        a["key"] = article_key(a)
    all_candidates = candidates + notes

    cache = article_cache.load()
    new_candidates = [a for a in candidates if a["key"] not in cache]
    new_notes = [a for a in notes if a["key"] not in cache]
    print(f"[veille] {len(all_candidates)} article(s) au total, "
          f"{len(new_candidates) + len(new_notes)} nouveau(x) jamais classé(s) "
          "(le reste vient du cache local, 0 token).")

    if new_candidates:
        _progress(55, f"Classement Mistral de {len(new_candidates)} article(s) scrapé(s)…")
        print(f"[veille] Appel à Mistral (classification) pour {len(new_candidates)} article(s) scrapé(s)...")
        cache.update(classify_articles(new_candidates))

    if new_notes:
        _progress(80, f"Classement Mistral de {len(new_notes)} PDF/lien(s)…")
        print(f"[veille] Appel à Mistral (priorité + résumé, pas de filtrage périmètre) "
              f"pour {len(new_notes)} PDF/note(s) GreenUnivers...")
        note_results = classify_greenunivers_notes(new_notes)
        for r in note_results.values():
            r["in_scope"] = True  # sélection déjà faite par l'utilisateur au dépôt
        cache.update(note_results)

    if new_candidates or new_notes:
        article_cache.save(cache)

    entries = []
    for a in all_candidates:
        verdict = cache.get(a["key"])
        if verdict and verdict.get("in_scope"):
            is_pdf_note = any(
                str(p).lower().endswith(".pdf") for p in a.get("_files", [])
            )
            if a["source"] == "GreenUnivers" and is_pdf_note:
                source_line = "Source : (GreenUnivers -voir pdf)"
            elif a["source"] == "GreenUnivers":
                source_line = "Source : GreenUnivers (accès abonné)"
            else:
                source_line = f"Source : {a['source']} — {a.get('url', '')}"
            entries.append({
                "priority": verdict.get("priority") or "P2",
                "theme": verdict.get("theme") or "AUTRE",
                "title": verdict.get("title") or a.get("title", ""),
                "summary": verdict.get("summary") or "",
                "source_line": source_line,
            })

    _progress(92, "Dédoublonnage…")
    entries = _merge_duplicates(entries)
    text = _format_draft(entries, end)
    _progress(100, "Terminé")

    return Draft(
        text=text, period_label=period_label, run_date=end, notes=notes,
        source_status=source_status, entries=entries,
    )


def _strip_source_prefix(source_line: str) -> str:
    prefix = "Source : "
    return source_line[len(prefix):] if source_line.startswith(prefix) else source_line


def _merge_duplicates(entries: list[dict]) -> list[dict]:
    """Fusionne les entrées qui parlent du même événement (plusieurs sources \
en parlent, ex. un article de presse + un post LinkedIn sur la même \
annonce) : garde un seul titre/résumé plutôt que de dupliquer l'info dans la \
synthèse, mais cite toutes les sources concernées. Détection via Mistral \
(voir find_duplicate_groups) — un échec de cet appel ne doit pas bloquer la \
génération, on retombe alors sur les entrées non fusionnées."""
    if len(entries) < 2:
        return entries
    try:
        groups = find_duplicate_groups(entries)
    except Exception as exc:  # noqa: BLE001 - la dédup est un bonus, pas bloquant
        print(f"[veille] Dédoublonnage ignoré (échec : {exc})")
        return entries

    grouped_indices = {i for group in groups for i in group}
    merged = []
    for group in groups:
        members = [entries[i] for i in group]
        # Priorité au membre P1 (plus visible) si le groupe est mixte, puis
        # au résumé le plus complet.
        canonical = dict(min(members, key=lambda e: (e["priority"] != "P1", -len(e["summary"]))))
        sources = dict.fromkeys(_strip_source_prefix(e["source_line"]) for e in members)
        canonical["source_line"] = "Source : " + " ; ".join(sources)
        merged.append((min(group), canonical))

    for i, e in enumerate(entries):
        if i not in grouped_indices:
            merged.append((i, e))

    merged.sort(key=lambda pair: pair[0])
    return [e for _, e in merged]


MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _format_date_fr(d: date) -> str:
    """Évite de dépendre de la locale système (strftime('%B') donnerait
    "July" au lieu de "juillet" si la locale n'est pas fr_FR)."""
    return f"{d.day} {MOIS_FR[d.month - 1]} {d.year}"


def _format_draft(entries: list[dict], run_date: date) -> str:
    """Assemble le texte final en Python (déterministe, texte brut garanti) \
à partir des classifications déjà décidées — plus besoin de faire écrire le \
document entier par Mistral à chaque régénération."""
    lines = [f"Veille hebdo — {_format_date_fr(run_date)}", ""]

    for priority, label in (("P1", "Priorité 1 :"), ("P2", "Priorité 2 :")):
        section = [e for e in entries if e["priority"] == priority]
        lines.append(label)
        if not section:
            lines.append("Aucune actualité notable cette semaine dans le périmètre.")
        for e in section:
            lines.append(f"[{e['theme']}] {e['title']}")
            lines.append(e["summary"])
            lines.append(e["source_line"])
            lines.append("")
        if section:
            lines.pop()  # retire la dernière ligne vide de la section
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def deliver_and_archive(draft: Draft) -> None:
    """Sauvegarde l'archive texte et déplace les notes/PDF GreenUnivers
    utilisés hors de l'inbox."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARCHIVE_DIR / f"veille_{draft.run_date.isoformat()}.txt"
    out_path.write_text(draft.text, encoding="utf-8")
    print(f"[veille] Synthèse enregistrée : {out_path}")

    manual_notes.archive_processed(draft.notes, draft.run_date, ARCHIVE_DIR)


def finalize_draft(draft: Draft, entries: list[dict]) -> str:
    """Reconstruit le texte final à partir d'`entries` (potentiellement édité
    dans la webapp : articles supprimés, priorités changées — voir
    webapp.py `/confirm`), puis archive comme deliver_and_archive. Retourne
    le texte final pour affichage/copie/intégration au classeur Excel."""
    draft.text = _format_draft(entries, draft.run_date)
    deliver_and_archive(draft)
    return draft.text


def run(run_date: date | None = None, dry_run: bool = False) -> str:
    draft = build_draft(run_date)
    for w in draft.warnings:
        print(f"[veille] ATTENTION : {w}")
    if dry_run:
        print("[veille] --dry-run : notes non archivées.")
        print("\n" + draft.text)
        return draft.text
    deliver_and_archive(draft)
    return draft.text


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    try:
        run(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - on veut logger toute erreur pour le Planificateur de tâches
        print(f"[veille] ERREUR : {exc}", file=sys.stderr)
        raise
