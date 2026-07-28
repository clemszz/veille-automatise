from datetime import date

from .wp_source import fetch_posts

BASE_URL = "https://tecsol-quotidien.fr"


def fetch(start: date, end: date) -> list[dict]:
    return fetch_posts(BASE_URL, start, end, source_name="Tecsol Quotidien", crawl_delay=1.0)
