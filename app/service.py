from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from .config import settings
from .database import get_city_sync, mark_city_sync, mark_source, upsert_menu
from .cities import canonical_city
from .scrapers import kykyemek, kykyurtmenu

SCRAPERS = {"kykyemek": kykyemek, "kykyurtmenu": kykyurtmenu}


def sync_city(city_value: str, menu_date: str | None = None) -> dict[str, Any]:
    city_name, city_slug = canonical_city(city_value)
    selected_date = menu_date or datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()
    source_results = []
    total_saved = 0
    any_success = False
    errors = []

    for source_name in settings.source_names:
        scraper = SCRAPERS.get(source_name)
        if not scraper:
            source_results.append({"source": source_name, "ok": False, "error": "Bilinmeyen kaynak"})
            continue
        try:
            records = scraper.fetch_city(city_name, city_slug)
            saved = sum(1 for record in records if upsert_menu(record, city_slug))
            mark_source(source_name, True, saved=saved)
            any_success = True
            total_saved += saved
            source_results.append({"source": source_name, "ok": True, "received": len(records), "saved": saved})
        except Exception as exc:
            message = str(exc)[:700]
            mark_source(source_name, False, error=message)
            errors.append(f"{source_name}: {message}")
            source_results.append({"source": source_name, "ok": False, "error": message})

    mark_city_sync(city_slug, selected_date, any_success, "; ".join(errors) if errors else None)
    return {
        "city": city_name,
        "city_slug": city_slug,
        "ok": any_success,
        "records_saved": total_saved,
        "sources": source_results,
    }


def maybe_sync_city(city_value: str, menu_date: date | None = None, force: bool = False) -> dict[str, Any] | None:
    city_name, city_slug = canonical_city(city_value)
    selected_date = (menu_date or datetime.now(ZoneInfo("Europe/Istanbul")).date()).isoformat()
    if not force:
        state = get_city_sync(city_slug, selected_date)
        if state and state.get("last_attempt"):
            try:
                last_attempt = datetime.fromisoformat(state["last_attempt"])
                if datetime.now(timezone.utc) - last_attempt < timedelta(minutes=settings.cache_ttl_minutes):
                    return None
            except ValueError:
                pass
    return sync_city(city_name, selected_date)
