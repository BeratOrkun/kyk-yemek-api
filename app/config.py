from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", "./data/kyk.db")
    sync_interval_minutes: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "120"))
    cache_ttl_minutes: int = int(os.getenv("CACHE_TTL_MINUTES", "60"))
    sync_cities: str = os.getenv("SYNC_CITIES", "Ankara")
    source_order: str = os.getenv("SOURCE_ORDER", "kykyemek,kykyurtmenu")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    @property
    def sync_city_names(self) -> list[str]:
        return [x.strip() for x in self.sync_cities.split(",") if x.strip()]

    @property
    def source_names(self) -> list[str]:
        return [x.strip().lower() for x in self.source_order.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
Path(settings.database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
