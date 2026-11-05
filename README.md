# KYK Yemek Menü API & Otomatik Veri Dağıtım CDN'i

Bu proje, herkese açık KYK menü kaynaklarından (`kykyemek.com`, `kykyurtmenu.com`, açık yurt havuzları) günlük yemek listelerini toplayan, hem **GitHub Actions ile sıfır sunucu maliyetli statik JSON CDN** sağlayan hem de istenirse **FastAPI REST API** olarak sunulabilen bağımsız bir servistir.

## ⚡ Canlı Statik JSON CDN (Ücretsiz & Sıfır Bekleme)
Her gün GitHub Actions tarafından otomatik olarak güncellenen statik JSON dosyaları:

* **Günün Tüm Menüleri (Hafif & Hızlı):**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/kyk_today.json`
* **Geçmiş & Arşiv Menüleri:**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/kyk_menus.json`
* **Aktif Şehirler Listesi:**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/cities.json`

> **CORS:** GitHub Raw CDN tüm domainlerden gelen `fetch()` isteklerine doğrudan izin verir (`access-control-allow-origin: *`). İstediğiniz herhangi bir web sitesinden, mobil uygulamadan veya frontend projesinden sunucusuz olarak tüketebilirsiniz.

## Veri Kaynakları ve Öncelik Sırası

1. **kykyemek.com (Birincil Kaynak):** İllerin aylık kahvaltı ve akşam menülerini detaylı ve düzenli olarak yayınlayan ana kaynaktır.
2. **kykyurtmenu.com (İkincil / Yedek):** Şehir ve öğün bazlı herkese açık sayfalar üzerinden ek illerin verilerini çeker.
3. **Açık Veri Havuzları (Yedek):** Henüz yerel listesi açıklanmamış iller için genel KYK standart menü yedeğini sağlar.
4. **Manuel Yönetici Girişi:** Özel durumlarda API üzerinden elle menü düzeltmesi yapılabilir.

## İçerik

- FastAPI REST API ve `/docs` Swagger arayüzü
- 81 şehir ismini normalize eden yardımcı fonksiyon
- Şehir/öğün/tarih sorgulama
- Çoklu scraper adaptörü
- SQLite önbellek
- Veri önceliği: `manual > kykyemek > kykyurtmenu`
- Otomatik GitHub Actions senkronizasyonu
- Kaynak durumunu gösteren `/api/v1/sources`

**Önemli:** 81 şehir adının kabul edilmesi 81 ilde kaynak verisi bulunduğu anlamına gelmez. KYK Yemek sitesi de tüm illere erişemediğini belirtiyor.

## 1. Kurulum

Python 3.10+ önerilir.

```bash
cd kyk-yemek-api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows'ta dosyayı elle kopyalayabilirsin
```

`.env` içindeki `ADMIN_API_KEY` değerini değiştir. Güçlü anahtar üretmek için:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Uygulamayı başlat:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ardından `http://127.0.0.1:8000/docs` adresini aç. Sunucu ilk açıldığında `.env` içindeki `SYNC_CITIES` şehirlerini senkronize etmeyi dener.

## 2. API endpoint'leri

| İstek | Açıklama |
|---|---|
| `GET /health` | Servis ayakta mı? |
| `GET /api/v1/cities` | 81 ilin slug listesi |
| `GET /api/v1/menu/today?city=Ankara` | Bugünün kahvaltı ve akşam menüsü |
| `GET /api/v1/menu?city=Ankara&meal=breakfast` | Bugünün kahvaltısı |
| `GET /api/v1/menu?city=Ankara&meal=dinner` | Bugünün akşam yemeği |
| `GET /api/v1/menu?city=Ankara&meal=dinner&date=2026-11-05` | Belirli tarih/öğün |
| `GET /api/v1/menus/month?city=Ankara&year=2026&month=11` | Veritabanındaki aylık arşiv |
| `GET /api/v1/sources` | Yedek HTML kaynaklarının son hata/başarı durumu |
| `POST /api/v1/admin/sync?city=Ankara` | Bir şehri elle senkronize et |
| `POST /api/v1/admin/sync-all` | `.env` içindeki şehirleri senkronize et |
| `POST /api/v1/admin/import` | Elle menü ekle / düzelt |

### Yönetici senkronizasyonu

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/sync?city=Ankara" \
  -H "X-Admin-Key: .env-icindeki-ADMIN_API_KEY"
```

### Elle menü ekleme

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/import" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: .env-icindeki-ADMIN_API_KEY" \
  -d '{
    "city": "Ankara",
    "date": "2026-11-05",
    "meal": "dinner",
    "items": ["Mercimek çorbası", "Tavuk sote", "Pirinç pilavı"],
    "calories": 780
  }'
```

Elle girilen kayıt, kaynaklardan gelen kayıtlara göre yüksek önceliğe sahiptir.

## 3. Örnek JSON

Bu yalnızca cevap şemasını gösterir; gerçek menü verisi değildir.

```json
{
  "ok": true,
  "data": {
    "city": "Ankara",
    "city_slug": "Ankara",
    "meal": "dinner",
    "date": "2026-11-05",
    "items": ["Mercimek Çorbası", "Tavuk Sote"],
    "calories": 740,
    "source": "kykyemek",
    "source_url": "https://kykyemek.com/...",
    "fetched_at": "2026-11-05T...+00:00"
  }
}
```

## 4. Şehir ekleme ve tarama sıklığı

`.env` dosyası:

```env
SYNC_CITIES=Ankara,İstanbul,İzmir,Eskişehir,Antalya,Adana
SYNC_INTERVAL_MINUTES=120
CACHE_TTL_MINUTES=60
SOURCE_ORDER=kykyemek,kykyurtmenu
```

İlk denemede yalnızca Ankara ile başla. Sonra birkaç şehri ekleyip `/api/v1/sources` ve `/api/v1/admin/sync` cevaplarına bak. Tüm 81 ili aynı anda ve çok sık sorgulama; veri kaynağının kapsamı sınırlı olabilir ve gereksiz trafik yaratmamalısın.

## 5. Hata ayıklama

- `kykyemek` parser'ı `.cardDate`, `.food-main-text` ve `.food-detail-text` alanlarını temel alır. Bu sınıflar değişirse `app/scrapers/kykyemek.py` güncellenmelidir.
- `kykyurtmenu` adaptörü `/{şehir}/kahvalti` ve `/{şehir}/aksam` HTML sayfalarının metnini okur.
- Hiçbir kaynak veri vermezse sistem uydurma menü üretmez; 404 döndürür. Kaynak hatasını `/api/v1/sources` üzerinden görebilirsin.
- Bir kaynak bozulursa diğer kaynak denenmeye devam eder.
- CAPTCHA, giriş duvarı veya erişim kısıtlamasını aşmaya çalışma. İstek sıklığını makul tut.

Testleri çalıştır:

```bash
pip install pytest
pytest -q
```

## 6. Railway / Render dağıtımı

### Railway

1. Projeyi GitHub'a gönder.
2. Railway'de **New Project → Deploy from GitHub Repo** seç.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Variables bölümünde `.env.example` içindeki değişkenleri tanımla.
5. Kalıcı Volume oluşturup `/data` yoluna bağla ve `DATABASE_PATH=/data/kyk.db` ayarla.
6. Domain oluştur; `/health`, `/docs` ve `/api/v1/sources` ile test et.

### Render

Build command: `pip install -r requirements.txt`

Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

SQLite dosyası kalıcı olsun istiyorsan persistent disk bağlamalısın. Disk olmadan instance yeniden başladığında dosya silinebilir. Daha ciddi kullanımda PostgreSQL/Supabase adaptörü eklemeni öneririm.

## 7. React Native / Expo kullanımı

```js
const API_BASE = "https://SENIN-API-DOMAININ";

export async function getTodayMenu(city) {
  const url = `${API_BASE}/api/v1/menu/today?city=${encodeURIComponent(city)}`;
  const response = await fetch(url);
  const json = await response.json();
  if (!response.ok) {
    throw new Error(json.detail?.message || "Menü alınamadı");
  }
  return json;
}
```

Örnek:

```js
const result = await getTodayMenu("Ankara");
console.log(result.menus.breakfast?.items);
console.log(result.menus.dinner?.items);
```

Arayüzde `source` ve `fetched_at` alanlarını göster. Böylece kullanıcı verinin hangi kaynaktan ve ne zaman alındığını görür.

## 8. Önerilen mimari

Frontend / Mobil Uygulama → Doğrudan GitHub Actions CDN (`data/kyk_today.json`) veya senin FastAPI API'n → `kykyemek` ve `kykyurtmenu` adaptörleri → yerel SQLite ve JSON cache.

## Kullanım ve doğruluk notu

Kaynakların kullanım koşullarını, yeniden yayımlama ve ticari kullanım izinlerini kontrol et. GSB/KYGM logosu veya resmî kurum onayı varmış gibi sunma. Menü, fiilen yemekhanede sunulan yemekle değişebilir; öğrenciye bu uyarıyı göster. Bu kod örnek/teknik entegrasyon amacıyla hazırlanmıştır.
