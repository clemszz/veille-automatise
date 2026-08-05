"""Extraction de texte générique depuis une URL, pour l'onglet "Résumés PDF"
quand la source n'est pas un PDF GreenUnivers (article en accès libre, post
LinkedIn, communiqué de presse...). Contrairement à GreenUnivers (voir
sources/manual_notes.py), rien n'interdit ici une requête automatisée — simple
GET + nettoyage HTML, best-effort (pas d'extraction "lecture" avancée type
Readability : suffisant pour donner à Mistral de quoi rédiger un résumé)."""
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "stratia/1.0"


def fetch_url_text(url: str, max_chars: int = 6000, timeout: int = 20) -> dict:
    """Renvoie {"title": ..., "text": ...}. Lève une exception si l'URL est
    injoignable ou renvoie une erreur HTTP — laissé à l'appelant de décider
    comment l'afficher (voir pdf_solo.add_web_note)."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"},
        timeout=timeout,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "form", "aside"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return {"title": title, "text": text[:max_chars]}


def domain_label(url: str) -> str:
    """Nom de source lisible dérivé du domaine, ex.
    "https://www.pv-magazine.fr/x" -> "pv-magazine.fr", pour l'afficher comme
    "source" quand on n'a pas de nom d'éditeur plus précis."""
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else (netloc or url)
