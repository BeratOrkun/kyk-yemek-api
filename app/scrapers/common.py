from __future__ import annotations
import re
from datetime import date
from typing import Optional

TURKISH_MONTHS = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_turkish_date(value: str) -> Optional[date]:
    """'5 Kasım 2026 Perşembe' gibi tarihleri ISO date nesnesine çevirir."""
    if not value:
        return None
    text = value.strip().lower()
    text = text.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
    text = text.replace("ü", "u").replace("ö", "o").replace("ç", "c")
    match = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(20\d{2})\b", text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = TURKISH_MONTHS.get(month_name)
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def parse_calories(value: str | None) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"(\d{2,4})\s*kcal", value, re.IGNORECASE)
    return int(match.group(1)) if match else None
