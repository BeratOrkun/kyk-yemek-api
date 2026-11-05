from app.scrapers.kykyemek import parse_menu_html
from app.scrapers.kykyurtmenu import parse_city_page
from app.scrapers.common import parse_turkish_date


def test_turkish_date():
    assert parse_turkish_date("5 Kasım 2026 Perşembe").isoformat() == "2026-11-05"


def test_kykyemek_parser():
    html = '''<div class="card cardStyle mainPageColor">
      <p class="date">5 Kasım 2026 Perşembe</p>
      <p style="color:#503C3C; font-weight:700">Mercimek Çorbası</p>
      <p style="color:#503C3C; font-weight:700">Tavuk Sote</p>
      <p class="text-end">740 kcal</p>
    </div>'''
    rows = parse_menu_html(html, "Ankara", "dinner", "https://example.test")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-05"
    assert rows[0]["items"] == ["Mercimek Çorbası", "Tavuk Sote"]
    assert rows[0]["calories"] == 740


def test_kykyurtmenu_parser():
    html = '''<h1>Ankara KYK Kahvaltı Menüsü</h1>
    <p>5 Kasım 2026 - Kahvaltı Yemek Listesi</p>
    <div><p>Kahvaltı</p><p>650 kcal</p><p>1. Yemek</p>
    <p>Haşlanmış Yumurta</p><p>2. Yemek</p><p>Beyaz Peynir</p>
    <a>🏠 Ankara Ana Menü</a></div>'''
    rows = parse_city_page(html, "Ankara", "breakfast", "https://example.test/ankara/kahvalti")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-05"
    assert "Haşlanmış Yumurta" in rows[0]["items"]


def test_kepce_normalizer():
    from app.scrapers.kepce import normalize_payload
    payload = [{
        "city_name": "Ankara",
        "city_slug": "ankara",
        "serve_date": "2026-11-05",
        "meal_type": "dinner",
        "status": "approved",
        "items": [{
            "name": "Mercimek Çorbası",
            "amount": "200 ml",
            "calories": 140,
            "price": 18.0,
            "category": "ÇORBA",
            "is_alternative": False,
            "master_data": {"is_vegan": True},
        }],
        "calculated_calories": 140,
    }]
    rows = normalize_payload(payload, "Ankara", "2026-11-05", "https://kepce.org/api/v1/menus")
    assert len(rows) == 1
    assert rows[0]["items"] == ["Mercimek Çorbası"]
    assert rows[0]["item_details"][0]["price"] == 18.0
    assert rows[0]["calories"] == 140
