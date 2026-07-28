from datetime import date

from .wp_source import fetch_posts

BASE_URL = "https://www.pv-magazine.fr"


def fetch(start: date, end: date) -> list[dict]:
    # pv-magazine.fr demande un Crawl-delay de 10s dans son robots.txt
    return fetch_posts(BASE_URL, start, end, source_name="PV Magazine France", crawl_delay=10.0)
