"""Pré-filtre grossier par mots-clés, avant l'appel Mistral.

But : réduire le volume d'articles envoyés au modèle (coût/latence), pas
remplacer le jugement fin sur le périmètre. Un article qui matche un mot-clé
d'exclusion n'est PAS supprimé ici : on laisse Mistral trancher avec le
contexte complet, on se contente de ne pas le perdre s'il matche aussi un
mot-clé d'inclusion (ex. article agrivoltaïsme qui mentionne une toiture en
passant).
"""
from config import INCLUDE_KEYWORDS


def is_candidate(article: dict) -> bool:
    haystack = " ".join([
        article.get("title", ""),
        article.get("excerpt", ""),
        article.get("content", ""),
    ]).lower()
    return any(kw in haystack for kw in INCLUDE_KEYWORDS)


def prefilter(articles: list[dict]) -> list[dict]:
    return [a for a in articles if is_candidate(a)]
