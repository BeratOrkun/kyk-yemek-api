from __future__ import annotations
import json
import re
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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://kykyemek.com/",
    })
    return session


def _is_menu_card(tag: Any) -> bool:
    classes = tag.get("class", [])
    return "card" in classes and ("cardStyle" in classes or "mainPageColor" in classes or "cardDate" in str(tag))


def parse_menu_html(html: str, city: str, meal: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(_is_menu_card)

    if not cards:
        cards = soup.select(".card, div.card, article, .menu-card")

    records: list[dict] = []
    for card in cards:
        date_node = card.select_one(".cardDate, p.date, .date, time")
        date_text = clean_text(date_node.get_text(" ", strip=True)) if date_node else ""
        menu_date = parse_turkish_date(date_text)
        if not menu_date:
            menu_date = parse_turkish_date(card.get_text(" ", strip=True))
        if not menu_date:
            continue

        item_nodes = card.select(".food-main-text, .food-detail-text, p[style*='color:#503C3C'], p[style*='color: #503C3C']")
        if not item_nodes:
            item_nodes = card.select(".menu-item, .meal-item, li")

        items: list[str] = []
        for node in item_nodes:
            raw_text = clean_text(node.get_text(" ", strip=True))
            if not raw_text or raw_text in {"/", "-", "~"}:
                continue
            if "kcal" in raw_text.lower() or parse_calories(raw_text) is not None:
                continue
            # Yemek adı / ile ayrılmış alternatifler içerebilir (Örn: Ezogelin Çorba / Brokoli Çorba)
            if "/" in raw_text:
                parts = [clean_text(p) for p in raw_text.split("/") if clean_text(p)]
                for p in parts:
                    if p and p not in items and len(p) <= 120:
                        items.append(p)
            else:
                if raw_text not in items and len(raw_text) <= 120:
                    items.append(raw_text)

        calorie_node = card.select_one(".card-body div:last-child, p.text-end, .text-end, .calorie, .calories")
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
    
    # kykyemek API il adının baş harfi büyük bekler (Örn: Ankara, Istanbul, Izmir)
    city_param = city.capitalize()

    for meal, meal_type in (("breakfast", "false"), ("dinner", "true")):
        params = urlencode({"city": city_param, "mealType": meal_type, "hidePast": "false", "monthShift": "0"})
        url = f"{BASE_URL}/Menu/GetDailyMenu/{city_param}?{params}"
        try:
            response = session.get(url, timeout=18)
            response.raise_for_status()
            try:
                data = response.json()
                html = data.get("html", "")
            except Exception:
                html = response.text
        except requests.RequestException as exc:
            raise SourceError(f"{SOURCE_NAME} HTTP hatası ({city}/{meal}): {exc}") from exc

        parsed = parse_menu_html(html, city, meal, url)
        all_records.extend(parsed)

    if not all_records:
        raise SourceError(
            f"{SOURCE_NAME} yanıt verdi ancak {city} için ayrıştırılabilir menü bulamadı. "
            "Şehir kaynakta bulunmuyor olabilir veya HTML yapısı değişmiş olabilir."
        )
    return all_records
