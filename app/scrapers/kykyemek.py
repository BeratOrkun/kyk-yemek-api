from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from .common import clean_text, parse_turkish_date, parse_calories

BASE_URL = "https://kykyemek.com"
SOURCE_NAME = "kykyemek"


class SourceError(RuntimeError):
    pass


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KYKMenuReader/1.0 (+public menu reader; contact: admin@example.com)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    })
    return session


def _is_menu_card(tag: Any) -> bool:
    classes = tag.get("class", [])
    return "card" in classes and ("cardStyle" in classes or "mainPageColor" in classes)


def parse_menu_html(html: str, city: str, meal: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(_is_menu_card)

    # Kaynağın CSS sınıfları değişirse date sınıfı bulunan kartları yedek olarak dene.
    if not cards:
        candidates = soup.select("div.card, article, .menu-card")
        cards = [node for node in candidates if node.select_one(".date, p.date, time")]

    records: list[dict] = []
    for card in cards:
        date_node = card.select_one("p.date, .date, time")
        date_text = clean_text(date_node.get_text(" ", strip=True)) if date_node else ""
        menu_date = parse_turkish_date(date_text)
        if not menu_date:
            menu_date = parse_turkish_date(card.get_text(" ", strip=True))
        if not menu_date:
            continue

        item_nodes = card.select("p[style*='color:#503C3C'], p[style*='color: #503C3C']")
        if not item_nodes:
            item_nodes = card.select(".menu-item, .meal-item, li")
        items: list[str] = []
        for node in item_nodes:
            item = clean_text(node.get_text(" ", strip=True))
            if item and item not in items:
                items.append(item)

        calorie_node = card.select_one("p.text-end, .text-end, .calorie, .calories")
        calories_text = clean_text(calorie_node.get_text(" ", strip=True)) if calorie_node else ""
        calories = parse_calories(calories_text) or parse_calories(card.get_text(" ", strip=True))

        if not items:
            continue
        records.append({
            "city": city,
            "meal": meal,
            "date": menu_date.isoformat(),
            "items": items,
            "calories": calories,
            "source": SOURCE_NAME,
            "source_url": source_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return records


def fetch_city(city: str, city_slug: str) -> list[dict]:
    """İki öğünü alır. mealType=false kahvaltı, true akşam olarak eşlenir."""
    session = _make_session()
    all_records: list[dict] = []
    for meal, meal_type in (("breakfast", "false"), ("dinner", "true")):
        params = urlencode({"city": city_slug, "mealType": meal_type})
        url = f"{BASE_URL}/Menu/GetDailyMenu/{city_slug}?{params}"
        try:
            response = session.get(url, timeout=18)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SourceError(f"{SOURCE_NAME} HTTP hatası ({city}/{meal}): {exc}") from exc

        parsed = parse_menu_html(response.text, city, meal, url)
        all_records.extend(parsed)

    if not all_records:
        raise SourceError(
            f"{SOURCE_NAME} yanıt verdi ancak {city} için ayrıştırılabilir menü bulamadı. "
            "Şehir kaynakta bulunmuyor olabilir veya HTML yapısı değişmiş olabilir."
        )
    return all_records
