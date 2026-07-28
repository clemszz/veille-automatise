"""Récupération d'articles via l'API REST WordPress standard (wp-json).

Utilisé pour les sources publiques (Tecsol Quotidien, PV Magazine France).
N'est PAS utilisé pour GreenUnivers : contenu réservé aux abonnés, et les
mentions légales du site interdisent explicitement les requêtes automatisées
et la redistribution interne du contenu (cf. README). Pour GreenUnivers, voir
manual_notes.py.
"""
import html
import re
import time
from datetime import date, datetime

import requests

USER_AGENT = "veille-engie-green/1.0"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get_with_retry(url: str, params: dict, attempts: int = 4):
    """Petites tentatives avec backoff, sur une connexion neuve à chaque essai
    (une nouvelle requests.Session() à chaque fois) : certains WAF/CDN
    (Cloudflare) semblent maintenir un score anti-bot dégradé sur une
    connexion déjà challengée, alors qu'une connexion neuve repart saine."""
    last_exc = None
    for i in range(attempts):
        try:
            session = requests.Session()
            session.headers.update(DEFAULT_HEADERS)
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code in (403, 429, 503) and i < attempts - 1:
                time.sleep(2 + 3 * i)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(2 + 3 * i)
    raise last_exc


def fetch_posts(base_url: str, start: date, end: date, source_name: str,
                 crawl_delay: float = 1.0, max_pages: int = 5) -> list[dict]:
    """Récupère les articles publiés entre start et end (inclus) via wp-json.

    base_url: racine du site, ex. "https://tecsol-quotidien.fr"
    """
    after = datetime.combine(start, datetime.min.time()).isoformat()
    before = datetime.combine(end, datetime.max.time()).isoformat()

    articles = []
    page = 1

    while page <= max_pages:
        url = f"{base_url}/wp-json/wp/v2/posts"
        params = {
            "after": after,
            "before": before,
            "per_page": 50,
            "page": page,
            "orderby": "date",
            "order": "desc",
        }
        resp = _get_with_retry(url, params)
        if resp.status_code == 400:
            break  # au-delà de la dernière page, WP renvoie 400
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break

        for post in batch:
            articles.append({
                "source": source_name,
                "title": _strip_html(post.get("title", {}).get("rendered", "")),
                "url": post.get("link", ""),
                "date": post.get("date", ""),
                "excerpt": _strip_html(post.get("excerpt", {}).get("rendered", ""))[:600],
                "content": _strip_html(post.get("content", {}).get("rendered", ""))[:3000],
            })

        total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
        page += 1
        time.sleep(crawl_delay)  # respect du Crawl-delay annoncé par le site

    return articles
