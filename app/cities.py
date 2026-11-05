from __future__ import annotations
import re
import unicodedata

# Türkiye'nin 81 ili. Kaynakların tamamında veri bulunduğu anlamına GELMEZ.
CITY_NAMES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya",
    "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum",
    "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir",
    "Gaziantep", "Giresun", "Gümüşhane", "Hakkâri", "Hatay", "Iğdır", "Isparta", "İstanbul",
    "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kırıkkale",
    "Kırklareli", "Kırşehir", "Kilis", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
    "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize",
    "Sakarya", "Samsun", "Şanlıurfa", "Siirt", "Sinop", "Sivas", "Şırnak", "Tekirdağ",
    "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak"
]


def slugify_city(value: str) -> str:
    value = value.strip().replace("ı", "i").replace("İ", "I")
    value = value.replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G")
    value = value.replace("ü", "u").replace("Ü", "U").replace("ö", "o").replace("Ö", "O")
    value = value.replace("ç", "c").replace("Ç", "C")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "", value)
    return value.lower()


_CITY_BY_SLUG = {slugify_city(name): name for name in CITY_NAMES}


def canonical_city(value: str) -> tuple[str, str]:
    slug = slugify_city(value)
    if slug not in _CITY_BY_SLUG:
        raise ValueError(f"Geçersiz şehir: {value}. Türkiye'nin 81 ilinden birini girin.")
    name = _CITY_BY_SLUG[slug]
    # Bazı eski kaynaklar URL'de özel yazım bekleyebilir; ASCII slug yeterli.
    return name, slug.capitalize()
