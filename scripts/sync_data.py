#!/usr/bin/env python3
"""
KYK Yemek Menüleri - Otomatik Veri Senkronizasyon Scripti
Bu script GitHub Actions tarafından periyodik olarak çalıştırılır:
1. Kepçe API'den tüm şehirlerin güncel menülerini toplar.
2. Eksik şehirler için kykyurtmenu ve diğer kaynaklara başvurur.
3. Çıktıları data/kyk_today.json ve data/kyk_menus.json olarak depolar.
"""

from __future__ import annotations
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Proje kök dizinini Python yoluna ekle
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.cities import CITY_NAMES, slugify_city, canonical_city
from app.scrapers import kepce, kykyurtmenu

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kyk_sync")

TZ_ISTANBUL = ZoneInfo("Europe/Istanbul")
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TODAY_FILE = DATA_DIR / "kyk_today.json"
ARCHIVE_FILE = DATA_DIR / "kyk_menus.json"
CITIES_FILE = DATA_DIR / "cities.json"


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"{path.name} okunamadı, boş başlatılıyor: {e}")
    return {}


def save_json(path: Path, data: dict | list) -> None:
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)
    logger.info(f"{path.name} başarıyla kaydedildi ({path.stat().st_size} bayt).")


def fetch_kepce_bulk(today_iso: str) -> dict[str, dict]:
    """Kepçe API tek bir çağrıda birden fazla ilin menüsünü dönebilir."""
    import requests
    results: dict[str, dict] = {}
    try:
        url = "https://kepce.org/api/v1/menus?date=today"
        logger.info(f"Kepçe toplu menü sorgulanıyor: {url}")
        res = requests.get(url, headers={"User-Agent": "KYKMenuReader/1.0 (+public bot)"}, timeout=20)
        res.raise_for_status()
        payload = res.json()
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("menus", []))
        
        if not isinstance(payload, list):
            logger.warning("Kepçe beklenmeyen veri formatı döndürdü.")
            return results

        # Menüleri il bazında toparla
        for entry in payload:
            city_raw = entry.get("city_name") or entry.get("city_slug")
            if not city_raw:
                continue
            slug = slugify_city(city_raw)
            city_name = entry.get("city_name") or slug.capitalize()
            
            meal_type = str(entry.get("meal_type", "")).lower()
            meal_key = "breakfast" if meal_type in {"breakfast", "kahvalti", "kahvaltı"} else "dinner"
            
            items = []
            for it in (entry.get("items") or []):
                name = str(it.get("name", "")).strip()
                if name:
                    items.append(name)
            
            if not items:
                continue

            if slug not in results:
                results[slug] = {
                    "city": city_name,
                    "city_slug": slug,
                    "date": entry.get("serve_date") or today_iso,
                    "breakfast": None,
                    "dinner": None,
                }
            
            results[slug][meal_key] = {
                "items": items,
                "calories": entry.get("calculated_calories"),
                "source": "kepce",
                "source_url": "https://kepce.org",
                "item_details": entry.get("items", []),
                "bot_commentary": entry.get("bot_commentary"),
            }
        logger.info(f"Kepçe'den {len(results)} il için menü alındı.")
    except Exception as e:
        logger.error(f"Kepçe toplu sorgu hatası: {e}")
    return results


def main():
    now_istanbul = datetime.now(TZ_ISTANBUL)
    today_iso = now_istanbul.date().isoformat()
    logger.info(f"--- KYK Menü Senkronizasyonu Başladı: {today_iso} ({now_istanbul.strftime('%H:%M:%S')}) ---")

    # Mevcut verileri yükle (geçmiş verileri korumak için)
    existing_today = load_json(TODAY_FILE)
    existing_archive = load_json(ARCHIVE_FILE)
    
    # 1. Adım: Kepçe Toplu Çekim
    kepce_menus = fetch_kepce_bulk(today_iso)

    # Günün menüleri havuzu
    today_pool: dict[str, dict] = existing_today.get("menus", {}) if existing_today.get("date") == today_iso else {}

    # Kepçe verilerini ekle
    for slug, city_data in kepce_menus.items():
        if slug not in today_pool:
            today_pool[slug] = city_data
        else:
            # Öncelikli olarak güncelle
            if city_data.get("breakfast"):
                today_pool[slug]["breakfast"] = city_data["breakfast"]
            if city_data.get("dinner"):
                today_pool[slug]["dinner"] = city_data["dinner"]
            today_pool[slug]["city"] = city_data["city"]
            today_pool[slug]["date"] = today_iso

    # 2. Adım: Eksik veya önemli iller için kykyurtmenu dene
    priority_check_cities = [
        "Ankara", "İstanbul", "İzmir", "Eskişehir", "Antalya", "Bursa", "Konya",
        "Trabzon", "Samsun", "Kayseri", "Gaziantep", "Adana", "Kocaeli", "Sakarya",
        "Erzurum", "Diyarbakır", "Çanakkale", "Denizli", "Muğla", "Balıkesir"
    ]

    for city_name in priority_check_cities:
        slug = slugify_city(city_name)
        existing_city_data = today_pool.get(slug)
        needs_breakfast = not existing_city_data or not existing_city_data.get("breakfast")
        needs_dinner = not existing_city_data or not existing_city_data.get("dinner")

        if needs_breakfast or needs_dinner:
            try:
                logger.info(f"{city_name} için kykyurtmenu deneniyor...")
                records = kykyurtmenu.fetch_city(city_name, slug)
                if records:
                    if slug not in today_pool:
                        today_pool[slug] = {
                            "city": city_name,
                            "city_slug": slug,
                            "date": today_iso,
                            "breakfast": None,
                            "dinner": None,
                        }
                    for rec in records:
                        meal_key = rec["meal"]
                        if not today_pool[slug].get(meal_key):
                            today_pool[slug][meal_key] = {
                                "items": rec["items"],
                                "calories": rec.get("calories"),
                                "source": "kykyurtmenu",
                                "source_url": rec.get("source_url"),
                            }
                time.sleep(0.5)  # Nazik istek aralığı
            except Exception as e:
                logger.debug(f"{city_name} kykyurtmenu hatası: {e}")

    # Şehirler listesi JSON
    cities_list = []
    for c in CITY_NAMES:
        s = slugify_city(c)
        has_data = s in today_pool and (bool(today_pool[s].get("breakfast")) or bool(today_pool[s].get("dinner")))
        cities_list.append({"name": c, "slug": s, "has_today_menu": has_data})

    # Dosyaları hazırla
    today_output = {
        "last_updated": now_istanbul.isoformat(),
        "date": today_iso,
        "total_cities_with_menu": sum(1 for c in cities_list if c["has_today_menu"]),
        "menus": today_pool,
    }

    # Arşiv (tarihe göre sakla)
    if "archive" not in existing_archive:
        existing_archive = {"by_date": {}, "last_updated": now_istanbul.isoformat()}
    
    existing_archive["last_updated"] = now_istanbul.isoformat()
    existing_archive["by_date"][today_iso] = today_pool

    # Kaydet
    save_json(TODAY_FILE, today_output)
    save_json(ARCHIVE_FILE, existing_archive)
    save_json(CITIES_FILE, cities_list)

    logger.info(f"--- Senkronizasyon Tamamlandı! Toplam {today_output['total_cities_with_menu']} ilde menü hazır. ---")


if __name__ == "__main__":
    main()
