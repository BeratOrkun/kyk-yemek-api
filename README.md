# KYK Yemek Menü API & Otomatik Veri Dağıtım CDN'i

Bu proje, herkese açık KYK menü kaynaklarından (`kepce.org`, `kykyurtmenu.com`, `kykyemek.com`) günlük yemek listelerini toplayan, hem **GitHub Actions ile sıfır sunucu maliyetli statik JSON CDN** sağlayan hem de istenirse **FastAPI REST API** olarak sunulabilen bağımsız bir servistir.

## ⚡ Canlı Statik JSON CDN (Ücretsiz & Sıfır Bekleme)
Her gün GitHub Actions tarafından otomatik olarak güncellenen statik JSON dosyaları:

* **Günün Tüm Menüleri (Hafif & Hızlı):**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/kyk_today.json`
* **Geçmiş & Arşiv Menüleri:**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/kyk_menus.json`
* **Aktif Şehirler Listesi:**  
  `https://raw.githubusercontent.com/BeratOrkun/kyk-yemek-api/main/data/cities.json`

> **CORS:** GitHub Raw CDN tüm domainlerden gelen `fetch()` isteklerine doğrudan izin verir (`access-control-allow-origin: *`). İstediğiniz herhangi bir web sitesinden, mobil uygulamadan veya frontend projesinden sunucusuz olarak tüketebilirsiniz.

## Araştırılan kaynaklar ve öncelik sırası

1. **Kepçe JSON API (ilk tercih):** `GET https://kepce.org/api/v1/menus?city=ankara&date=today`. Kepçe GitHub README dosyasında bu endpoint'i ve JSON cevap yapısını açıkça gösteriyor. Servis her sorguda yalnızca istenen şehir/tarih menüsünü çağırır; ham JSON için `/api/v1/kepce`, sadeleştirilmiş menü için `/api/v1/menu` kullanılır. Uygulama cevabında Kepçe'ye görünür atıf ve aktif bağlantı bulunur. Kepçe verisi kalıcı DB'ye kopyalanmaz; 10 dakikalık süreç içi cache kullanılır.
2. **kykyemek.com (yedek):** Açık kaynaklı bir scraper'ın kullandığı `Menu/GetDailyMenu/{city}?city={city}&mealType={false|true}` endpoint'i var. Örnek scraper'da `false` kahvaltı, `true` akşam yemeği olarak eşlenmiş. Site SSS sayfasında resmî uygulama olmadığını ve tüm illerin verisine erişemediğini belirtiyor.
3. **kykyurtmenu.com (ikinci yedek):** Herkese açık şehir sayfaları ve `/ankara/kahvalti`, `/ankara/aksam` gibi öğün sayfaları sunar. SSS sayfasında saatlik güncelleme ve resmî sistem entegrasyonu iddiası vardır; ancak bu projede doğrulanmış, herkese açık API adresi tespit edilmedi. Bu nedenle HTML parser kullanılır.
4. **Elle veri girişi:** Üç kaynaktan da veri yoksa yönetici endpoint'i üzerinden menüyü JSON ile girebilirsiniz.

Kepçe kullanım koşulları API/RSS kanallarını, makul istek sıklığını ve görünür `kepce.org` atfını zorunlu tutuyor. Uygulamanızın kullanıcı arayüzünde bu atfı ve aktif bağlantıyı kaldırmayın; bütün veritabanını topluca kopyalamayın veya Kepçe'ye gitme ihtiyacını ortadan kaldıracak şekilde aynalamayın. Bu proje Kepçe'nin kaynak kodunu kopyalamaz; herkese açık API'sini çağırır.

## İçerik

- FastAPI REST API ve `/docs` Swagger arayüzü
- 81 şehir ismini normalize eden yardımcı fonksiyon
- Şehir/öğün/tarih sorgulama
- İki scraper adaptörü
- SQLite önbellek
- Veri önceliği: `manual > kykyemek > kykyurtmenu`
- Zamanlanmış senkronizasyon
- API anahtarı ile yönetici endpoint'leri
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
| `GET /api/v1/kepce?city=ankara&date=today` | Kepçe JSON API cevabını atıfla ilet |
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

- Kepçe canlı JSON API'si `/api/v1/menus?city=...&date=...` şeklinde çağrılır. `/api/v1/kepce` ham JSON çıktısını verir. Bu veri için 10 dakikalık bellek cache'i vardır.
- `kykyemek` parser'ı `.card.cardStyle.mainPageColor`, `.date` ve `p[style*='color:#503C3C']` alanlarını temel alır. Bu CSS sınıfları değişirse `app/scrapers/kykyemek.py` güncellenmelidir.
- `kykyurtmenu` adaptörü `/{şehir}/kahvalti` ve `/{şehir}/aksam` HTML sayfalarının görünür metnini okur. Bu kaynak için herkese açık API doğrulanmadığından HTML değişikliklerine daha duyarlıdır.
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

Mobil uygulama → senin FastAPI API'n → Kepçe JSON API (10 dk bellek cache'i) → gerekirse kykyemek/kykyurtmenu HTML adaptörleri → yerel SQLite cache.

Kepçe'den gelen veriyi kalıcı bir kopya hâline getirmek yerine sadece sorgulanan gün için API üzerinden tüket. Uygulamanın menü ekranında görünür **“Veri: Kepçe”** metni ve `https://kepce.org` bağlantısı göster. Diğer HTML kaynaklarının menüleri kendi SQLite cache'inde tutulur. Mobil uygulama üçüncü taraf kaynaklara doğrudan bağlanmaz; yalnızca senin API'ni çağırır.

## Kullanım ve doğruluk notu

Kaynakların kullanım koşullarını, yeniden yayımlama ve ticari kullanım izinlerini kontrol et. GSB/KYGM logosu veya resmî kurum onayı varmış gibi sunma. Menü, fiilen yemekhanede sunulan yemekle değişebilir; öğrenciye bu uyarıyı göster. Bu kod örnek/teknik entegrasyon amacıyla hazırlanmıştır.
