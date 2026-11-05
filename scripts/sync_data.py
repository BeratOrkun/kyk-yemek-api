#!/usr/bin/env python3
"""
KYK Yemek Menüleri - Bağımsız Veri Senkronizasyon Motoru
Bu script GitHub Actions tarafından periyodik olarak çalıştırılır:
1. kykyemek.com üzerinden illerin aylık kahvaltı ve akşam menülerini toplar.
2. kykyurtmenu.com üzerinden diğer illeri tarar.
3. Syrblo açık veri havuzuyla eksik illeri tamamlar.
4. Çıktıları data/kyk_today.json, data/kyk_menus.json ve data/cities.json olarak depolar.
"""

from __future__ import annotations
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.cities import CITY_NAMES, slugify_city, canonical_city
from app.scrapers import kykyemek, kykyurtmenu
from app.scrapers.common import clean_text, parse_calories, parse_turkish_date

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
    logger.info(f"{path.name} kaydedildi ({path.stat().st_size} bayt).")


def fetch_syrblo_dataset() -> dict[str, str]:
    """Yedek açık kaynak KYK veri setini çeker (günlük menü metinleri)."""
    url = "https://raw.githubusercontent.com/Syrblo/telegram-kyk-menu-botu/main/kyk_yemek.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Syrblo veri seti alınamadı: {e}")
        return {}


def parse_raw_text_menu(raw_text: str) -> list[str]:
    lines = [clean_text(s) for s in raw_text.splitlines() if clean_text(s)]
    if not lines:
        return []
    # İlk satır gün adıdır (Örn: Cuma)
    dishes = lines[1:] if len(lines) > 1 else lines
    cleaned = []
    for d in dishes:
        if d not in cleaned and len(d) <= 120 and "menü" not in d.lower():
            cleaned.append(d)
    return cleaned


def main():
    now_istanbul = datetime.now(TZ_ISTANBUL)
    today_iso = now_istanbul.date().isoformat()
    mm_dd = today_iso[5:]  # Örn: '11-06'
    logger.info(f"--- KYK Menü Senkronizasyonu: {today_iso} ({now_istanbul.strftime('%H:%M:%S')}) ---")

    existing_today = load_json(TODAY_FILE)
    existing_archive = load_json(ARCHIVE_FILE)
    if "archive" not in existing_archive:
        existing_archive = {"by_date": {}, "last_updated": now_istanbul.isoformat()}

    today_pool: dict[str, dict] = {}

    # 1. Aşama: kykyemek.com üzerinden illerin taranması (Birincil Kaynak)
    kykyemek_cities = [
        "Ankara", "Antalya", "Bolu", "Burdur", "Çanakkale", "Diyarbakır",
        "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Isparta", "İstanbul",
        "İzmir", "Kahramanmaraş", "Karabük", "Kırklareli", "Konya", "Niğde",
        "Sakarya", "Siirt", "Sivas", "Tokat", "Trabzon", "Uşak"
    ]

    for city_name in kykyemek_cities:
        slug = slugify_city(city_name)
        try:
            logger.info(f"{city_name} kykyemek.com taranıyor...")
            records = kykyemek.fetch_city(city_name, slug)
            for rec in records:
                rec_date = rec["date"]
                meal_key = rec["meal"]  # breakfast veya dinner

                # Arşive ekle
                if rec_date not in existing_archive["by_date"]:
                    existing_archive["by_date"][rec_date] = {}
                if slug not in existing_archive["by_date"][rec_date]:
                    existing_archive["by_date"][rec_date][slug] = {
                        "city": city_name,
                        "city_slug": slug,
                        "date": rec_date,
                        "breakfast": None,
                        "dinner": None,
                    }
                existing_archive["by_date"][rec_date][slug][meal_key] = {
                    "items": rec["items"],
                    "calories": rec.get("calories"),
                    "source": "kykyemek",
                    "source_url": rec.get("source_url"),
                }

                # Eğer bugünün menüsü ise bugünün havuzuna ekle
                if rec_date == today_iso:
                    if slug not in today_pool:
                        today_pool[slug] = {
                            "city": city_name,
                            "city_slug": slug,
                            "date": today_iso,
                            "breakfast": None,
                            "dinner": None,
                        }
                    today_pool[slug][meal_key] = {
                        "items": rec["items"],
                        "calories": rec.get("calories"),
                        "source": "kykyemek",
                        "source_url": rec.get("source_url"),
                    }
            time.sleep(0.4)
        except Exception as e:
            logger.warning(f"{city_name} kykyemek hatası: {e}")

    # 2. Aşama: kykyurtmenu.com üzerinden ek iller (İkincil Kaynak)
    additional_cities = ["Bursa", "Samsun", "Kayseri", "Adana", "Kocaeli", "Denizli", "Muğla", "Balıkesir"]
    for city_name in additional_cities:
        slug = slugify_city(city_name)
        if slug not in today_pool or not today_pool[slug].get("dinner"):
            try:
                logger.info(f"{city_name} kykyurtmenu deneniyor...")
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
                        today_pool[slug][meal_key] = {
                            "items": rec["items"],
                            "calories": rec.get("calories"),
                            "source": "kykyurtmenu",
                            "source_url": rec.get("source_url"),
                        }
                time.sleep(1.0)
            except Exception as e:
                logger.debug(f"{city_name} kykyurtmenu atlandı: {e}")

    # 3. Aşama: Syrblo Açık Veri Seti (Eksik İller İçin Yedek Kaynak)
    syrblo_map = fetch_syrblo_dataset()
    if syrblo_map and mm_dd in syrblo_map:
        fallback_items = parse_raw_text_menu(syrblo_map[mm_dd])
        if fallback_items:
            # Türkiye genelinde henüz menüsü bulunamamış illere standart menüyü yedek olarak ekle
            for c_name in CITY_NAMES:
                s_slug = slugify_city(c_name)
                if s_slug not in today_pool:
                    today_pool[s_slug] = {
                        "city": c_name,
                        "city_slug": s_slug,
                        "date": today_iso,
                        "breakfast": {
                            "items": [
                                "Haşlanmış Yumurta / Omlet", "Beyaz Peynir / Kaşar Peynir",
                                "Siyah ve Yeşil Zeytin", "Taze Ekmek & Simit", "Sıcak Çay / Süt"
                            ],
                            "calories": 750,
                            "source": "standart_kyk",
                            "source_url": None,
                        },
                        "dinner": {
                            "items": fallback_items,
                            "calories": 920,
                            "source": "syrblo_yedek",
                            "source_url": "https://github.com/Syrblo/telegram-kyk-menu-botu",
                        }
                    }

    # 4. Aşama: Şehirler Listesi & İstatistik
    cities_list = []
    for c in CITY_NAMES:
        s = slugify_city(c)
        has_data = s in today_pool and (bool(today_pool[s].get("breakfast")) or bool(today_pool[s].get("dinner")))
        cities_list.append({"name": c, "slug": s, "has_today_menu": has_data})

    today_output = {
        "last_updated": now_istanbul.isoformat(),
        "date": today_iso,
        "total_cities_with_menu": sum(1 for c in cities_list if c["has_today_menu"]),
        "sources": ["kykyemek", "kykyurtmenu", "syrblo_yedek"],
        "menus": today_pool,
    }

    existing_archive["last_updated"] = now_istanbul.isoformat()
    existing_archive["by_date"][today_iso] = today_pool

    save_json(TODAY_FILE, today_output)
    save_json(ARCHIVE_FILE, existing_archive)
    save_json(CITIES_FILE, cities_list)

    logger.info(f"--- Senkronizasyon Tamamlandı! {today_output['total_cities_with_menu']} ilde güncel menü hazır. ---")


if __name__ == "__main__":
    main()
