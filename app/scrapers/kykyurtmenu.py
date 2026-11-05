from __future__ import annotations
from datetime import datetime, timezone
import re
import requests
from bs4 import BeautifulSoup

from .common import clean_text, parse_turkish_date, parse_calories

BASE_URL = "https://www.kykyurtmenu.com"
SOURCE_NAME = "kykyurtmenu"


class SourceError(RuntimeError):
    pass


def parse_city_page(html: str, city: str, meal: str, source_url: str) -> list[dict]:
    """kykyurtmenu şehir/öğün sayfasındaki seçili menüyü çıkarır.

    Bu kaynak herkese açık bir API yayımlamıyor; sayfanın HTML metni okunur.
    HTML tasarımı değişirse parser'ın güncellenmesi gerekebilir.
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean_text(x) for x in soup.get_text("\n", strip=True).splitlines()]
    lines = [x for x in lines if x]

    meal_title = "Kahvaltı" if meal == "breakfast" else "Akşam Yemeği"
    date_value = None
    for line in lines[:12]:
        date_value = parse_turkish_date(line)
        if date_value:
            break
    if not date_value:
        date_value = parse_turkish_date(" ".join(lines[:15]))
    if not date_value:
        return []

    # Menü başlığı tek satır olarak geçtiğinde oradan başla; bu, menü listesini
    # şehir sayfasının SEO açıklamalarından ayırmaya yardımcı olur.
    start = None
    for i, line in enumerate(lines):
        if line.casefold() == meal_title.casefold():
            if i + 1 < len(lines) and parse_calories(lines[i + 1]) is not None:
                start = i + 1
                break
    if start is None:
        # Bazı HTML sürümlerinde başlık satırı yanında başka metin de bulunabilir.
        for i, line in enumerate(lines):
            if line.casefold().startswith(meal_title.casefold()) and i + 1 < len(lines):
                start = i + 1
                break
    if start is None:
        return []

    calories = parse_calories(lines[start]) if start < len(lines) else None
    items: list[str] = []
    for line in lines[start + 1:]:
        low = line.casefold()
        if "ana menü" in low or "diğer öğünü gör" in low or "diğer öğünü" in low:
            break
        if line.startswith(("🍳", "🍲", "🏠")):
            break
        if re.match(r"^\d+\.?\s*yemek$", low):
            continue
        if parse_turkish_date(line):
            continue
        if low in {"kahvaltı", "akşam", "akşam yemeği", "ana sayfa", "şehirler", "-", "yemek listesi", "kcal"}:
            continue
        if re.match(r"^\d+(\s*/\s*\d+)*$", line.strip()):
            continue
        if low in {"pzt", "sal", "çar", "per", "cum", "cmt", "paz"}:
            continue
        if re.match(r"^(pzt|sal|çar|per|cum|cmt|paz)\s*\d+$", low):
            continue
        if line not in items and len(line) <= 120:
            items.append(line)

    if not items:
        return []
    return [{
        "city": city,
        "meal": meal,
        "date": date_value.isoformat(),
        "items": items,
        "calories": calories,
        "source": SOURCE_NAME,
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }]


def fetch_city(city: str, city_slug: str) -> list[dict]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KYKMenuReader/1.0 (+public menu reader)",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    all_records: list[dict] = []
    for meal, suffix in (("breakfast", "kahvalti"), ("dinner", "aksam")):
        url = f"{BASE_URL}/{city_slug.lower()}/{suffix}"
        try:
            response = session.get(url, timeout=18)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SourceError(f"{SOURCE_NAME} HTTP hatası ({city}/{meal}): {exc}") from exc
        all_records.extend(parse_city_page(response.text, city, meal, url))

    if not all_records:
        raise SourceError(
            f"{SOURCE_NAME} sayfasından menü çıkarılamadı. HTML değişmiş veya şehir sayfası boş olabilir."
        )
    return all_records
