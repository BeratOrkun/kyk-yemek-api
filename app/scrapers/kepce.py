from __future__ import annotations
from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://kepce.org"
API_URL = f"{BASE_URL}/api/v1/menus"
SOURCE_NAME = "kepce"
CACHE_TTL_SECONDS = 600  # 10 dakika: API'ye sık istek göndermemek için
_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_cache_lock = Lock()


class SourceError(RuntimeError):
    pass


def fetch_raw(city_slug: str, requested_date: str = "today") -> tuple[Any, str]:
    key = (city_slug.lower(), requested_date)
    now = monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1], f"{API_URL}?city={city_slug.lower()}&date={requested_date}"

    url = API_URL
    try:
        response = requests.get(
            url,
            params={"city": city_slug.lower(), "date": requested_date},
            headers={"User-Agent": "KYKMenuReader/1.0", "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SourceError(f"Kepçe API HTTP hatası: {exc}") from exc
    except ValueError as exc:
        raise SourceError("Kepçe API geçerli JSON döndürmedi.") from exc

    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("menus", []))
    if not isinstance(payload, list):
        raise SourceError("Kepçe API beklenmeyen JSON biçimi döndürdü.")

    with _cache_lock:
        _cache[key] = (monotonic(), payload)
    return payload, response.url


def normalize_payload(payload: list[dict[str, Any]], city: str, requested_date: str, source_url: str) -> list[dict]:
    rows: list[dict] = []
    for menu in payload:
        status = str(menu.get("status", "approved")).lower()
        if status not in {"approved", "published", "active"}:
            continue

        meal_raw = str(menu.get("meal_type", "")).lower()
        if meal_raw in {"breakfast", "kahvalti", "kahvaltı"}:
            meal = "breakfast"
        elif meal_raw in {"dinner", "aksam", "akşam", "supper"}:
            meal = "dinner"
        else:
            continue

        serve_date = str(menu.get("serve_date") or requested_date)
        item_details: list[dict[str, Any]] = []
        item_names: list[str] = []
        for item in menu.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            detail = {
                "name": name,
                "amount": item.get("amount"),
                "calories": item.get("calories"),
                "price": item.get("price"),
                "category": item.get("category"),
                "is_alternative": bool(item.get("is_alternative", False)),
            }
            master = item.get("master_data") or {}
            if isinstance(master, dict):
                diet_flags = {
                    key: master[key]
                    for key in ("is_celiac", "is_vegan", "is_vegetarian")
                    if key in master
                }
                if diet_flags:
                    detail["dietary"] = diet_flags
            item_details.append(detail)
            item_names.append(name)

        if not item_names:
            continue
        calories = menu.get("calculated_calories")
        if calories is None:
            known = [x.get("calories") for x in item_details if isinstance(x.get("calories"), (int, float))]
            calories = sum(known) if known else None

        rows.append({
            "city": menu.get("city_name") or city,
            "city_slug": menu.get("city_slug") or city.lower(),
            "meal": meal,
            "date": serve_date,
            "items": item_names,
            "item_details": item_details,
            "calories": calories,
            "source": SOURCE_NAME,
            "source_status": status,
            "source_url": BASE_URL,
            "source_api_url": source_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def fetch_city_date(city: str, city_slug: str, menu_date: date) -> list[dict]:
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    date_param = "today" if menu_date == today else menu_date.isoformat()
    payload, source_url = fetch_raw(city_slug, date_param)
    rows = normalize_payload(payload, city, menu_date.isoformat(), source_url)
    return [row for row in rows if row["date"] == menu_date.isoformat()]
