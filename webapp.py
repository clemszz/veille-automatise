"""Mini app web locale, en deux onglets :

- "Veille automatique" : dépôt des PDF GreenUnivers + scrape Tecsol/PV
  Magazine + classification in_scope/priorité par Mistral + génération/
  validation de la synthèse hebdomadaire (workflow d'origine).
- "Résumés PDF" : dépôt de PDF en vrac, résumé + titre générés
  automatiquement par Mistral dans la même nomenclature, SANS décision
  in_scope/priorité — l'utilisateur garde la main sur la sélection des
  articles en choisissant quoi déposer (voir pdf_solo.py).

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
import threading
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template_string, request, url_for
from werkzeug.utils import secure_filename

import pdf_solo
import tracker_excel
from config import BASE_DIR, INBOX_GREENUNIVERS, INBOX_PDF_SOLO, WEBAPP_PORT
from main import Draft, _format_date_fr, build_draft, finalize_draft
from sources import manual_notes

app = Flask(__name__)

# État en mémoire du process (app mono-utilisateur locale, pas besoin de
# session/DB : un seul aperçu "en attente" à la fois par onglet).
_pending_draft: Draft | None = None
_pending_pdf_entries: list[dict] | None = None

# Persistance de l'aperçu sur disque : sans ça, un redémarrage de l'app
# (plantage, fermeture de la fenêtre, redéploiement) perd l'aperçu généré et
# le bouton "Valider" d'un onglet déjà ouvert ne fonctionne plus. On sérialise
# donc l'aperçu (pickle : Draft = dataclass, entries = dicts, notes = chemins)
# pour le recharger au démarrage. Fichier local, app de confiance.
_PENDING_DIR = BASE_DIR / ".cache"
_PENDING_DRAFT_PATH = _PENDING_DIR / "pending_draft.pkl"
_PENDING_PDF_PATH = _PENDING_DIR / "pending_pdf.pkl"

# Génération lancée dans un thread pour pouvoir suivre l'avancement en direct
# (barre de progression), au lieu d'un long POST bloquant. Un seul job à la
# fois (app mono-utilisateur). _gen_job = {kind, state, pct, msg, error}.
_gen_job: dict | None = None
_gen_lock = threading.Lock()


def _persist_draft() -> None:
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    if _pending_draft is None:
        _PENDING_DRAFT_PATH.unlink(missing_ok=True)
    else:
        _PENDING_DRAFT_PATH.write_bytes(pickle.dumps(_pending_draft))


def _persist_pdf() -> None:
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    if _pending_pdf_entries is None:
        _PENDING_PDF_PATH.unlink(missing_ok=True)
    else:
        _PENDING_PDF_PATH.write_bytes(pickle.dumps(_pending_pdf_entries))


def _load_pending() -> None:
    """Recharge au démarrage l'aperçu éventuellement sauvegardé avant un
    redémarrage. Toute erreur de lecture (format changé, fichier corrompu)
    est ignorée : on repart alors d'un aperçu vide, sans planter."""
    global _pending_draft, _pending_pdf_entries
    try:
        if _PENDING_DRAFT_PATH.exists():
            _pending_draft = pickle.loads(_PENDING_DRAFT_PATH.read_bytes())
    except Exception:  # noqa: BLE001
        _pending_draft = None
    try:
        if _PENDING_PDF_PATH.exists():
            _pending_pdf_entries = pickle.loads(_PENDING_PDF_PATH.read_bytes())
    except Exception:  # noqa: BLE001
        _pending_pdf_entries = None


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
<title>Veille ENGIE Green</title>
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
    width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0;
    background: rgba(255,255,255,0.16); display: flex; align-items: center; justify-content: center;
  }
  .hero-mark svg { width: 24px; height: 24px; }
  .hero-txt h1 { font-size: 1.35rem; margin: 0; font-weight: 700; letter-spacing: -0.01em; }
  .hero-txt p { margin: 0.15rem 0 0; font-size: 0.85rem; opacity: 0.9; }

  .tabs { display: flex; gap: 0.3rem; margin-bottom: 1.3rem; border-bottom: 1px solid var(--border); }
  .tab-btn {
    margin: 0; padding: 0.65rem 1.1rem; font-weight: 600; font-size: 0.9rem; cursor: pointer;
    border: none; background: none; color: var(--muted); border-bottom: 2.5px solid transparent;
    border-radius: 0; transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn:hover { background: none; color: var(--accent); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--green); }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1.3rem 1.4rem; margin-bottom: 1.1rem; box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s, transform 0.2s; animation: cardIn 0.4s ease both;
  }
  .card:hover { box-shadow: var(--shadow-md); }
  .card.highlight { border-color: var(--green); background: linear-gradient(var(--green-tint), var(--card) 60%); }
  .tab-panel .card:nth-child(1) { animation-delay: 0.02s; }
  .tab-panel .card:nth-child(2) { animation-delay: 0.07s; }
  .tab-panel .card:nth-child(3) { animation-delay: 0.12s; }
  .tab-panel .card:nth-child(4) { animation-delay: 0.17s; }
  .tab-panel .card:nth-child(5) { animation-delay: 0.22s; }
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
  button:disabled { opacity: 0.6; cursor: default; transform: none; box-shadow: none; }
  a.btn-link {
    display: inline-block; text-decoration: none; margin-top: 1rem; padding: 0.65rem 1.25rem;
    font-weight: 600; font-size: 0.9rem; border-radius: 9px; background: var(--green); color: white;
    transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
  }
  a.btn-link:hover { background: var(--green-dark); transform: translateY(-1px); box-shadow: var(--shadow-md); }
  a.btn-link.secondary { background: var(--btn-secondary-bg); color: var(--text); }
  a.btn-link.secondary:hover { background: var(--btn-secondary-hover); color: var(--accent); }
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
  .entry-row.dragging { opacity: 0.35; }
  .drag-handle {
    cursor: grab; color: var(--muted); font-size: 1rem; line-height: 1; flex-shrink: 0;
    padding: 0.2rem 0.15rem; align-self: flex-start; margin-top: 0.15rem; user-select: none;
    touch-action: none;
  }
  .drag-handle:hover { color: var(--accent); }
  .entry-row.dragging .drag-handle { cursor: grabbing; }
  .theme-badge {
    display: inline-block; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em;
    color: var(--accent); background: var(--green-light); padding: 0.12rem 0.5rem;
    border-radius: 5px; margin-right: 0.4rem; vertical-align: middle;
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
    <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>
      <path d="M2 21c0-3 1.85-5.36 5.08-6"/>
    </svg>
  </div>
  <div class="hero-txt">
    <h1>Veille hebdo ENGIE Green</h1>
    <p>Solaire au sol · Éolien · Stockage BESS · Hydro-STEP</p>
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

<div class="tabs">
  <button type="button" class="tab-btn {{ 'active' if active_tab == 'veille' else '' }}" onclick="showTab('veille', this)">Veille automatique</button>
  <button type="button" class="tab-btn {{ 'active' if active_tab == 'pdf' else '' }}" onclick="showTab('pdf', this)">Résumés PDF</button>
</div>

<div id="panel-veille" class="tab-panel" style="{{ '' if active_tab == 'veille' else 'display:none;' }}">

<div class="card">
  <h2><span class="step-num">1</span> Déposer des articles GreenUnivers{% if pending_files %}<span class="count-badge">{{ pending_files|length }} en attente</span>{% endif %}</h2>
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
  {% else %}
  <p class="hint">Aucun PDF en attente.</p>
  {% endif %}
</div>

<div class="card">
  <h2><span class="step-num">2</span> Ajouter un lien ou coller du texte</h2>
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
    pas de filtrage périmètre, seulement la priorité P1/P2 est jugée.
  </p>
</div>

<div class="card">
  <h2><span class="step-num">3</span> Générer la veille</h2>
  <button type="button" id="genBtn" onclick="triggerGenerate('veille')">Générer / régénérer la veille</button>
  <p class="hint">Récupère Tecsol + PV Magazine de la semaine + les PDF/liens/textes déposés ci-dessus, puis appelle Mistral.</p>
</div>

{% if draft_entries %}
<div class="card">
  <h2><span class="step-num">4</span> Aperçu — modifie puis valide</h2>

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
      {% for theme in draft_entries|map(attribute='theme')|unique %}
      <option value="{{ theme }}">{{ theme }}</option>
      {% endfor %}
    </select>
    <label><input type="checkbox" id="apercuHideP2"> Masquer les P2</label>
  </div>
  <form id="apercuForm" data-run-date="{{ draft_run_date_fr }}" method="post" onsubmit="showLoading('Enregistrement et intégration au classeur en cours…')">
    <input type="hidden" name="order" id="apercuOrder">
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
          <span class="theme-badge">{{ e.theme }}</span><input type="text" class="title-edit" name="title_{{ loop.index0 }}" value="{{ e.title }}">
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
    </div>
  </form>
</div>
{% endif %}

{% if final_text %}
<div class="card highlight">
  <h2>✓ Veille enregistrée</h2>
  <div id="finalDraftView" class="draft-view">{{ final_text_html|safe }}</div>
  <textarea id="finalDraftTextRaw" style="display:none">{{ final_text }}</textarea>
  <div class="actions">
    <button type="button" onclick="copyFinalDraft()">Copier le texte</button>
  </div>
  <p class="hint">Colle directement dans un mail (titres en gras conservés si ton client mail les supporte).</p>
</div>
{% endif %}

</div>

<div id="panel-pdf" class="tab-panel" style="{{ '' if active_tab == 'pdf' else 'display:none;' }}">

<div class="card">
  <h2><span class="step-num">1</span> Déposer des PDF{% if pdf_pending_files %}<span class="count-badge">{{ pdf_pending_files|length }} en attente</span>{% endif %}</h2>
  <form method="post" action="{{ url_for('upload_pdf_solo') }}" enctype="multipart/form-data">
    <label class="dropzone" for="pdfs-solo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>
      </svg>
      <span class="dz-title">Glisse tes PDF ici ou clique pour parcourir</span>
      <span class="dz-hint">Plusieurs fichiers à la fois — titre deviné automatiquement</span>
      <input type="file" id="pdfs-solo" name="pdfs" accept="application/pdf" multiple required hidden>
    </label>
    <div class="dz-selected" data-for="pdfs-solo"></div>
    <input type="submit" value="Déposer les PDF">
  </form>
  <p class="hint">
    Contrairement à l'onglet "Veille automatique", tout PDF déposé ici sera
    résumé et gardé — pas de filtrage in_scope/priorité : c'est toi qui décides
    quoi déposer.
  </p>
  {% if pdf_pending_files %}
  <ul class="file-list">
    {% for f in pdf_pending_files %}
    <li>
      <span class="fname" title="{{ f.filename }}">{{ f.title }}</span>
      <span class="fsize">{{ f.size_kb }} ko</span>
      <form method="post" action="{{ url_for('delete_pending_pdf_solo') }}" style="margin:0;" onsubmit="return confirm('Supprimer ce fichier ?');">
        <input type="hidden" name="filename" value="{{ f.filename }}">
        <button type="submit">Supprimer</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="hint">Aucun PDF en attente.</p>
  {% endif %}
</div>

<div class="card">
  <h2><span class="step-num">2</span> Ajouter un lien ou coller du texte</h2>
  <form method="post" action="{{ url_for('add_web_note_pdf_solo') }}">
    <label>Lien de l'article à scraper (accès libre, pas GreenUnivers)</label>
    <input type="url" name="url" class="input" placeholder="https://...">
    <label style="margin-top:0.8rem;">Ou texte collé à la main (si pas de lien exploitable)</label>
    <textarea name="text" class="textarea" rows="6"
      placeholder="Colle ici le texte de l'article..."></textarea>
    <input type="submit" value="Ajouter à la file">
  </form>
  <p class="hint">
    Pour les sources qui ne sont pas un PDF GreenUnivers (article en accès
    libre, post LinkedIn, communiqué...). Remplis l'un OU l'autre : le lien
    est scrapé automatiquement, sinon le texte collé est utilisé tel quel.
  </p>
</div>

<div class="card">
  <h2><span class="step-num">3</span> Générer les résumés</h2>
  <button type="button" id="genPdfBtn" onclick="triggerGenerate('pdf')">Générer / régénérer les résumés</button>
  <p class="hint">Résume chaque PDF/lien/texte déposé ci-dessus (titre + résumé factuel), même nomenclature que la veille hebdo.</p>
</div>

{% if pdf_entries %}
<div class="card">
  <h2><span class="step-num">4</span> Aperçu — à valider avant diffusion</h2>
  <div id="pdfDraftView" class="draft-view">{{ pdf_entries_html|safe }}</div>
  <textarea id="pdfDraftTextRaw" style="display:none">{{ pdf_entries_text }}</textarea>
  <div class="actions">
    <button type="button" onclick="copyPdfDraft()">Copier le texte</button>
    <a class="btn-link secondary" href="{{ url_for('download_pdf_solo') }}">Télécharger le PDF (résumés + sources)</a>
    <form method="post" action="{{ url_for('confirm_pdf_solo') }}" style="display:inline">
      <button type="submit" class="ghost">Valider (archiver les PDF)</button>
    </form>
  </div>
  <p class="hint">
    "Copier le texte" : même format "[THEME] Titre" / résumé / source que la
    veille hebdo, à coller directement dans un mail. "Télécharger le PDF" :
    un seul PDF avec la page de résumés en premier, suivie de tous les PDF
    sources compilés à la suite dans le même ordre.
  </p>
</div>
{% endif %}

</div>

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
async function copyPdfDraft() {
  const raw = document.getElementById('pdfDraftTextRaw').value;
  const htmlContent = document.getElementById('pdfDraftView').innerHTML;
  try {
    const item = new ClipboardItem({
      'text/plain': new Blob([raw], {type: 'text/plain'}),
      'text/html': new Blob([htmlContent], {type: 'text/html'})
    });
    await navigator.clipboard.write([item]);
    toast('Résumés copiés (avec titres en gras) dans le presse-papier.');
  } catch (e) {
    await navigator.clipboard.writeText(raw);
    toast('Résumés copiés (sans mise en forme, ton navigateur ne supporte pas mieux).');
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

// Overlay "déterminé" (barre de progression réelle) : pour les deux boutons
// "Générer" — voir triggerGenerate/pollProgress, alimentés par
// main.build_draft/pdf_solo.generate_entries (progress_cb) via
// /generate + /generate/progress côté serveur.
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

function triggerGenerate(kind) {
  const isPdf = kind === 'pdf';
  const endpoint = isPdf ? '/pdf-solo/generate' : '/generate';
  const btn = document.getElementById(isPdf ? 'genPdfBtn' : 'genBtn');
  if (btn) btn.disabled = true;
  showProgressOverlay(isPdf ? 'Extraction et résumé en cours…' : 'Récupération des sources en cours…');
  fetch(endpoint, {method: 'POST'})
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
function showTab(name, btn) {
  var shown = name === 'veille' ? document.getElementById('panel-veille') : document.getElementById('panel-pdf');
  document.getElementById('panel-veille').style.display = name === 'veille' ? '' : 'none';
  document.getElementById('panel-pdf').style.display = name === 'pdf' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Relance l'animation de fondu du panneau affiché.
  shown.style.animation = 'none';
  void shown.offsetWidth;
  shown.style.animation = '';
  history.replaceState(null, '', '?tab=' + name);
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
    function upd() {
      sel.classList.toggle('p1', sel.value === 'P1');
      sel.classList.toggle('p2', sel.value === 'P2');
      updateApercuCounter();
      applyApercuFilters();
    }
    sel.addEventListener('change', upd);
    upd();
  });
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

// Filtre d'affichage (thème + masquer les P2) : purement visuel, ne touche
// pas aux cases "Garder" — une actu masquée reste incluse à la validation.
function applyApercuFilters() {
  var themeSel = document.getElementById('apercuThemeFilter');
  var hideP2 = document.getElementById('apercuHideP2');
  if (!themeSel) return;
  var theme = themeSel.value;
  var hide = hideP2 && hideP2.checked;
  document.querySelectorAll('#apercuForm .entry-row').forEach(function (row) {
    var matchesTheme = !theme || row.dataset.theme === theme;
    var sel = row.querySelector('select');
    var isP2 = sel && sel.value === 'P2';
    row.classList.toggle('filtered-out', !matchesTheme || (hide && isP2));
  });
}
function initApercuFilters() {
  var themeSel = document.getElementById('apercuThemeFilter');
  var hideP2 = document.getElementById('apercuHideP2');
  if (themeSel) themeSel.addEventListener('change', applyApercuFilters);
  if (hideP2) hideP2.addEventListener('change', applyApercuFilters);
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
      dragEl = null;
    });
    row.addEventListener('dragover', function (e) {
      if (!dragEl || dragEl === row) return;
      e.preventDefault();
      var rect = row.getBoundingClientRect();
      var after = (e.clientY - rect.top) > rect.height / 2;
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

  form.addEventListener('submit', function () {
    var order = Array.from(container.querySelectorAll('.entry-row')).map(function (r) { return r.dataset.index; });
    document.getElementById('apercuOrder').value = order.join(',');
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
  initEntryToggles();
  initApercuFilters();
  initDragReorder();
  autoResizeSummaries();
  // Une génération lancée avant un rechargement (ou depuis un autre onglet)
  // continue en tâche de fond côté serveur : on reprend son suivi si elle
  // tourne encore, plutôt que de la perdre silencieusement.
  fetch('/generate/progress').then(function (r) { return r.json(); }).then(function (data) {
    if (data.state === 'running') {
      var btn = document.getElementById(data.kind === 'pdf' ? 'genPdfBtn' : 'genBtn');
      if (btn) btn.disabled = true;
      showProgressOverlay(data.msg || 'Génération en cours…');
      pollGenerateProgress(btn);
    }
  }).catch(function () {});
});

// Si la page est restaurée depuis le cache du navigateur (bouton
// précédent/suivant après un envoi de formulaire), l'overlay de chargement
// peut rester affiché par-dessus tout et bloquer silencieusement les clics
// (bouton d'onglet y compris) : on le force à disparaître à chaque affichage.
window.addEventListener('pageshow', function () {
  document.getElementById('overlay').classList.remove('active');
  ['genBtn', 'genPdfBtn'].forEach(function (id) {
    var btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });
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


def _pdf_entries_to_html(entries: list[dict]) -> str:
    """Même esprit que _draft_to_html, mais à partir des entrées structurées
    de l'onglet "Résumés PDF" (pas de texte brut à re-parser, pas de titre de
    section Priorité 1/2 puisqu'il n'y a pas de triage ici)."""
    out = []
    for e in entries:
        title = html_module.escape(f"[{e['theme']}] {e['title']}")
        out.append(f'<p class="art-title"><strong>{title}</strong></p>')
        out.append(f'<p class="art-body">{html_module.escape(e["summary"])}</p>')
    return "\n".join(out)


def _render(message=None, ok=False, status=200, active_tab="veille", final_text=None):
    return render_template_string(
        PAGE,
        message=message,
        ok=ok,
        active_tab=active_tab,
        pending_files=manual_notes.list_pending(INBOX_GREENUNIVERS),
        draft_entries=_pending_draft.entries if _pending_draft else None,
        source_status=_pending_draft.source_status if _pending_draft else None,
        warnings=_pending_draft.warnings if _pending_draft else None,
        final_text=final_text,
        final_text_html=_draft_to_html(final_text) if final_text else None,
        draft_run_date_fr=_format_date_fr(_pending_draft.run_date) if _pending_draft else None,
        pdf_pending_files=pdf_solo.list_pending(),
        pdf_entries=_pending_pdf_entries,
        pdf_entries_html=_pdf_entries_to_html(_pending_pdf_entries) if _pending_pdf_entries else None,
        pdf_entries_text=pdf_solo.format_entries_text(_pending_pdf_entries) if _pending_pdf_entries else None,
    ), status


@app.get("/")
def index():
    active_tab = "pdf" if request.args.get("tab") == "pdf" else "veille"
    return _render(active_tab=active_tab)


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


@app.post("/delete-pending")
def delete_pending():
    filename = request.form.get("filename", "")
    manual_notes.delete_pending(INBOX_GREENUNIVERS, filename)
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


def _run_generation() -> None:
    """Tâche de fond : génère l'aperçu de veille en mettant à jour _gen_job
    au fil des étapes (voir main.build_draft progress_cb). Persiste l'aperçu
    dès qu'il est prêt (voir _persist_draft)."""
    global _pending_draft
    def cb(pct, msg):
        if _gen_job is not None:
            _gen_job["pct"] = pct
            _gen_job["msg"] = msg
    try:
        draft = build_draft(progress_cb=cb)
        _pending_draft = draft
        _persist_draft()
        if _gen_job is not None:
            _gen_job["state"] = "done"
    except Exception as exc:  # noqa: BLE001 - remonter l'erreur au client via le job
        if _gen_job is not None:
            _gen_job["state"] = "error"
            _gen_job["error"] = str(exc)


def _run_pdf_generation() -> None:
    global _pending_pdf_entries
    def cb(pct, msg):
        if _gen_job is not None:
            _gen_job["pct"] = pct
            _gen_job["msg"] = msg
    try:
        entries = pdf_solo.generate_entries(progress_cb=cb)
        _pending_pdf_entries = entries
        _persist_pdf()
        if _gen_job is not None:
            _gen_job["state"] = "done"
    except Exception as exc:  # noqa: BLE001
        if _gen_job is not None:
            _gen_job["state"] = "error"
            _gen_job["error"] = str(exc)


@app.post("/generate")
def generate():
    """Démarre la génération en tâche de fond et rend la main immédiatement :
    le front suit l'avancement via /generate/progress (barre de progression)."""
    global _gen_job
    with _gen_lock:
        if _gen_job and _gen_job["state"] == "running":
            return jsonify({"state": "running"})
        _gen_job = {"kind": "veille", "state": "running", "pct": 0, "msg": "Démarrage…", "error": ""}
    threading.Thread(target=_run_generation, daemon=True).start()
    return jsonify({"state": "running"})


@app.get("/generate/progress")
def generate_progress():
    if not _gen_job:
        return jsonify({"state": "idle"})
    return jsonify({k: _gen_job.get(k) for k in ("kind", "state", "pct", "msg", "error")})


def _parse_edited_entries(form, entries: list[dict]) -> list[dict]:
    """Reconstruit la liste d'entrées à partir du formulaire d'aperçu — voir
    le bloc `entry-row` du template. Prend en compte :
    - l'ordre choisi (champ `order` : indices dans l'ordre d'affichage, après
      réorganisation par glisser-déposer) ;
    - les actus décochées (case `keep_{i}`) qui sont exclues ;
    - la priorité (`priority_{i}`), le titre (`title_{i}`) et le résumé
      (`summary_{i}`) éventuellement édités en direct dans l'aperçu.
    Le thème et la ligne source ne sont pas éditables : repris de l'entrée
    d'origine par index."""
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
        title = (form.get(f"title_{i}") or "").strip() or base["title"]
        summary = (form.get(f"summary_{i}") or "").strip() or base["summary"]
        edited.append({**base, "priority": priority, "title": title, "summary": summary})
    return edited


def _integrate_to_excel(text: str, run_date: date) -> str:
    """Intègre automatiquement la veille finalisée au classeur Excel — voir
    tracker_excel.integrate_draft_text. Un échec ici (ex. classeur ouvert
    dans Excel, verrouillé) ne doit pas remettre en cause l'archivage déjà
    effectué : on le signale pour un rattrapage via la carte manuelle."""
    try:
        added = tracker_excel.integrate_draft_text(text, run_date)
    except Exception as exc:  # noqa: BLE001
        return f"Intégration Excel échouée ({exc}) — utilise la carte d'intégration manuelle ci-dessous."
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
    global _pending_draft
    if not _pending_draft:
        return _render("Aucun aperçu en attente.", status=400)

    draft = _pending_draft
    edited_entries = _parse_edited_entries(request.form, draft.entries)
    text = finalize_draft(draft, edited_entries)
    _pending_draft = None
    _persist_draft()

    excel_msg = _integrate_to_excel(text, draft.run_date)
    return _render(
        f"Veille enregistrée et archivée. {excel_msg}", ok=True, final_text=text,
    )


@app.post("/pdf-solo/upload")
def upload_pdf_solo():
    pdf_files = [f for f in request.files.getlist("pdfs") if f and f.filename]
    error = _validate_pdf_upload(pdf_files)
    if error:
        return _render(error, status=400, active_tab="pdf")

    skipped = _save_uploaded_pdfs(pdf_files, INBOX_PDF_SOLO)
    message = _upload_message(pdf_files, skipped)
    if message:
        return _render(message, ok=True, active_tab="pdf")
    return redirect(url_for("index", tab="pdf"))


@app.post("/pdf-solo/delete-pending")
def delete_pending_pdf_solo():
    filename = request.form.get("filename", "")
    pdf_solo.delete_pending(filename)
    return redirect(url_for("index", tab="pdf"))


@app.post("/pdf-solo/add-web")
def add_web_note_pdf_solo():
    url = request.form.get("url", "").strip()
    text = request.form.get("text", "").strip()
    try:
        pdf_solo.add_web_note(url=url, text=text)
    except ValueError as exc:
        return _render(str(exc), status=400, active_tab="pdf")
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter la page (ex. lien injoignable)
        return _render(f"Erreur pendant la récupération : {exc}", status=500, active_tab="pdf")

    return redirect(url_for("index", tab="pdf"))


@app.post("/pdf-solo/generate")
def generate_pdf_solo():
    """Comme /generate mais pour l'onglet Résumés PDF (même mécanisme de
    progression en tâche de fond, même endpoint /generate/progress)."""
    global _gen_job
    with _gen_lock:
        if _gen_job and _gen_job["state"] == "running":
            return jsonify({"state": "running"})
        _gen_job = {"kind": "pdf", "state": "running", "pct": 0, "msg": "Démarrage…", "error": ""}
    threading.Thread(target=_run_pdf_generation, daemon=True).start()
    return jsonify({"state": "running"})


@app.get("/pdf-solo/download-pdf")
def download_pdf_solo():
    """Génère à la volée (ne consomme/n'archive rien) un PDF unique : la page
    de résumés suivie de tous les PDF sources compilés à la suite, voir
    pdf_solo.build_combined_pdf."""
    if not _pending_pdf_entries:
        return _render("Aucun résumé en attente à exporter.", status=400, active_tab="pdf")

    try:
        pdf_bytes = pdf_solo.build_combined_pdf(_pending_pdf_entries)
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter la page
        return _render(f"Erreur pendant la génération du PDF : {exc}", status=500, active_tab="pdf")

    filename = f"resumes_pdf_{date.today().isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/pdf-solo/confirm")
def confirm_pdf_solo():
    """Archive les PDF résumés (déplacés hors de la file d'attente) — comme
    pour l'onglet "Veille automatique", l'envoi/l'intégration au classeur se
    fait séparément (copier-coller du texte, voir carte 3)."""
    global _pending_pdf_entries
    if not _pending_pdf_entries:
        return _render("Aucun résumé en attente.", status=400, active_tab="pdf")

    pdf_solo.archive_processed(_pending_pdf_entries)
    _pending_pdf_entries = None
    _persist_pdf()
    return _render(
        "PDF archivés. Ils ont été déplacés hors de la file d'attente.", ok=True, active_tab="pdf"
    )


_load_pending()  # recharge un aperçu éventuellement laissé avant un redémarrage

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WEBAPP_PORT, debug=False, threaded=True)
