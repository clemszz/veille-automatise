"""Mini app web locale pour la veille hebdomadaire ENGIE Green : dépôt de
PDF/liens GreenUnivers + scrape Tecsol/PV Magazine + classification par
Mistral + génération/édition/validation de la synthèse hebdomadaire.

Un bouton "Activer/désactiver le scraping automatique" (voir
main.build_draft, paramètre scraping_enabled) permet de couper Tecsol/PV
Magazine une semaine donnée : dans ce mode, seuls les PDF/liens déposés sont
traités, sans aucun jugement de périmètre ni de priorité (tout est inclus,
priorité par défaut modifiable dans l'aperçu) — pratique pour une semaine où
on ne veut traiter que du GreenUnivers sans bruit de scraping.

Lancer avec run_webapp.bat (ou `python webapp.py`). Accessible :
- Depuis ce PC : http://localhost:5000
- Depuis un autre appareil sur le même réseau (téléphone, autre PC) :
  http://<IP-locale-de-ce-PC>:5000  (trouver l'IP avec `ipconfig`)

Pas d'authentification : app de confiance sur réseau local uniquement.
"""
import hashlib
import html as html_module
import json
import pickle
import re
import secrets
import sys
import threading
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template_string, request, url_for
from werkzeug.utils import secure_filename

import combined_pdf
import tracker_excel
from config import BASE_DIR, INBOX_COMM, INBOX_GREENUNIVERS, WEBAPP_PORT, get_period
from main import Draft, _format_date_fr, build_draft, finalize_draft
from sources import manual_notes
from summarize_mistral import VEILLE_THEME_OPTIONS, _valid_veille_theme

# Logo StratIA (badge degrade vert/teal + "S", voir assets/logo.png) encode
# en base64 pour rester dans ce fichier unique, sans route/fichier statique
# separe -- utilise a la fois comme favicon et comme icone dans le hero
# (voir PAGE plus bas).
_LOGO_B64 = "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"

app = Flask(__name__)

# État en mémoire du process (app mono-utilisateur locale, pas besoin de
# session/DB : un seul aperçu "en attente" à la fois).
_pending_draft: Draft | None = None
_scraping_enabled: bool = True

# Un aperçu/des PDF encore en attente au moment où l'app démarre viennent
# forcément d'une session précédente jamais validée/nettoyée (voir
# _load_pending) : on les affiche repliés derrière un petit bandeau
# "Afficher / Supprimer définitivement" plutôt que tout ré-étaler comme si de
# rien n'était (voir _render, /discard-draft, /discard-pending-files). Un
# élément ajouté PENDANT que ce process tourne (génération, dépôt de PDF)
# n'est lui jamais considéré "laissé de côté" : il reste affiché normalement.
_draft_from_previous_session: bool = False
_startup_pending_filenames: set[str] = set()
_startup_pending_comm_filenames: set[str] = set()

# Si l'intégration Excel échoue à la validation (cas le plus probable : le
# classeur est ouvert dans Excel au même moment), la synthèse est déjà
# enregistrée/archivée mais pas encore dans le classeur — on garde les
# entrées en mémoire pour permettre un nouvel essai en un clic (voir
# _integrate_to_excel, /retry-excel-integration) sans tout regénérer.
_last_failed_excel: dict | None = None
_last_final_text: str | None = None

# Persistance sur disque : sans ça, un redémarrage de l'app (plantage,
# fermeture de la fenêtre, redéploiement) perd l'aperçu généré et le réglage
# du bouton scraping. On sérialise donc l'aperçu (pickle : Draft = dataclass,
# entries = dicts, notes = chemins) et le réglage du toggle pour les
# recharger au démarrage. Fichiers locaux, app de confiance.
_PENDING_DIR = BASE_DIR / ".cache"
_PENDING_DRAFT_PATH = _PENDING_DIR / "pending_draft.pkl"
_SCRAPING_ENABLED_PATH = _PENDING_DIR / "scraping_enabled.txt"

# Génération lancée dans un thread pour pouvoir suivre l'avancement en direct
# (barre de progression), au lieu d'un long POST bloquant. Un seul job à la
# fois (app mono-utilisateur). _gen_job = {state, pct, msg, error}.
_gen_job: dict | None = None
_gen_lock = threading.Lock()


def _persist_draft() -> None:
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    if _pending_draft is None:
        _PENDING_DRAFT_PATH.unlink(missing_ok=True)
    else:
        _PENDING_DRAFT_PATH.write_bytes(pickle.dumps(_pending_draft))


def _save_scraping_enabled() -> None:
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    _SCRAPING_ENABLED_PATH.write_text("1" if _scraping_enabled else "0", encoding="utf-8")


def _load_pending() -> None:
    """Recharge au démarrage l'aperçu et le réglage du scraping
    éventuellement sauvegardés avant un redémarrage. Toute erreur de lecture
    (format changé, fichier corrompu) est ignorée : on repart alors d'un état
    par défaut, sans planter. Marque aussi tout aperçu/PDF déjà présent à cet
    instant comme "hérité d'une session précédente" (voir
    _draft_from_previous_session / _startup_pending_filenames ci-dessus)."""
    global _pending_draft, _scraping_enabled, _draft_from_previous_session
    global _startup_pending_filenames, _startup_pending_comm_filenames
    try:
        if _PENDING_DRAFT_PATH.exists():
            _pending_draft = pickle.loads(_PENDING_DRAFT_PATH.read_bytes())
            if _pending_draft is not None:
                # Filet de sécurité : un aperçu resté en attente depuis avant
                # l'introduction de la liste fermée des thèmes (ou une
                # future liste modifiée) peut contenir un thème libre qui ne
                # correspondrait plus à aucune option du filtre/sélecteur —
                # le filtre par thème de l'aperçu semblerait alors "ne rien
                # afficher" pour cet aperçu. On renormalise à la relecture.
                for e in _pending_draft.entries:
                    e["theme"] = _valid_veille_theme(e.get("theme"))
            _draft_from_previous_session = _pending_draft is not None
    except Exception:  # noqa: BLE001
        _pending_draft = None
        _draft_from_previous_session = False
    try:
        if _SCRAPING_ENABLED_PATH.exists():
            _scraping_enabled = _SCRAPING_ENABLED_PATH.read_text(encoding="utf-8").strip() != "0"
    except Exception:  # noqa: BLE001
        _scraping_enabled = True
    _startup_pending_filenames = {f["filename"] for f in manual_notes.list_pending(INBOX_GREENUNIVERS)}
    _startup_pending_comm_filenames = {f["filename"] for f in manual_notes.list_pending(INBOX_COMM)}


@app.after_request
def _no_cache(response):
    """Interdit toute mise en cache navigateur de la page : sans ça, un
    rechargement classique peut réafficher une version HTML/JS obsolète
    depuis le cache disque sans même recontacter le serveur (vécu : bouton
    "Envoyer sur Teams" et onglet "Résumés PDF" qui semblaient ne jamais se
    mettre à jour alors que le code servi était déjà correct)."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

PAGE = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StratIA</title>
<link rel="icon" type="image/png" href="data:image/png;base64,{{ logo_b64 }}">
<script>
// Applique le thème clair/sombre choisi manuellement (voir toggleTheme() plus
// bas) AVANT le premier rendu, pour éviter un flash du mauvais thème au
// chargement. Sans préférence enregistrée, le thème système s'applique tout
// seul via la media query CSS (prefers-color-scheme), pas besoin d'attribut.
(function () {
  try {
    var saved = localStorage.getItem('veille-theme');
    if (saved === 'dark' || saved === 'light') {
      document.documentElement.setAttribute('data-theme', saved);
    }
  } catch (e) {}
})();
</script>
<style>
  :root {
    --green: #16794f; --green-dark: #0f5c3b; --teal: #1aa17f;
    --accent: var(--green-dark);
    --green-light: #e8f4ee; --green-tint: #f2f8f5;
    --bg: #f4f7f5; --card: #ffffff; --border: #e4e9e6;
    --text: #1b2620; --muted: #66716a;
    --ok-bg: #e7f7ee; --ok-text: #146c43; --warn-bg: #fff6e0; --warn-text: #8a5a00;
    --err-bg: #fdecec; --err-text: #a3231f;
    --ring: rgba(22,121,79,0.4);
    --shadow-sm: 0 1px 2px rgba(16,60,40,0.05);
    --shadow-md: 0 6px 20px rgba(16,60,40,0.09);
    --radius: 12px;
    --overlay-bg: rgba(244,247,245,0.82);
    --toast-bg: var(--text); --toast-text: #fff;
    --btn-secondary-bg: #eef2f0; --btn-secondary-hover: #e2e8e5;
    --panel-bg: #fbfcfb;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 800px; margin: 0 auto; padding: 0 1rem 3rem;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
  }

  .hero {
    background: linear-gradient(120deg, var(--green-dark), var(--green) 55%, var(--teal));
    color: #fff; margin: 0 -1rem 1.6rem; padding: 1.6rem 1.5rem 1.7rem;
    border-radius: 0 0 20px 20px; box-shadow: var(--shadow-md);
    display: flex; align-items: center; gap: 0.9rem;
  }
  .hero-mark {
    width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
    overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  }
  .hero-mark img { width: 100%; height: 100%; display: block; }
  .hero-txt h1 { font-size: 1.35rem; margin: 0; font-weight: 700; letter-spacing: -0.01em; }
  .hero-txt p { margin: 0.15rem 0 0; font-size: 0.85rem; opacity: 0.9; }

  .scrape-toggle {
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 0.9rem 1.2rem; margin-bottom: 1.1rem; box-shadow: var(--shadow-sm);
    animation: cardIn 0.4s ease both;
  }
  .scrape-toggle strong { display: block; font-size: 0.92rem; }
  .scrape-toggle .hint { display: block; margin: 0.15rem 0 0; }
  .switch {
    margin: 0; padding: 0; width: 46px; height: 26px; border-radius: 999px; flex-shrink: 0;
    background: var(--border); border: none; position: relative; cursor: pointer;
    transition: background 0.2s;
  }
  .switch:hover { background: var(--border); transform: none; box-shadow: none; }
  .switch.on { background: var(--green); }
  .switch.on:hover { background: var(--green-dark); }
  .switch-thumb {
    position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%;
    background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.25); transition: transform 0.2s;
  }
  .switch.on .switch-thumb { transform: translateX(20px); }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1.3rem 1.4rem; margin-bottom: 1.1rem; box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s, transform 0.2s; animation: cardIn 0.4s ease both;
  }
  .card:hover { box-shadow: var(--shadow-md); }
  .card.highlight { border-color: var(--green); background: linear-gradient(var(--green-tint), var(--card) 60%); }
  .card:nth-child(2) { animation-delay: 0.02s; }
  .card:nth-child(3) { animation-delay: 0.07s; }
  .card:nth-child(4) { animation-delay: 0.12s; }
  .card:nth-child(5) { animation-delay: 0.17s; }
  .card:nth-child(6) { animation-delay: 0.22s; }
  .card h2 { font-size: 1.02rem; margin: 0 0 0.95rem; display: flex; align-items: center; gap: 0.55rem; }
  .step-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.6rem; height: 1.6rem; border-radius: 50%;
    background: linear-gradient(135deg, var(--green), var(--teal));
    color: white; font-size: 0.82rem; font-weight: 700; flex-shrink: 0;
  }
  .count-badge {
    margin-left: auto; background: var(--green-light); color: var(--accent);
    font-size: 0.72rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 999px;
  }
  label { display: block; margin-bottom: 0.4rem; font-weight: 600; font-size: 0.9rem; }

  .input, .textarea {
    width: 100%; padding: 0.65rem 0.75rem; border: 1px solid var(--border); border-radius: 9px;
    font-family: inherit; font-size: 0.9rem; background: var(--card); color: var(--text);
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input:focus, .textarea:focus { outline: none; border-color: var(--green); box-shadow: 0 0 0 3px var(--ring); }
  .textarea { resize: vertical; min-height: 5.5rem; }

  .dropzone {
    display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
    padding: 1.6rem 1rem; border: 1.5px dashed var(--border); border-radius: var(--radius);
    background: var(--green-tint); cursor: pointer; text-align: center; margin-bottom: 0;
    transition: border-color 0.15s, background 0.15s, transform 0.1s;
  }
  .dropzone:hover { border-color: var(--green); background: var(--green-light); }
  .dropzone.dragover { border-color: var(--green); background: var(--green-light); transform: scale(1.01); }
  .dropzone svg { width: 30px; height: 30px; color: var(--green); opacity: 0.85; }
  .dz-title { font-weight: 600; font-size: 0.9rem; color: var(--text); }
  .dz-hint { font-size: 0.8rem; color: var(--muted); }
  .dz-selected { font-size: 0.83rem; color: var(--accent); font-weight: 600; margin-top: 0.55rem; }
  .dz-selected:empty { display: none; }

  input[type=submit], button, .btn {
    margin-top: 1rem; padding: 0.65rem 1.25rem; font-weight: 600; cursor: pointer;
    border: none; border-radius: 9px; background: var(--green); color: white; font-size: 0.9rem;
    transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
  }
  input[type=submit]:hover, button:hover, .btn:hover { background: var(--green-dark); transform: translateY(-1px); box-shadow: var(--shadow-md); }
  input[type=submit]:active, button:active, .btn:active { transform: translateY(0); box-shadow: none; }
  button.secondary { background: var(--btn-secondary-bg); color: var(--text); }
  button.secondary:hover { background: var(--btn-secondary-hover); color: var(--accent); }
  button.ghost { background: transparent; color: var(--accent); border: 1.5px solid var(--border); }
  button.ghost:hover { background: var(--green-tint); border-color: var(--green); }
  button.danger { background: var(--err-bg); color: var(--err-text); }
  button.danger:hover { background: #fbd7d5; color: var(--err-text); transform: none; box-shadow: none; }
  button:disabled { opacity: 0.6; cursor: default; transform: none; box-shadow: none; }
  :focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  .hint { color: var(--muted); font-size: 0.85rem; margin: 0.6rem 0 0; }
  .msg {
    padding: 0.85rem 1rem; border-radius: 9px; margin-bottom: 1rem; font-size: 0.9rem;
    display: flex; gap: 0.55rem; align-items: flex-start; animation: slideDown 0.3s ease;
  }
  .msg::before { font-weight: 700; flex-shrink: 0; }
  .ok { background: var(--ok-bg); color: var(--ok-text); }
  .ok::before { content: "\\2713"; }
  .err { background: var(--err-bg); color: var(--err-text); }
  .err::before { content: "\\26A0"; }
  .warn-box {
    background: var(--warn-bg); color: var(--warn-text); border-radius: 9px;
    padding: 0.8rem 1rem; margin-bottom: 1rem; font-size: 0.88rem; animation: slideDown 0.3s ease;
  }
  .warn-box ul { margin: 0.3rem 0 0; padding-left: 1.1rem; }
  .hidden-block { display: none; }
  .leftover-banner {
    display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap;
    background: var(--warn-bg); color: var(--warn-text); border-radius: 9px;
    padding: 0.7rem 0.9rem; margin: 0.9rem 0 0; font-size: 0.85rem; animation: slideDown 0.3s ease;
  }
  .leftover-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .leftover-actions button { margin: 0; padding: 0.4rem 0.85rem; font-size: 0.82rem; }
  .source-status { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
  .pill {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.7rem;
    border-radius: 999px; font-size: 0.8rem; font-weight: 600;
  }
  .pill.ok { background: var(--ok-bg); color: var(--ok-text); }
  .pill.warn { background: var(--warn-bg); color: var(--warn-text); }
  .pill.err { background: var(--err-bg); color: var(--err-text); }
  .draft-view {
    width: 100%; max-height: 480px; overflow-y: auto; box-sizing: border-box;
    font-size: 0.92rem; line-height: 1.5; padding: 0.9rem 1rem; border-radius: 9px;
    border: 1px solid var(--border); background: var(--panel-bg);
  }
  .draft-view .draft-h { font-weight: 700; font-size: 1rem; color: var(--accent); margin: 0 0 0.8rem; }
  .draft-view .draft-section {
    font-weight: 700; text-transform: uppercase; font-size: 0.78rem; letter-spacing: 0.03em;
    color: var(--muted); margin: 1.1rem 0 0.5rem; border-top: 1px solid var(--border); padding-top: 0.8rem;
  }
  .draft-view .draft-section:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
  .draft-view .art-title { margin: 0.9rem 0 0.15rem; }
  .draft-view .art-title:first-child { margin-top: 0; }
  .draft-view .art-body { margin: 0 0 0.15rem; color: var(--text); }
  .draft-view .art-body:has(+ .art-title), .draft-view .art-body:last-child { margin-bottom: 0; }
  .actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.9rem; }
  .entry-row { display: flex; gap: 0.9rem; padding: 0.95rem 0; border-top: 1px solid var(--border); transition: opacity 0.2s; cursor: grab; }
  .entry-row input, .entry-row textarea, .entry-row select { cursor: auto; }
  .entry-row:active { cursor: grabbing; }
  .entry-row:first-child { border-top: none; padding-top: 0; }
  .entry-row.excluded { opacity: 0.5; }
  .entry-row.excluded .title-edit { text-decoration: line-through; }
  .entry-controls {
    display: flex; flex-direction: column; gap: 0.4rem; align-items: flex-start;
    flex-shrink: 0; width: 92px;
  }
  .entry-controls label {
    display: flex; align-items: center; gap: 0.35rem; font-weight: 500;
    font-size: 0.82rem; margin: 0;
  }
  .priority-select {
    padding: 0.3rem 0.4rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.82rem;
    background: var(--card); cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .priority-select.p1 { border-color: var(--green); color: var(--accent); font-weight: 700; }
  .priority-select.p2 { color: var(--muted); }
  .entry-body { flex: 1; min-width: 0; }
  .entry-body .art-title { margin: 0 0 0.2rem; }
  .entry-body .art-body { margin: 0 0 0.2rem; }
  .file-list { list-style: none; margin: 0.9rem 0 0; padding: 0; }
  .file-list li {
    display: flex; align-items: center; gap: 0.6rem; padding: 0.55rem 0;
    border-top: 1px solid var(--border); font-size: 0.87rem; animation: slideDown 0.25s ease;
  }
  .file-list li:first-child { border-top: none; }
  .file-list .fname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-list .fsize { color: var(--muted); font-size: 0.8rem; flex-shrink: 0; }
  .file-list button {
    margin: 0; padding: 0.3rem 0.6rem; font-size: 0.78rem; font-weight: 600;
    background: var(--err-bg); color: var(--err-text); flex-shrink: 0;
  }
  .file-list button:hover { background: #fbd7d5; color: var(--err-text); transform: none; box-shadow: none; }

  .apercu-toolbar {
    display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem 0.9rem;
    margin: 0 0 0.7rem; padding: 0.6rem 0.8rem; background: var(--green-tint);
    border: 1px solid var(--border); border-radius: 9px; font-size: 0.85rem;
  }
  .apercu-counter { font-weight: 700; color: var(--accent); margin-right: auto; }
  .apercu-toolbar select { padding: 0.3rem 0.5rem; border: 1px solid var(--border); border-radius: 6px; background: var(--card); color: var(--text); font-size: 0.83rem; }
  .apercu-toolbar label { display: flex; align-items: center; gap: 0.3rem; font-weight: 500; margin: 0; font-size: 0.83rem; }
  .entry-row.filtered-out { display: none; }
  .entry-row.dragging {
    opacity: 0.7; background: var(--card); box-shadow: var(--shadow-md);
    border-radius: 8px; position: relative; z-index: 5; transform: scale(1.01);
  }
  .entry-row.drop-before { box-shadow: inset 0 3px 0 0 var(--green); }
  .entry-row.drop-after { box-shadow: inset 0 -3px 0 0 var(--green); }
  @keyframes justMoved { from { background: var(--green-light); } to { background: transparent; } }
  .entry-row.just-moved { animation: justMoved 0.7s ease; }
  .drag-handle {
    cursor: grab; color: var(--muted); font-size: 1rem; line-height: 1; flex-shrink: 0;
    padding: 0.2rem 0.15rem; align-self: flex-start; margin-top: 0.15rem; user-select: none;
    touch-action: none;
  }
  .drag-handle:hover { color: var(--accent); }
  .entry-row.dragging .drag-handle { cursor: grabbing; }
  .theme-select {
    display: inline-block; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em;
    color: var(--accent); background: var(--green-light); padding: 0.12rem 0.4rem;
    border-radius: 5px; margin-right: 0.4rem; vertical-align: middle; border: none; cursor: pointer;
  }
  .title-edit {
    display: inline-block; width: calc(100% - 4.6rem); max-width: 100%;
    border: 1px solid transparent; background: transparent; padding: 0.15rem 0.35rem;
    font-weight: 700; font-size: 0.98rem; font-family: inherit; color: var(--text);
    border-radius: 6px; vertical-align: middle; transition: border-color 0.15s, background 0.15s;
  }
  .title-edit:hover { border-color: var(--border); }
  .title-edit:focus { outline: none; border-color: var(--green); background: var(--card); box-shadow: 0 0 0 3px var(--ring); }
  .summary-edit {
    display: block; width: 100%; border: 1px solid transparent; background: transparent;
    padding: 0.2rem 0.35rem; font-family: inherit; font-size: 0.92rem; color: var(--text);
    border-radius: 6px; resize: none; overflow: hidden; line-height: 1.45; margin: 0.15rem 0 0.15rem -0.35rem;
    transition: border-color 0.15s, background 0.15s;
  }
  .summary-edit:hover { border-color: var(--border); }
  .summary-edit:focus { outline: none; border-color: var(--green); background: var(--card); box-shadow: 0 0 0 3px var(--ring); }

  .progress-wrap { margin-top: 1rem; }
  .progress-track {
    width: 100%; height: 8px; border-radius: 999px; background: var(--border); overflow: hidden;
  }
  .progress-bar {
    height: 100%; width: 0%; border-radius: 999px;
    background: linear-gradient(90deg, var(--green), var(--teal));
    transition: width 0.35s ease;
  }
  .progress-label { font-size: 0.83rem; color: var(--muted); margin: 0.45rem 0 0; }

  #overlay {
    display: none; position: fixed; inset: 0; background: var(--overlay-bg);
    z-index: 10; align-items: center; justify-content: center; backdrop-filter: blur(3px);
  }
  #overlay.active { display: flex; animation: fadeIn 0.2s ease; }
  .overlay-box {
    background: var(--card); padding: 1.7rem 2.1rem; border-radius: 14px; box-shadow: var(--shadow-md);
    display: flex; flex-direction: column; align-items: center; gap: 1rem; text-align: center;
  }
  .spinner {
    width: 42px; height: 42px; border: 4px solid var(--green-light); border-top-color: var(--green);
    border-radius: 50%; animation: spin 0.8s linear infinite;
  }
  .overlay-box p { color: var(--muted); font-size: 0.9rem; margin: 0; max-width: 18rem; }
  #toast {
    position: fixed; left: 50%; bottom: 1.6rem; transform: translateX(-50%) translateY(1rem);
    background: var(--toast-bg); color: var(--toast-text); padding: 0.75rem 1.15rem; border-radius: 10px;
    font-size: 0.88rem; font-weight: 500; box-shadow: var(--shadow-md); opacity: 0;
    pointer-events: none; transition: opacity 0.25s, transform 0.25s; z-index: 50; max-width: 90%;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes cardIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }
  .tab-panel { animation: fadeIn 0.28s ease; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
  }

  /* --green-dark reste un vert profond (dégradés/fonds de bouton) ; le
     texte/accent sur fond sombre utilise --accent, plus clair, pour le
     contraste — voir usages séparés plus haut dans la feuille de style.
     Le thème sombre s'applique automatiquement selon les préférences
     système (media query), ou de force si l'utilisateur a cliqué sur le
     bouton clair/sombre (attribut data-theme posé sur <html>, voir
     toggleTheme() — a plus de spécificité donc gagne sur la media query). */
  @media (prefers-color-scheme: dark) {
    :root {
      --green: #2fa671; --green-dark: #0c4a30; --teal: #2bbf9a;
      --accent: #7fd9ae;
      --green-light: #163a2c; --green-tint: #142a21;
      --bg: #101613; --card: #181f1b; --border: #2a332d;
      --text: #e7ede9; --muted: #9aa69e;
      --ok-bg: #123626; --ok-text: #6fdba3; --warn-bg: #3a2f0e; --warn-text: #f0c766;
      --err-bg: #3a1616; --err-text: #ff9b93;
      --ring: rgba(47,166,113,0.35);
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.25);
      --shadow-md: 0 10px 26px rgba(0,0,0,0.4);
      --overlay-bg: rgba(16,22,19,0.86);
      --toast-bg: #2a332d; --toast-text: var(--text);
      --btn-secondary-bg: #232b25; --btn-secondary-hover: #2b342d;
      --panel-bg: #12180f;
    }
  }
  :root[data-theme="dark"] {
    --green: #2fa671; --green-dark: #0c4a30; --teal: #2bbf9a;
    --accent: #7fd9ae;
    --green-light: #163a2c; --green-tint: #142a21;
    --bg: #101613; --card: #181f1b; --border: #2a332d;
    --text: #e7ede9; --muted: #9aa69e;
    --ok-bg: #123626; --ok-text: #6fdba3; --warn-bg: #3a2f0e; --warn-text: #f0c766;
    --err-bg: #3a1616; --err-text: #ff9b93;
    --ring: rgba(47,166,113,0.35);
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.25);
    --shadow-md: 0 10px 26px rgba(0,0,0,0.4);
    --overlay-bg: rgba(16,22,19,0.86);
    --toast-bg: #2a332d; --toast-text: var(--text);
    --btn-secondary-bg: #232b25; --btn-secondary-hover: #2b342d;
    --panel-bg: #12180f;
  }
  :root[data-theme="light"] {
    --green: #16794f; --green-dark: #0f5c3b; --teal: #1aa17f;
    --accent: var(--green-dark);
    --green-light: #e8f4ee; --green-tint: #f2f8f5;
    --bg: #f4f7f5; --card: #ffffff; --border: #e4e9e6;
    --text: #1b2620; --muted: #66716a;
    --ok-bg: #e7f7ee; --ok-text: #146c43; --warn-bg: #fff6e0; --warn-text: #8a5a00;
    --err-bg: #fdecec; --err-text: #a3231f;
    --ring: rgba(22,121,79,0.4);
    --shadow-sm: 0 1px 2px rgba(16,60,40,0.05);
    --shadow-md: 0 6px 20px rgba(16,60,40,0.09);
    --overlay-bg: rgba(244,247,245,0.82);
    --toast-bg: var(--text); --toast-text: #fff;
    --btn-secondary-bg: #eef2f0; --btn-secondary-hover: #e2e8e5;
    --panel-bg: #fbfcfb;
  }
  .theme-toggle {
    margin: 0 0 0 auto; padding: 0; width: 38px; height: 38px; border-radius: 10px;
    background: rgba(255,255,255,0.16); border: none; color: #fff;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
    flex-shrink: 0; transition: background 0.15s, transform 0.1s;
  }
  .theme-toggle:hover { background: rgba(255,255,255,0.28); transform: translateY(-1px); box-shadow: none; }
  .theme-toggle svg { width: 19px; height: 19px; }
  .app-footer {
    text-align: center; color: var(--muted); font-size: 0.78rem;
    margin: 1.6rem 0 0.4rem; padding-top: 1rem; border-top: 1px solid var(--border);
  }
</style>
</head>
<body>
<div id="overlay">
  <div class="overlay-box">
    <div class="spinner" id="overlaySpinner"></div>
    <div class="progress-wrap" id="overlayProgressWrap" style="display:none; width:220px;">
      <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
    </div>
    <p id="overlayText">Récupération des sources et génération en cours… 10 à 30 secondes.</p>
  </div>
</div>
<div id="toast" role="status" aria-live="polite"></div>

<div class="hero">
  <div class="hero-mark">
    <img src="data:image/png;base64,{{ logo_b64 }}" alt="StratIA" width="44" height="44">
  </div>
  <div class="hero-txt">
    <h1>StratIA</h1>
    <p>Veille hebdo ENGIE Green · Solaire au sol · Éolien · Stockage BESS · Hydro-STEP</p>
  </div>
  <button type="button" id="themeToggle" class="theme-toggle" onclick="toggleTheme()" title="Basculer thème clair/sombre" aria-label="Basculer thème clair/sombre">
    <svg id="themeIconSun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="4.2"/>
      <path d="M12 2.5v2.4M12 19.1v2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7"/>
    </svg>
    <svg id="themeIconMoon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none">
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/>
    </svg>
  </button>
</div>

{% if message %}<div class="msg {{ 'ok' if ok else 'err' }}">{{ message }}</div>{% endif %}

<div class="scrape-toggle">
  <div>
    <strong>Scraping automatique (Tecsol + PV Magazine)</strong>
    <span class="hint">
      {% if scraping_enabled %}
      Activé : les deux sites sont scrapés et jugés par Mistral, en plus des PDF/liens déposés ci-dessous.
      {% else %}
      Désactivé : seuls les PDF/liens déposés ci-dessous seront traités, tous inclus sans jugement de périmètre ni de priorité (priorité par défaut modifiable dans l'aperçu).
      {% endif %}
    </span>
  </div>
  <form method="post" action="{{ url_for('toggle_scraping') }}">
    <button type="submit" class="switch {{ 'on' if scraping_enabled else '' }}" aria-pressed="{{ 'true' if scraping_enabled else 'false' }}" title="Activer/désactiver le scraping automatique">
      <span class="switch-thumb"></span>
    </button>
  </form>
</div>

<div class="card">
  <h2><span class="step-num">1</span> Déposer PDF P1/P2{% if pending_files or pending_files_previous %}<span class="count-badge">{{ (pending_files|length) + (pending_files_previous|length) }} en attente</span>{% endif %}</h2>
  <form method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data">
    <label class="dropzone" for="pdfs-veille">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>
      </svg>
      <span class="dz-title">Glisse tes PDF ici ou clique pour parcourir</span>
      <span class="dz-hint">Plusieurs fichiers à la fois — titre deviné automatiquement</span>
      <input type="file" id="pdfs-veille" name="pdfs" accept="application/pdf" multiple required hidden>
    </label>
    <div class="dz-selected" data-for="pdfs-veille"></div>
    <input type="submit" value="Déposer les PDF">
  </form>
  {% if pending_files_previous %}
  <div class="leftover-banner" id="pdfLeftoverBanner">
    <span>{{ pending_files_previous|length }} PDF/lien(s) laissé(s) en attente lors d'une session précédente.</span>
    <div class="leftover-actions">
      <button type="button" class="secondary" onclick="revealLeftover('pdfLeftoverList', 'pdfLeftoverBanner')">Afficher</button>
      <form method="post" action="{{ url_for('discard_pending_files') }}" style="margin:0;" onsubmit="return confirm('Supprimer définitivement ces PDF/notes en attente ? Cette action est irréversible.');">
        <button type="submit" class="danger">Supprimer définitivement</button>
      </form>
    </div>
  </div>
  <ul class="file-list hidden-block" id="pdfLeftoverList">
    {% for f in pending_files_previous %}
    <li>
      <span class="fname" title="{{ f.filename }}">{{ f.title }}</span>
      <span class="fsize">{{ f.size_kb }} ko</span>
      <form method="post" action="{{ url_for('delete_pending') }}" style="margin:0;" onsubmit="return confirm('Supprimer ce fichier ?');">
        <input type="hidden" name="filename" value="{{ f.filename }}">
        <button type="submit">Supprimer</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% endif %}
  {% if pending_files %}
  <ul class="file-list">
    {% for f in pending_files %}
    <li>
      <span class="fname" title="{{ f.filename }}">{{ f.title }}</span>
      <span class="fsize">{{ f.size_kb }} ko</span>
      <form method="post" action="{{ url_for('delete_pending') }}" style="margin:0;" onsubmit="return confirm('Supprimer ce fichier ?');">
        <input type="hidden" name="filename" value="{{ f.filename }}">
        <button type="submit">Supprimer</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% elif not pending_files_previous %}
  <p class="hint">Aucun PDF en attente.</p>
  {% endif %}
</div>

<div class="card">
  <h2><span class="step-num">2</span> Déposer PDF P1 uniquement{% if pending_comm_files or pending_comm_files_previous %}<span class="count-badge">{{ (pending_comm_files|length) + (pending_comm_files_previous|length) }} en attente</span>{% endif %}</h2>
  <form method="post" action="{{ url_for('upload_comm') }}" enctype="multipart/form-data">
    <label class="dropzone" for="pdfs-comm">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>
      </svg>
      <span class="dz-title">Glisse tes PDF ici ou clique pour parcourir</span>
      <span class="dz-hint">Communiqués, notes internes... envoyés par la Comm</span>
      <input type="file" id="pdfs-comm" name="pdfs" accept="application/pdf" multiple required hidden>
    </label>
    <div class="dz-selected" data-for="pdfs-comm"></div>
    <input type="submit" value="Déposer les PDF">
  </form>
  <p class="hint">
    Toujours priorité P1, sans jugement de périmètre — thème choisi par
    Mistral parmi ENGIE / ENGIE R&B / ACTU GENERALE ENERGIE (modifiable
    ensuite dans l'aperçu, comme n'importe quel thème).
  </p>
  {% if pending_comm_files_previous %}
  <div class="leftover-banner" id="commLeftoverBanner">
    <span>{{ pending_comm_files_previous|length }} PDF de communication laissé(s) en attente lors d'une session précédente.</span>
    <div class="leftover-actions">
      <button type="button" class="secondary" onclick="revealLeftover('commLeftoverList', 'commLeftoverBanner')">Afficher</button>
      <form method="post" action="{{ url_for('discard_pending_comm_files') }}" style="margin:0;" onsubmit="return confirm('Supprimer définitivement ces PDF en attente ? Cette action est irréversible.');">
        <button type="submit" class="danger">Supprimer définitivement</button>
      </form>
    </div>
  </div>
  <ul class="file-list hidden-block" id="commLeftoverList">
    {% for f in pending_comm_files_previous %}
    <li>
      <span class="fname" title="{{ f.filename }}">{{ f.title }}</span>
      <span class="fsize">{{ f.size_kb }} ko</span>
      <form method="post" action="{{ url_for('delete_pending_comm') }}" style="margin:0;" onsubmit="return confirm('Supprimer ce fichier ?');">
        <input type="hidden" name="filename" value="{{ f.filename }}">
        <button type="submit">Supprimer</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% endif %}
  {% if pending_comm_files %}
  <ul class="file-list">
    {% for f in pending_comm_files %}
    <li>
      <span class="fname" title="{{ f.filename }}">{{ f.title }}</span>
      <span class="fsize">{{ f.size_kb }} ko</span>
      <form method="post" action="{{ url_for('delete_pending_comm') }}" style="margin:0;" onsubmit="return confirm('Supprimer ce fichier ?');">
        <input type="hidden" name="filename" value="{{ f.filename }}">
        <button type="submit">Supprimer</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% elif not pending_comm_files_previous %}
  <p class="hint">Aucun PDF en attente.</p>
  {% endif %}
</div>

<div class="card">
  <h2><span class="step-num">3</span> Ajouter un lien ou coller du texte</h2>
  <form method="post" action="{{ url_for('add_web_note_veille') }}">
    <label>Lien de l'article à scraper (accès libre, pas GreenUnivers)</label>
    <input type="url" name="url" class="input" placeholder="https://...">
    <label style="margin-top:0.8rem;">Ou texte collé à la main (si pas de lien exploitable)</label>
    <textarea name="text" class="textarea" rows="6"
      placeholder="Colle ici le texte de l'article..."></textarea>
    <input type="submit" value="Ajouter à la file">
  </form>
  <p class="hint">
    Pour une source qui n'est pas un PDF GreenUnivers (article en accès
    libre, post LinkedIn, communiqué...). Traité comme les PDF ci-dessus :
    {% if scraping_enabled %}pas de filtrage périmètre, seulement la priorité P1/P2 est jugée.{% else %}aucun jugement (scraping désactivé) : inclus tel quel, priorité par défaut modifiable dans l'aperçu.{% endif %}
  </p>
</div>

<div class="card">
  <h2><span class="step-num">4</span> Générer la veille</h2>
  <button type="button" id="genBtn" onclick="triggerGenerate()">Générer / régénérer la veille</button>
  <p class="hint">
    {% if scraping_enabled %}
    Récupère Tecsol + PV Magazine ({{ next_period_label }}) + les PDF/liens/textes déposés ci-dessus, puis appelle Mistral.
    {% else %}
    Scraping désactivé : traite uniquement les PDF/liens/textes déposés ci-dessus (résumé factuel, sans jugement).
    {% endif %}
  </p>
  <label style="display:flex;align-items:center;gap:0.45rem;margin-top:0.9rem;font-weight:500;font-size:0.87rem;">
    <input type="checkbox" id="customPeriodToggle" onchange="toggleCustomPeriod()">
    Choisir une période personnalisée (ex. rattraper une semaine oubliée)
  </label>
  <div id="customPeriodFields" class="hidden-block" style="margin-top:0.6rem;">
    <label style="margin-right:1rem;">Du
      <input type="date" id="periodStart" value="{{ default_period_start }}" class="input" style="max-width:165px;display:inline-block;width:auto;margin-left:0.3rem;">
    </label>
    <label>Au
      <input type="date" id="periodEnd" value="{{ default_period_end }}" class="input" style="max-width:165px;display:inline-block;width:auto;margin-left:0.3rem;">
    </label>
    <p class="hint" style="margin-top:0.5rem;">
      Par défaut : {{ next_period_label }} (7 jours se terminant aujourd'hui).
      Élargis la période pour rattraper une semaine oubliée, ou choisis une
      plage précise — s'applique uniquement à Tecsol/PV Magazine (les PDF/
      liens déposés à la main ne sont pas concernés par une date).
    </p>
  </div>
</div>

{% if draft_entries %}
{% if draft_from_previous_session %}
<div class="card" id="apercuLeftoverBanner">
  <h2><span class="step-num">5</span> Aperçu en attente (non enregistré)</h2>
  <div class="warn-box" style="margin-bottom:0;">
    Une veille a été générée le {{ draft_run_date_fr }} ({{ draft_entries|length }} actu{{ 's' if draft_entries|length > 1 else '' }}) lors d'une session précédente, mais n'a jamais été validée.
  </div>
  <div class="actions">
    <button type="button" onclick="revealLeftover('apercuFull', 'apercuLeftoverBanner')">Afficher l'aperçu</button>
    <form method="post" action="{{ url_for('discard_draft') }}" style="margin:0;" onsubmit="return confirm('Supprimer définitivement cet aperçu en attente ? Cette action est irréversible (les PDF/liens sources ne sont pas supprimés).');">
      <button type="submit" class="danger">Supprimer définitivement</button>
    </form>
  </div>
</div>
{% endif %}
<div class="card {{ 'hidden-block' if draft_from_previous_session else '' }}" id="apercuFull">
  <h2><span class="step-num">5</span> Aperçu — modifie puis valide</h2>

  {% if source_status %}
  <div class="source-status">
    {% for s in source_status %}
      {% if s.ok and s.count > 0 %}
        <span class="pill ok">✓ {{ s.name }} : {{ s.count }} article(s)</span>
      {% elif s.ok %}
        <span class="pill warn">⚠ {{ s.name }} : 0 article</span>
      {% else %}
        <span class="pill err">✗ {{ s.name }} : échec</span>
      {% endif %}
    {% endfor %}
  </div>
  {% endif %}

  {% if draft_period_label %}
  <p class="hint" style="margin:0 0 0.8rem;">Articles scrapés {{ draft_period_label }}.</p>
  {% endif %}

  {% if warnings %}
  <div class="warn-box">
    <strong>À vérifier avant d'envoyer :</strong>
    <ul>{% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>
  </div>
  {% endif %}

  <p class="hint" style="margin:0 0 0.6rem;">
    Décoche une actu pour l'exclure, modifie titre/résumé/priorité au besoin,
    glisse <span class="drag-handle" style="display:inline;padding:0;">⠿</span>
    pour réordonner, puis valide.
  </p>
  <div class="apercu-toolbar">
    <span id="apercuCounter" class="apercu-counter"></span>
    <select id="apercuThemeFilter">
      <option value="">Tous les thèmes</option>
      {% for theme in theme_options %}
      <option value="{{ theme }}">{{ theme }}</option>
      {% endfor %}
    </select>
    <select id="apercuPriorityFilter">
      <option value="">Toutes priorités</option>
      <option value="P1">P1 uniquement</option>
      <option value="P2">P2 uniquement</option>
    </select>
  </div>
  <form id="apercuForm" data-run-date="{{ draft_run_date_fr }}" method="post">
    <input type="hidden" name="order" id="apercuOrder">
    <input type="hidden" name="filter_theme" id="apercuFilterThemeHidden">
    <input type="hidden" name="filter_priority" id="apercuFilterPriorityHidden">
    <div class="draft-view">
      {% for e in draft_entries %}
      <div class="entry-row" draggable="true" data-index="{{ loop.index0 }}" data-theme="{{ e.theme }}">
        <div class="drag-handle" title="Glisser pour réordonner">⠿</div>
        <div class="entry-controls">
          <label><input type="checkbox" name="keep_{{ loop.index0 }}" checked> Garder</label>
          <select name="priority_{{ loop.index0 }}" class="priority-select">
            <option value="P1" {% if e.priority == 'P1' %}selected{% endif %}>P1</option>
            <option value="P2" {% if e.priority == 'P2' %}selected{% endif %}>P2</option>
          </select>
        </div>
        <div class="entry-body">
          <select name="theme_{{ loop.index0 }}" class="theme-select">
            {% for theme in theme_options %}
            <option value="{{ theme }}" {% if e.theme == theme %}selected{% endif %}>{{ theme }}</option>
            {% endfor %}
          </select><input type="text" class="title-edit" name="title_{{ loop.index0 }}" value="{{ e.title }}">
          <textarea class="summary-edit" name="summary_{{ loop.index0 }}" rows="1">{{ e.summary }}</textarea>
          <p class="hint entry-source" style="margin-top:0.2rem;">{{ e.source_line }}</p>
        </div>
      </div>
      {% else %}
      <p class="hint">Aucune actualité retenue cette semaine.</p>
      {% endfor %}
    </div>
    <div class="actions">
      <button type="submit" formaction="{{ url_for('confirm') }}">Valider (enregistrer + intégrer à l'Excel)</button>
      <button type="button" class="ghost" onclick="copyEditedDraft()">Copier le texte</button>
      <button type="submit" id="downloadPdfBtn" class="secondary" formaction="{{ url_for('download_combined_pdf') }}" formmethod="post">Télécharger le PDF (résumés + sources)</button>
    </div>
  </form>
  <p class="hint">
    "Télécharger le PDF" : un seul fichier avec la synthèse mise en page en
    premier (titres cliquables vers la page source ou le lien de l'article),
    suivie des PDF sources regroupés par thème. Respecte les filtres
    thème/priorité actifs ci-dessus et les modifications faites dans
    l'aperçu (thème/titre/résumé/priorité/actus décochées).
  </p>
</div>
{% endif %}

{% if final_text %}
<div class="card highlight">
  <h2>✓ Veille enregistrée</h2>
  <div id="finalDraftView" class="draft-view">{{ final_text_html|safe }}</div>
  <textarea id="finalDraftTextRaw" style="display:none">{{ final_text }}</textarea>
  <div class="actions">
    <button type="button" onclick="copyFinalDraft()">Copier le texte</button>
    {% if excel_retry_available %}
    <form method="post" action="{{ url_for('retry_excel_integration') }}" style="margin:0;">
      <button type="submit" class="secondary">Réessayer l'intégration Excel</button>
    </form>
    {% endif %}
  </div>
  <p class="hint">Colle directement dans un mail (titres en gras conservés si ton client mail les supporte).</p>
</div>
{% endif %}

<footer class="app-footer">Outil interne — Service Marketing — Clément Duran</footer>

<script>
async function copyFinalDraft() {
  const raw = document.getElementById('finalDraftTextRaw').value;
  const htmlContent = document.getElementById('finalDraftView').innerHTML;
  try {
    const item = new ClipboardItem({
      'text/plain': new Blob([raw], {type: 'text/plain'}),
      'text/html': new Blob([htmlContent], {type: 'text/html'})
    });
    await navigator.clipboard.write([item]);
    toast('Texte copié (avec titres en gras) — colle-le dans ton mail.');
  } catch (e) {
    await navigator.clipboard.writeText(raw);
    toast('Texte copié (sans mise en forme, ton navigateur ne supporte pas mieux).');
  }
}
function collectApercuGroups() {
  const form = document.getElementById('apercuForm');
  const groups = {P1: [], P2: []};
  form.querySelectorAll('.entry-row').forEach(row => {
    if (row.classList.contains('filtered-out')) return; // masquée (filtre thème / "Masquer les P2") : ne pas copier
    const keep = row.querySelector('input[type=checkbox]');
    if (!keep || !keep.checked) return;
    const prio = row.querySelector('select').value;
    const theme = row.dataset.theme || '';
    const titleRaw = row.querySelector('.title-edit').value.trim();
    const title = theme ? `[${theme}] ${titleRaw}` : titleRaw;
    const body = row.querySelector('.summary-edit').value.trim();
    const source = row.querySelector('.entry-source').innerText.trim();
    (groups[prio] || groups.P2).push({title, body, source});
  });
  return groups;
}
function buildApercuText(groups, runDate) {
  const lines = [`Veille hebdo — ${runDate}`, ''];
  [['P1', 'Priorité 1 :'], ['P2', 'Priorité 2 :']].forEach(([key, label]) => {
    lines.push(label);
    const items = groups[key];
    if (!items.length) lines.push('Aucune actualité notable cette semaine dans le périmètre.');
    items.forEach(e => { lines.push(e.title); lines.push(e.body); lines.push(e.source); lines.push(''); });
    if (items.length) lines.pop();
    lines.push('');
  });
  return lines.join('\\n').trim() + '\\n';
}
function buildApercuHtml(groups, runDate) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let out = `<p class="draft-h">${esc('Veille hebdo — ' + runDate)}</p>`;
  [['P1', 'Priorité 1 :'], ['P2', 'Priorité 2 :']].forEach(([key, label]) => {
    out += `<p class="draft-section">${esc(label)}</p>`;
    const items = groups[key];
    if (!items.length) out += '<p class="art-body">Aucune actualité notable cette semaine dans le périmètre.</p>';
    items.forEach(e => {
      out += `<p class="art-title"><strong>${esc(e.title)}</strong></p>`;
      out += `<p class="art-body">${esc(e.body)}</p>`;
      out += `<p class="art-body">${esc(e.source)}</p>`;
    });
  });
  return out;
}
async function copyEditedDraft() {
  const form = document.getElementById('apercuForm');
  const runDate = form.dataset.runDate;
  const groups = collectApercuGroups();
  const text = buildApercuText(groups, runDate);
  try {
    const item = new ClipboardItem({
      'text/plain': new Blob([text], {type: 'text/plain'}),
      'text/html': new Blob([buildApercuHtml(groups, runDate)], {type: 'text/html'})
    });
    await navigator.clipboard.write([item]);
    toast('Aperçu copié (avec titres en gras) — colle-le dans ton mail.');
  } catch (e) {
    await navigator.clipboard.writeText(text);
    toast('Aperçu copié (sans mise en forme, ton navigateur ne supporte pas mieux).');
  }
}
// Overlay "indéterminé" (spinner) : pour les actions courtes sans étapes
// suivies (ex. "Valider" — archivage + Excel), voir apercuForm.
function showLoading(msg) {
  document.getElementById('overlaySpinner').style.display = '';
  document.getElementById('overlayProgressWrap').style.display = 'none';
  const p = document.getElementById('overlayText');
  if (p) p.textContent = msg || 'Récupération des sources et génération en cours… 10 à 30 secondes.';
  document.getElementById('overlay').classList.add('active');
  const btn = document.getElementById('genBtn');
  if (btn) btn.disabled = true;
}

// Overlay "déterminé" (barre de progression réelle) : pour le bouton
// "Générer" — voir triggerGenerate/pollGenerateProgress, alimentés par
// main.build_draft (progress_cb) via /generate + /generate/progress côté
// serveur.
function showProgressOverlay(msg) {
  document.getElementById('overlaySpinner').style.display = 'none';
  document.getElementById('overlayProgressWrap').style.display = '';
  document.getElementById('progressBar').style.width = '0%';
  const p = document.getElementById('overlayText');
  if (p) p.textContent = msg;
  document.getElementById('overlay').classList.add('active');
}
function updateProgressOverlay(pct, msg) {
  document.getElementById('progressBar').style.width = Math.max(0, Math.min(100, pct)) + '%';
  const p = document.getElementById('overlayText');
  if (p && msg) p.textContent = msg;
}
function hideOverlay() {
  document.getElementById('overlay').classList.remove('active');
}

// Bascule l'affichage des champs de période personnalisée (voir
// customPeriodToggle) — purement visuel, triggerGenerate lit directement
// l'état de la case à cocher pour décider quoi envoyer à /generate.
function toggleCustomPeriod() {
  var toggle = document.getElementById('customPeriodToggle');
  var fields = document.getElementById('customPeriodFields');
  if (fields) fields.classList.toggle('hidden-block', !(toggle && toggle.checked));
}

function triggerGenerate() {
  const btn = document.getElementById('genBtn');
  if (btn) btn.disabled = true;
  showProgressOverlay('Récupération des sources en cours…');
  const body = new URLSearchParams();
  const customToggle = document.getElementById('customPeriodToggle');
  if (customToggle && customToggle.checked) {
    const start = document.getElementById('periodStart').value;
    const end = document.getElementById('periodEnd').value;
    if (start) body.set('period_start', start);
    if (end) body.set('period_end', end);
  }
  fetch('/generate', {method: 'POST', body: body})
    .then(function (r) { return r.json(); })
    .then(function () { pollGenerateProgress(btn); })
    .catch(function () {
      hideOverlay();
      if (btn) btn.disabled = false;
      toast("Impossible de démarrer la génération (voir la console).");
    });
}

function pollGenerateProgress(btn) {
  fetch('/generate/progress').then(function (r) { return r.json(); }).then(function (data) {
    if (data.state === 'running') {
      updateProgressOverlay(data.pct || 0, data.msg || 'En cours…');
      setTimeout(function () { pollGenerateProgress(btn); }, 600);
    } else if (data.state === 'done') {
      updateProgressOverlay(100, 'Terminé — actualisation…');
      setTimeout(function () { location.reload(); }, 350);
    } else {
      hideOverlay();
      if (btn) btn.disabled = false;
      toast(data.state === 'error'
        ? ('Erreur pendant la génération : ' + (data.error || 'inconnue'))
        : 'Génération interrompue.');
    }
  }).catch(function () { setTimeout(function () { pollGenerateProgress(btn); }, 1000); });
}

// Thème clair/sombre manuel (le data-theme posé sur <html> l'emporte sur la
// media query prefers-color-scheme, voir règles CSS :root[data-theme=...]).
// Sans choix explicite (première visite), on suit le thème système.
function currentTheme() {
  var forced = document.documentElement.getAttribute('data-theme');
  if (forced === 'dark' || forced === 'light') return forced;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function applyThemeIcon() {
  var dark = currentTheme() === 'dark';
  var sun = document.getElementById('themeIconSun');
  var moon = document.getElementById('themeIconMoon');
  if (sun) sun.style.display = dark ? 'none' : '';
  if (moon) moon.style.display = dark ? '' : 'none';
}
function toggleTheme() {
  var next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('veille-theme', next); } catch (e) {}
  applyThemeIcon();
}
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if (!document.documentElement.getAttribute('data-theme')) applyThemeIcon();
  });
}

// Petit bandeau de confirmation éphémère (remplace les alert() bloquants).
var _toastTimer;
function toast(msg) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function () { t.classList.remove('show'); }, 2800);
}

// Affiche un aperçu/une liste de PDF laissés en attente par une session
// précédente (repliés par défaut derrière un bandeau, voir _render/webapp.py
// pending_files_previous et draft_from_previous_session) et masque le
// bandeau correspondant. Purement visuel : les données étaient déjà chargées
// côté serveur, il n'y a rien à récupérer à distance.
function revealLeftover(showId, hideId) {
  var show = document.getElementById(showId);
  var hide = document.getElementById(hideId);
  if (show) show.classList.remove('hidden-block');
  if (hide) hide.style.display = 'none';
  // Les résumés (textarea auto-hauteur) calculent leur hauteur au chargement
  // via scrollHeight, qui vaut 0 tant que le bloc parent est display:none —
  // il faut recalculer une fois le bloc réellement visible.
  autoResizeSummaries();
}

// Zones de dépôt : clic pour parcourir (via <label for>), glisser-déposer,
// et affichage du nombre de fichiers choisis. Marche pour les deux onglets.
function initDropzones() {
  document.querySelectorAll('.dropzone').forEach(function (dz) {
    var input = dz.querySelector('input[type=file]');
    if (!input) return;
    var out = document.querySelector('.dz-selected[data-for="' + input.id + '"]');
    function render() {
      if (!out) return;
      var n = input.files.length;
      out.textContent = n === 0 ? '' : (n === 1 ? input.files[0].name : n + ' fichiers sélectionnés');
    }
    input.addEventListener('change', render);
    ['dragenter', 'dragover'].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('dragover'); });
    });
    dz.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        render();
      }
    });
  });
}

// Colore le sélecteur de priorité (P1 en vert appuyé, P2 en gris) en direct,
// et met à jour le compteur + les filtres qui en dépendent (masquer les P2).
function initPrioritySelects() {
  document.querySelectorAll('.priority-select').forEach(function (sel) {
    function updClasses() {
      sel.classList.toggle('p1', sel.value === 'P1');
      sel.classList.toggle('p2', sel.value === 'P2');
      updateApercuCounter();
      applyApercuFilters();
    }
    sel.addEventListener('change', function () {
      updClasses();
      reorderByPriority(sel.closest('.entry-row'));
    });
    updClasses();
  });
}

// Le thème est éditable au même titre que la priorité (select dans chaque
// ligne, voir .theme-select) : data-theme doit rester synchro pour que les
// filtres de l'aperçu (applyApercuFilters) et le regroupement par thème du
// texte copié (collectApercuGroups) reflètent bien la valeur choisie.
function initThemeSelects() {
  document.querySelectorAll('.theme-select').forEach(function (sel) {
    sel.addEventListener('change', function () {
      var row = sel.closest('.entry-row');
      if (row) row.dataset.theme = sel.value;
      applyApercuFilters();
    });
  });
}

// Quand on change la priorité d'une actu dans l'aperçu, la ligne se replace
// aussitôt pour respecter "P2 à la fin" (même tri qu'à la génération, voir
// main.build_draft) : descend tout en bas si passée en P2, remonte juste
// avant le premier P2 si repassée en P1. Un flash confirme le déplacement
// (même feedback que le glisser-déposer, voir .just-moved).
function reorderByPriority(row) {
  if (!row) return;
  var container = row.parentElement;
  if (!container) return;
  var sel = row.querySelector('.priority-select');
  if (!sel) return;
  if (sel.value === 'P2') {
    container.appendChild(row);
  } else {
    var firstP2 = Array.from(container.children).find(function (r) {
      return r !== row && r.classList.contains('entry-row') &&
        r.querySelector('.priority-select') && r.querySelector('.priority-select').value === 'P2';
    });
    container.insertBefore(row, firstP2 || null);
  }
  row.classList.add('just-moved');
  setTimeout(function () { row.classList.remove('just-moved'); }, 700);
}

// Grise + barre visuellement une actu décochée (feedback immédiat), et tient
// à jour le compteur P1/P2 conservés.
function initEntryToggles() {
  document.querySelectorAll('.entry-row input[type=checkbox]').forEach(function (cb) {
    var row = cb.closest('.entry-row');
    function upd() { row.classList.toggle('excluded', !cb.checked); updateApercuCounter(); }
    cb.addEventListener('change', upd);
    upd();
  });
  updateApercuCounter();
}

// Compteur "X P1 · Y P2 conservé(s)" en haut de l'aperçu — ne compte que les
// actus encore cochées "Garder", quelle que soit leur priorité actuelle.
function updateApercuCounter() {
  var el = document.getElementById('apercuCounter');
  if (!el) return;
  var p1 = 0, p2 = 0;
  document.querySelectorAll('#apercuForm .entry-row').forEach(function (row) {
    var cb = row.querySelector('input[type=checkbox]');
    if (!cb || !cb.checked) return;
    var sel = row.querySelector('select');
    if (sel && sel.value === 'P1') p1++; else p2++;
  });
  el.textContent = p1 + ' P1 · ' + p2 + ' P2 conservé(s)';
}

// Filtre d'affichage (thème + vue P1/P2) : purement visuel, ne touche pas aux
// cases "Garder" — une actu masquée reste incluse à la validation, et
// "Copier le texte" ne reprend que ce qui reste visible (voir
// collectApercuGroups, qui exclut déjà .filtered-out).
function applyApercuFilters() {
  var themeSel = document.getElementById('apercuThemeFilter');
  var prioSel = document.getElementById('apercuPriorityFilter');
  if (!themeSel) return;
  var theme = themeSel.value;
  var prio = prioSel ? prioSel.value : '';
  document.querySelectorAll('#apercuForm .entry-row').forEach(function (row) {
    var matchesTheme = !theme || row.dataset.theme === theme;
    var sel = row.querySelector('select');
    var matchesPrio = !prio || (sel && sel.value === prio);
    row.classList.toggle('filtered-out', !matchesTheme || !matchesPrio);
  });
}
function initApercuFilters() {
  var themeSel = document.getElementById('apercuThemeFilter');
  var prioSel = document.getElementById('apercuPriorityFilter');
  if (themeSel) themeSel.addEventListener('change', applyApercuFilters);
  if (prioSel) prioSel.addEventListener('change', applyApercuFilters);
}

// Réorganisation par glisser-déposer : on peut saisir n'importe où sur la
// ligne (poignée ⠿ ou ailleurs) SAUF les champs éditables (titre, résumé,
// case à cocher, sélecteur de priorité), pour ne pas gêner la sélection de
// texte/l'interaction avec ces champs. Au dépôt, la ligne est déplacée dans
// le DOM ; l'ordre réel est recalculé juste avant l'envoi du formulaire dans
// le champ caché "order" (voir webapp._parse_edited_entries côté serveur).
function initDragReorder() {
  var container = document.querySelector('#apercuForm .draft-view');
  var form = document.getElementById('apercuForm');
  if (!container || !form) return;
  var dragEl = null;

  function clearDropMarkers() {
    container.querySelectorAll('.entry-row').forEach(function (r) {
      r.classList.remove('drop-before', 'drop-after');
    });
  }

  container.querySelectorAll('.entry-row').forEach(function (row) {
    row.addEventListener('dragstart', function (e) {
      if (e.target.closest('input, textarea, select')) { e.preventDefault(); return; }
      dragEl = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      // Firefox exige un setData pour autoriser le drag ; la valeur elle-même
      // n'est pas utilisée (le réordonnancement se fait via le DOM).
      try { e.dataTransfer.setData('text/plain', row.dataset.index); } catch (err) {}
    });
    row.addEventListener('dragend', function () {
      row.classList.remove('dragging');
      clearDropMarkers();
      // Flash de confirmation sur la ligne à son emplacement final, pour que
      // le déplacement soit sans ambiguïté (au lieu du simple fondu qui la
      // faisait presque disparaître pendant le glisser).
      var moved = row;
      moved.classList.add('just-moved');
      setTimeout(function () { moved.classList.remove('just-moved'); }, 700);
      dragEl = null;
    });
    row.addEventListener('dragover', function (e) {
      if (!dragEl || dragEl === row) return;
      e.preventDefault();
      var rect = row.getBoundingClientRect();
      var after = (e.clientY - rect.top) > rect.height / 2;
      clearDropMarkers();
      row.classList.add(after ? 'drop-after' : 'drop-before');
      container.insertBefore(dragEl, after ? row.nextSibling : row);
    });
    row.addEventListener('drop', function (e) { e.preventDefault(); });
  });
  // Autorise aussi de déposer sous la dernière ligne (zone vide en bas de la
  // liste, qui n'a pas de .entry-row propre pour recevoir un dragover).
  container.addEventListener('dragover', function (e) {
    if (!dragEl) return;
    e.preventDefault();
  });
  container.addEventListener('drop', function (e) { e.preventDefault(); });

  form.addEventListener('submit', function (evt) {
    var order = Array.from(container.querySelectorAll('.entry-row')).map(function (r) { return r.dataset.index; });
    document.getElementById('apercuOrder').value = order.join(',');
    // Ne sert qu'au téléchargement PDF (voir download_combined_pdf) : Valider
    // ignore ces deux champs, seul le "garder"/l'ordre/les éditions comptent.
    var themeFilter = document.getElementById('apercuThemeFilter');
    var prioFilter = document.getElementById('apercuPriorityFilter');
    document.getElementById('apercuFilterThemeHidden').value = themeFilter ? themeFilter.value : '';
    document.getElementById('apercuFilterPriorityHidden').value = prioFilter ? prioFilter.value : '';
    // L'overlay "Enregistrement…" ne concerne que "Valider" : le
    // téléchargement PDF ne navigue pas (réponse en pièce jointe), un overlay
    // resterait affiché indéfiniment puisque rien ne vient ensuite le retirer.
    var isDownload = evt.submitter && evt.submitter.id === 'downloadPdfBtn';
    if (!isDownload) showLoading('Enregistrement et intégration au classeur en cours…');
  });
}

// Les résumés (textarea) s'ajustent à leur contenu au lieu d'un ascenseur
// interne — plus agréable pour relire/éditer un paragraphe court.
function autoResizeSummaries() {
  document.querySelectorAll('.summary-edit').forEach(function (ta) {
    function resize() { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; }
    ta.addEventListener('input', resize);
    resize();
  });
}

document.addEventListener('DOMContentLoaded', function () {
  applyThemeIcon();
  initDropzones();
  initPrioritySelects();
  initThemeSelects();
  initEntryToggles();
  initApercuFilters();
  initDragReorder();
  autoResizeSummaries();
  // Une génération lancée avant un rechargement (ou depuis un autre onglet)
  // continue en tâche de fond côté serveur : on reprend son suivi si elle
  // tourne encore, plutôt que de la perdre silencieusement.
  fetch('/generate/progress').then(function (r) { return r.json(); }).then(function (data) {
    if (data.state === 'running') {
      var btn = document.getElementById('genBtn');
      if (btn) btn.disabled = true;
      showProgressOverlay(data.msg || 'Génération en cours…');
      pollGenerateProgress(btn);
    }
  }).catch(function () {});
});

// Si la page est restaurée depuis le cache du navigateur (bouton
// précédent/suivant après un envoi de formulaire), l'overlay de chargement
// peut rester affiché par-dessus tout et bloquer silencieusement les clics
// on le force à disparaître à chaque affichage.
window.addEventListener('pageshow', function () {
  document.getElementById('overlay').classList.remove('active');
  var btn = document.getElementById('genBtn');
  if (btn) btn.disabled = false;
});
</script>
</body>
</html>
"""


def _draft_to_html(text: str) -> str:
    """Transforme le texte brut de la synthèse en HTML lisible, avec le
    titre de chaque article en gras. Purement pour l'affichage/la copie
    enrichie : le texte brut (draft.text) reste la source de vérité stockée
    en archive et intégrée au classeur Excel."""
    out = []
    block: list[str] = []

    def flush():
        if not block:
            return
        title = html_module.escape(block[0])
        out.append(f'<p class="art-title"><strong>{title}</strong></p>')
        for line in block[1:]:
            out.append(f'<p class="art-body">{html_module.escape(line)}</p>')
        block.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.lower().startswith("veille hebdo"):
            flush()
            out.append(f'<p class="draft-h">{html_module.escape(line)}</p>')
            continue
        if re.match(r"^priorité\s*\d+\s*:?$", line, re.IGNORECASE):
            flush()
            out.append(f'<p class="draft-section">{html_module.escape(line)}</p>')
            continue
        block.append(line)
    flush()
    return "\n".join(out)


def _next_scrape_period_label() -> str:
    """Période que couvrirait un clic sur "Générer" maintenant (voir
    config.get_period) — affichée avant génération pour que l'utilisateur
    sache depuis quelle date les articles seront recherchés."""
    start, end = get_period(date.today())
    return f"du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"


def _render(message=None, ok=False, status=200, final_text=None):
    default_period_start, default_period_end = get_period(date.today())
    all_pending = manual_notes.list_pending(INBOX_GREENUNIVERS)
    pending_files_previous = [f for f in all_pending if f["filename"] in _startup_pending_filenames]
    pending_files = [f for f in all_pending if f["filename"] not in _startup_pending_filenames]
    all_pending_comm = manual_notes.list_pending(INBOX_COMM)
    pending_comm_files_previous = [f for f in all_pending_comm if f["filename"] in _startup_pending_comm_filenames]
    pending_comm_files = [f for f in all_pending_comm if f["filename"] not in _startup_pending_comm_filenames]
    return render_template_string(
        PAGE,
        message=message,
        ok=ok,
        scraping_enabled=_scraping_enabled,
        pending_files=pending_files,
        pending_files_previous=pending_files_previous,
        pending_comm_files=pending_comm_files,
        pending_comm_files_previous=pending_comm_files_previous,
        draft_entries=_pending_draft.entries if _pending_draft else None,
        draft_from_previous_session=_draft_from_previous_session,
        source_status=_pending_draft.source_status if _pending_draft else None,
        warnings=_pending_draft.warnings if _pending_draft else None,
        final_text=final_text,
        final_text_html=_draft_to_html(final_text) if final_text else None,
        draft_run_date_fr=_format_date_fr(_pending_draft.run_date) if _pending_draft else None,
        draft_period_label=_pending_draft.period_label if _pending_draft else None,
        next_period_label=_next_scrape_period_label(),
        default_period_start=default_period_start.isoformat(),
        default_period_end=default_period_end.isoformat(),
        theme_options=VEILLE_THEME_OPTIONS,
        logo_b64=_LOGO_B64,
        excel_retry_available=_last_failed_excel is not None,
    ), status


@app.get("/")
def index():
    return _render()


@app.post("/toggle-scraping")
def toggle_scraping():
    global _scraping_enabled
    _scraping_enabled = not _scraping_enabled
    _save_scraping_enabled()
    return redirect(url_for("index"))


@app.post("/discard-draft")
def discard_draft():
    """Supprime définitivement un aperçu laissé en attente par une session
    précédente sans avoir été validé (voir bandeau _draft_from_previous_session
    dans le template). N'archive/ne touche à aucun PDF/note source : ils
    restent disponibles pour une prochaine génération."""
    global _pending_draft, _draft_from_previous_session
    _pending_draft = None
    _draft_from_previous_session = False
    _persist_draft()
    return redirect(url_for("index"))


@app.post("/discard-pending-files")
def discard_pending_files():
    """Supprime définitivement tous les PDF/notes en attente laissés par une
    session précédente sans avoir été inclus dans une veille validée (voir
    bandeau pending_files_previous dans le template)."""
    global _startup_pending_filenames
    manual_notes.delete_all_pending(INBOX_GREENUNIVERS)
    _startup_pending_filenames = set()
    return redirect(url_for("index"))


@app.post("/discard-pending-comm-files")
def discard_pending_comm_files():
    """Équivalent de /discard-pending-files pour les PDF de communication
    ENGIE (voir bandeau pending_comm_files_previous dans le template)."""
    global _startup_pending_comm_filenames
    manual_notes.delete_all_pending(INBOX_COMM)
    _startup_pending_comm_filenames = set()
    return redirect(url_for("index"))


def _title_from_original_filename(original_name: str) -> str:
    """Nom lisible dérivé du nom de fichier tel que déposé (ex. export
    navigateur "greenunivers.com-Bohr_Energie_leve_95_Me.pdf" -> "Bohr Energie
    leve 95 Me"). Utilisé seulement en repli quand le vrai titre de l'article
    n'a pas pu être extrait du contenu du PDF (voir
    manual_notes.guess_title_from_pdf) : le nom de fichier tronque à 60
    caractères et perd accents/apostrophes, donc moins fidèle que le texte
    de l'article quand celui-ci est exploitable."""
    name = Path(original_name).stem
    name = re.sub(r"^(www\.)?[\w.-]+\.(com|fr|net|org)-", "", name)  # préfixe domaine d'export navigateur
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name or original_name


def _validate_pdf_upload(pdf_files) -> str | None:
    if not pdf_files:
        return "Sélectionne au moins un fichier PDF."
    if any(not f.filename.lower().endswith(".pdf") for f in pdf_files):
        return "Tous les fichiers doivent être des PDF."
    return None


def _save_uploaded_pdfs(pdf_files, inbox_dir: Path) -> list[str]:
    """Dépose les PDF envoyés dans inbox_dir avec un nom unique (horodatage +
    slug + suffixe aléatoire, pour éviter toute collision entre deux dépôts du
    même article) et un .meta.json à côté portant le titre deviné, réutilisé
    aussi bien par l'onglet "Veille automatique" que "Résumés PDF". Un PDF
    dont le contenu (hash) est déjà en attente dans inbox_dir est ignoré au
    lieu d'être déposé une deuxième fois — renvoie les noms de fichiers
    ignorés pour affichage."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    seen_hashes = manual_notes.pending_pdf_hashes(inbox_dir)
    skipped = []
    for pdf_file in pdf_files:
        data = pdf_file.stream.read()
        file_hash = hashlib.sha256(data).hexdigest()
        if file_hash in seen_hashes:
            skipped.append(pdf_file.filename)
            continue
        seen_hashes.add(file_hash)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = secure_filename(Path(pdf_file.filename).stem)[:60] or "article"
        unique = secrets.token_hex(3)
        base_name = f"{stamp}_{slug}_{unique}"
        pdf_path = inbox_dir / f"{base_name}.pdf"
        pdf_path.write_bytes(data)

        title = manual_notes.guess_title_from_pdf(pdf_path) or _title_from_original_filename(pdf_file.filename)
        meta_path = inbox_dir / f"{base_name}.meta.json"
        meta_path.write_text(json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8")
    return skipped


def _upload_message(pdf_files: list, skipped: list[str]) -> str | None:
    """Message à afficher après un dépôt de PDF si au moins un doublon a été
    ignoré (voir _save_uploaded_pdfs) ; None si tout a été déposé sans souci
    (on redirige alors simplement sans message)."""
    if not skipped:
        return None
    added = len(pdf_files) - len(skipped)
    msg = f"{added} PDF déposé(s)." if added else "Aucun PDF déposé."
    msg += f" {len(skipped)} ignoré(s) car déjà en attente (doublon détecté) : {', '.join(skipped)}."
    return msg


@app.post("/upload")
def upload():
    pdf_files = [f for f in request.files.getlist("pdfs") if f and f.filename]
    error = _validate_pdf_upload(pdf_files)
    if error:
        return _render(error, status=400)

    skipped = _save_uploaded_pdfs(pdf_files, INBOX_GREENUNIVERS)
    message = _upload_message(pdf_files, skipped)
    if message:
        return _render(message, ok=True)
    return redirect(url_for("index"))


@app.post("/upload-comm")
def upload_comm():
    """Équivalent de /upload pour les PDF de communication ENGIE (voir
    config.INBOX_COMM) — toujours P1, thème parmi ENGIE/ENGIE R&B/ACTU
    GENERAL ENERGIE (voir summarize_mistral.classify_comm_notes)."""
    pdf_files = [f for f in request.files.getlist("pdfs") if f and f.filename]
    error = _validate_pdf_upload(pdf_files)
    if error:
        return _render(error, status=400)

    skipped = _save_uploaded_pdfs(pdf_files, INBOX_COMM)
    message = _upload_message(pdf_files, skipped)
    if message:
        return _render(message, ok=True)
    return redirect(url_for("index"))


@app.post("/delete-pending")
def delete_pending():
    filename = request.form.get("filename", "")
    manual_notes.delete_pending(INBOX_GREENUNIVERS, filename)
    return redirect(url_for("index"))


@app.post("/delete-pending-comm")
def delete_pending_comm():
    filename = request.form.get("filename", "")
    manual_notes.delete_pending(INBOX_COMM, filename)
    return redirect(url_for("index"))


@app.post("/veille/add-web")
def add_web_note_veille():
    url = request.form.get("url", "").strip()
    text = request.form.get("text", "").strip()
    try:
        manual_notes.add_web_note(INBOX_GREENUNIVERS, url=url, text=text)
    except ValueError as exc:
        return _render(str(exc), status=400)
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter la page (ex. lien injoignable)
        return _render(f"Erreur pendant la récupération : {exc}", status=500)

    return redirect(url_for("index"))


def _run_generation(period_start: date | None = None, period_end: date | None = None) -> None:
    """Tâche de fond : génère l'aperçu de veille en mettant à jour _gen_job
    au fil des étapes (voir main.build_draft progress_cb). Persiste l'aperçu
    dès qu'il est prêt (voir _persist_draft). Respecte le réglage du toggle
    "scraping automatique" tel qu'il était au moment du clic sur "Générer".

    `period_start`/`period_end` : période choisie manuellement dans l'aperçu
    (voir toggleCustomPeriod côté template) — None des deux (cas par défaut)
    laisse build_draft calculer automatiquement les 7 jours se terminant
    aujourd'hui. Reçus déjà parsés (pas de request.* ici : ce code tourne
    dans un thread de fond, hors contexte de requête Flask)."""
    global _pending_draft, _draft_from_previous_session
    def cb(pct, msg):
        if _gen_job is not None:
            _gen_job["pct"] = pct
            _gen_job["msg"] = msg
    try:
        draft = build_draft(
            progress_cb=cb, scraping_enabled=_scraping_enabled,
            period_start=period_start, period_end=period_end,
        )
        _pending_draft = draft
        _draft_from_previous_session = False  # généré dans cette session : affiché normalement, pas replié
        _persist_draft()
        if _gen_job is not None:
            _gen_job["state"] = "done"
    except Exception as exc:  # noqa: BLE001 - remonter l'erreur au client via le job
        if _gen_job is not None:
            _gen_job["state"] = "error"
            _gen_job["error"] = str(exc)


def _parse_period_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@app.post("/generate")
def generate():
    """Démarre la génération en tâche de fond et rend la main immédiatement :
    le front suit l'avancement via /generate/progress (barre de progression).
    period_start/period_end (optionnels, voir customPeriodToggle) : période
    personnalisée à couvrir au lieu du calcul automatique habituel."""
    global _gen_job
    period_start = _parse_period_date(request.form.get("period_start"))
    period_end = _parse_period_date(request.form.get("period_end"))
    with _gen_lock:
        if _gen_job and _gen_job["state"] == "running":
            return jsonify({"state": "running"})
        _gen_job = {"state": "running", "pct": 0, "msg": "Démarrage…", "error": ""}
    threading.Thread(target=_run_generation, args=(period_start, period_end), daemon=True).start()
    return jsonify({"state": "running"})


@app.get("/generate/progress")
def generate_progress():
    if not _gen_job:
        return jsonify({"state": "idle"})
    return jsonify({k: _gen_job.get(k) for k in ("state", "pct", "msg", "error")})


def _parse_edited_entries(form, entries: list[dict]) -> list[dict]:
    """Reconstruit la liste d'entrées à partir du formulaire d'aperçu — voir
    le bloc `entry-row` du template. Prend en compte :
    - l'ordre choisi (champ `order` : indices dans l'ordre d'affichage, après
      réorganisation par glisser-déposer) ;
    - les actus décochées (case `keep_{i}`) qui sont exclues ;
    - la priorité (`priority_{i}`), le thème (`theme_{i}`), le titre
      (`title_{i}`) et le résumé (`summary_{i}`) éventuellement édités en
      direct dans l'aperçu.
    La ligne source n'est pas éditable : reprise de l'entrée d'origine par
    index."""
    order_raw = form.get("order", "")
    indices = [int(x) for x in order_raw.split(",") if x.strip().isdigit()]
    if not indices:  # pas d'ordre transmis : on garde l'ordre d'origine
        indices = list(range(len(entries)))

    edited = []
    for i in indices:
        if i < 0 or i >= len(entries):
            continue
        if not form.get(f"keep_{i}"):
            continue
        base = entries[i]
        priority = form.get(f"priority_{i}") or base["priority"]
        if priority not in ("P1", "P2"):
            priority = base["priority"]
        theme = form.get(f"theme_{i}") or base["theme"]
        if theme not in VEILLE_THEME_OPTIONS:
            theme = base["theme"]
        title = (form.get(f"title_{i}") or "").strip() or base["title"]
        summary = (form.get(f"summary_{i}") or "").strip() or base["summary"]
        edited.append({**base, "priority": priority, "theme": theme, "title": title, "summary": summary})
    return edited


def _integrate_to_excel(entries: list[dict], run_date: date) -> str:
    """Intègre automatiquement la veille finalisée au classeur Excel à partir
    des entrées structurées de l'aperçu (voir tracker_excel.integrate_draft_entries) —
    plus besoin de reformater en texte puis de re-parser. Un échec ici (ex.
    classeur ouvert dans Excel, verrouillé) ne doit pas remettre en cause
    l'archivage déjà effectué : les entrées sont gardées en mémoire pour
    permettre de réessayer en un clic (voir _last_failed_excel,
    /retry-excel-integration) plutôt que de perdre le travail."""
    global _last_failed_excel
    try:
        added = tracker_excel.integrate_draft_entries(entries, run_date)
    except Exception as exc:  # noqa: BLE001
        _last_failed_excel = {"entries": entries, "run_date": run_date}
        return f"Intégration Excel échouée ({exc}) — ferme le classeur si besoin puis clique sur \"Réessayer l'intégration Excel\" ci-dessous."
    _last_failed_excel = None
    if not added:
        return "Aucune actu à intégrer au classeur (aperçu vide)."
    return f"{len(added)} actu(s) ajoutée(s) au classeur Excel."


@app.post("/confirm")
def confirm():
    """Valide l'aperçu (avec les modifications faites dans le formulaire :
    articles décochés, priorités changées) : enregistre la synthèse, archive
    les PDF/notes utilisés, et intègre directement au classeur Excel de
    suivi. Le texte final s'affiche ensuite avec un bouton "Copier" pour le
    coller dans un mail."""
    global _pending_draft, _last_final_text
    if not _pending_draft:
        return _render("Aucun aperçu en attente.", status=400)

    draft = _pending_draft
    edited_entries = _parse_edited_entries(request.form, draft.entries)
    text = finalize_draft(draft, edited_entries)
    _pending_draft = None
    _persist_draft()

    excel_msg = _integrate_to_excel(edited_entries, draft.run_date)
    _last_final_text = text
    return _render(
        f"Veille enregistrée et archivée. {excel_msg}", ok=True, final_text=text,
    )


@app.post("/retry-excel-integration")
def retry_excel_integration():
    """Réessaie l'intégration Excel après un échec à la validation (le plus
    souvent : le classeur était ouvert dans Excel). La synthèse est déjà
    enregistrée/archivée à ce stade ; seule l'intégration au classeur est
    rejouée, sans rien regénérer (voir _last_failed_excel)."""
    if not _last_failed_excel:
        return _render("Rien à réessayer : aucune intégration Excel en échec.", status=400)
    excel_msg = _integrate_to_excel(_last_failed_excel["entries"], _last_failed_excel["run_date"])
    return _render(excel_msg, ok=_last_failed_excel is None, final_text=_last_final_text)


@app.post("/download-combined-pdf")
def download_combined_pdf():
    """Génère à la volée (ne consomme/n'archive rien) un PDF unique : la
    synthèse mise en page de l'aperçu en cours, suivie des PDF sources
    regroupés par thème (voir combined_pdf.build_combined_pdf). Peut être
    appelé autant de fois que voulu avant de cliquer "Valider".

    Soumis depuis apercuForm (bouton "Télécharger le PDF") : reprend donc les
    éditions en cours (thème/titre/résumé/priorité, actus décochées, ordre —
    voir _parse_edited_entries), puis applique en plus les filtres
    thème/priorité actifs dans l'aperçu (filter_theme/filter_priority,
    purement visuels jusqu'ici) pour n'exporter que ce que l'utilisateur voit
    réellement à l'écran."""
    if not _pending_draft or not _pending_draft.entries:
        return _render("Aucun aperçu en attente à exporter.", status=400)

    draft = _pending_draft
    entries = _parse_edited_entries(request.form, draft.entries)
    filter_theme = (request.form.get("filter_theme") or "").strip()
    filter_priority = (request.form.get("filter_priority") or "").strip()
    if filter_theme:
        entries = [e for e in entries if e["theme"] == filter_theme]
    if filter_priority:
        entries = [e for e in entries if e["priority"] == filter_priority]

    try:
        pdf_bytes = combined_pdf.build_combined_pdf(entries, draft.run_date)
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter la page
        return _render(f"Erreur pendant la génération du PDF : {exc}", status=500)

    filename = f"veille_{draft.run_date.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_load_pending()  # recharge un aperçu et le réglage du scraping éventuellement laissés avant un redémarrage

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # Exe distribué (voir build_exe.bat) : pas de terminal de dev pour
        # cliquer sur l'URL affichée, donc on ouvre directement le navigateur.
        # Petit délai pour laisser le serveur Flask commencer à écouter avant
        # la première requête. En développement (script .py), pas d'ouverture
        # automatique : évite un nouvel onglet à chaque redémarrage du code.
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{WEBAPP_PORT}")).start()
    app.run(host="0.0.0.0", port=WEBAPP_PORT, debug=False, threaded=True)
