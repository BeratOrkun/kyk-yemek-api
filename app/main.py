from __future__ import annotations
from contextlib import asynccontextmanager
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Literal
import secrets

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .cities import CITY_NAMES, canonical_city
from .config import settings
from .database import init_db, get_menu, get_month, get_source_status, upsert_menu
from .service import maybe_sync_city, sync_city

TZ = ZoneInfo("Europe/Istanbul")
_stop_event = threading.Event()
_sync_thread: threading.Thread | None = None


class MenuImport(BaseModel):
    city: str
    date: date
    meal: Literal["breakfast", "dinner"]
    items: list[str] = Field(min_length=1)
    calories: int | None = Field(default=None, ge=0, le=10000)
    source_url: str | None = None


def _now_date() -> date:
    return datetime.now(TZ).date()


def _require_admin(candidate: str | None) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY sunucuda ayarlanmamış; yönetim endpoint'i kapalı.")
    if not candidate or not secrets.compare_digest(candidate, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Geçersiz yönetici anahtarı.")


def _background_sync() -> None:
    for city in settings.sync_city_names:
        try:
            sync_city(city, _now_date().isoformat())
        except Exception:
            # Bir şehir hatası diğer şehirlerin senkronizasyonunu durdurmasın.
            continue


def _scheduler_loop() -> None:
    interval_seconds = max(15, settings.sync_interval_minutes) * 60
    while not _stop_event.is_set():
        _background_sync()
        _stop_event.wait(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sync_thread
    init_db()
    _stop_event.clear()
    _sync_thread = threading.Thread(target=_scheduler_loop, name="kyk-menu-sync", daemon=True)
    _sync_thread.start()
    yield
    _stop_event.set()
    if _sync_thread and _sync_thread.is_alive():
        _sync_thread.join(timeout=2)


app = FastAPI(
    title="KYK Yemek Menü API",
    description="Üçüncü taraf açık menü kaynaklarını normalize ederek sunan topluluk API'si. Resmî GSB API'si değildir.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "KYK Yemek Menü API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "timezone": "Europe/Istanbul", "version": app.version}


@app.get("/api/v1/cities")
def cities():
    return {
        "count": len(CITY_NAMES),
        "note": "Bu liste Türkiye'nin illeridir; veri kaynaklarının tüm şehirleri desteklediği anlamına gelmez.",
        "cities": [{"name": c, "slug": canonical_city(c)[1]} for c in CITY_NAMES],
    }


@app.get("/api/v1/menu")
def menu(
    city: str = Query(..., description="Örn. Ankara, İstanbul, Eskişehir"),
    meal: Literal["breakfast", "dinner"] = Query(...),
    menu_date: date | None = Query(default=None, alias="date"),
):
    try:
        city_name, city_slug = canonical_city(city)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    requested_date = menu_date or _now_date()
    # Yönetici tarafından elle düzeltilmiş kayıt, canlı kaynaklardan üstündür.
    manual_record = get_menu(city_slug, meal, requested_date.isoformat())
    if manual_record and manual_record.get("source") == "manual":
        return {
            "ok": True,
            "data": manual_record,
            "attribution": {"name": "Yönetici girişi", "url": None, "text": "Bu menü yönetici tarafından girilmiştir."},
            "sync": None,
        }

    record = get_menu(city_slug, meal, requested_date.isoformat())
    sync_result = None
    if record is None:
        sync_result = maybe_sync_city(city_name, requested_date)
        record = get_menu(city_slug, meal, requested_date.isoformat())

    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Bu tarih/şehir/öğün için kaynaklardan menü bulunamadı.",
                "city": city_name,
                "date": requested_date.isoformat(),
                "meal": meal,
                "sync": sync_result,
            },
        )
    return {
        "ok": True,
        "data": record,
        "attribution": {"name": "Veri kaynağı", "url": record.get("source_url"), "text": "Menü üçüncü taraf kaynaktan alınmıştır."},
        "sync": sync_result,
    }


@app.get("/api/v1/menu/today")
def today(city: str = Query(...)):
    today_date = _now_date()
    results = {}
    errors = {}
    for meal_name in ("breakfast", "dinner"):
        try:
            results[meal_name] = menu(city=city, meal=meal_name, menu_date=today_date)["data"]
        except HTTPException as exc:
            errors[meal_name] = exc.detail
    if not results:
        raise HTTPException(status_code=404, detail={"message": "Bugün için menü bulunamadı.", "errors": errors})
    first = next(iter(results.values()))
    return {"ok": True, "city": first["city"], "date": today_date.isoformat(), "menus": results, "missing": errors}


@app.get("/api/v1/menus/month")
def month(
    city: str = Query(...),
    year: int | None = Query(default=None, ge=2020, le=2100),
    month_value: int | None = Query(default=None, alias="month", ge=1, le=12),
):
    try:
        city_name, city_slug = canonical_city(city)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    current = _now_date()
    selected_year = year or current.year
    selected_month = month_value or current.month
    records = get_month(city_slug, selected_year, selected_month)
    if not records:
        maybe_sync_city(city_name)
        records = get_month(city_slug, selected_year, selected_month)
    return {
        "ok": True,
        "city": city_name,
        "year": selected_year,
        "month": selected_month,
        "count": len(records),
        "data": records,
    }


@app.get("/api/v1/sources")
def sources():
    return {
        "official_gsb_api": False,
        "sources": get_source_status(),
        "configured_order": settings.source_names,
        "note": "Kaynak durumu son senkronizasyon denemesini gösterir; resmî doğruluk garantisi değildir.",
    }


@app.post("/api/v1/admin/sync")
def admin_sync(
    city: str = Query(...),
    menu_date: date | None = Query(default=None, alias="date"),
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(x_admin_key)
    try:
        return sync_city(city, (menu_date or _now_date()).isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/admin/sync-all")
def admin_sync_all(x_admin_key: str | None = Header(default=None)):
    _require_admin(x_admin_key)
    return {"results": [sync_city(city, _now_date().isoformat()) for city in settings.sync_city_names]}


@app.post("/api/v1/admin/import")
def admin_import(payload: MenuImport, x_admin_key: str | None = Header(default=None)):
    _require_admin(x_admin_key)
    try:
        city_name, city_slug = canonical_city(payload.city)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = {
        "city": city_name,
        "meal": payload.meal,
        "date": payload.date.isoformat(),
        "items": [item.strip() for item in payload.items if item.strip()],
        "calories": payload.calories,
        "source": "manual",
        "source_url": payload.source_url,
        "fetched_at": datetime.now(TZ).isoformat(),
    }
    if not record["items"]:
        raise HTTPException(status_code=422, detail="En az bir yemek adı gerekli.")
    upsert_menu(record, city_slug)
    return {"ok": True, "message": "Menü kaydedildi.", "data": record}
