# YHM-Shift — Akıllı Vardiya ve Servis Planlama Sistemi

Bu proje, Çelebi YHM operasyonu için Streamlit tabanlı vardiya, uçak ekip ataması, servis planlama ve delay/disruption öneri panelidir.

## İçerik

- `app.py`: Ana Streamlit uygulaması
- `data/departure_sample.csv`: Yüklenen Departure dosyasından örnek veri
- `data/staff_sample.csv`: 49 kişilik örnek personel/yetkinlik matrisi
- `data/services_sample.csv`: 15 güzergah için geliş/gidiş servis saatleri
- `assets/`: Çelebi logosu ve uçak görselleri
- `.streamlit/config.toml`: Lacivert/beyaz tema ayarları
- `requirements.txt`: Streamlit Cloud ve lokal kurulum paketleri

## Lokal Çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud Deploy

1. Bu klasördeki dosyaları GitHub repository içine yükle.
2. Streamlit Cloud > Deploy an app ekranında:
   - Repository: GitHub repo linkin
   - Branch: `main`
   - Main file path: `app.py`
3. Deploy butonuna bas.

## Veri Formatları

### Departure
Uygulama `A/L`, `IN`, `OUT`, `STA`, `STD` kolonlarını otomatik okur. CSV noktalı virgül (`;`) ayracı ve Türkçe karakter kodlaması desteklenir.

### Personel
Zorunlu/önerilen kolonlar:

- `employee_id`
- `name`
- `route`
- `employment_type` (`FT` veya `PT`)
- `qualifications`
- `is_supervisor`
- `is_lead`
- `can_checkin`
- `special_airlines` (Etihad için `ETD` veya `ETIHAD`)
- `success_pct`
- `active`

### Servis
Kolonlar:

- `route`: ARN, ATS, AVC, BAG, BAH, BHC, BAY, BEY, BOL, ESY, HAL, MAG, SEF, SUL, AKZ
- `direction`: `ARRIVAL` veya `DEPARTURE`
- `time`: `HH:MM`
- `min_count`: servis kalkış kotası, varsayılan 4
- `capacity`
- `active`

## Kurallar

- Gate hazır bulunma zamanı: STD - 1 saat 35 dakika
- Gate bitiş: STD + 25 dakika
- İki vardiya arası minimum dinlenme: 11 saat
- Full-time haftalık maksimum: 50 saat; hedef minimum: 40 saat
- Part-time haftalık maksimum: 25 saat
- 6 saat ve üzeri vardiyada 1 saat yemek molası düşülür
- Pool flights: UZB, IAW, DAH, FAD, RAM, BRU, AWG
- Pool flight ekibinde en az 1 Supervisor olmalıdır
- Etihad/ETD için `special_airlines` alanında ETD/ETIHAD yetkisi aranır
- Servis kotası: aynı güzergah ve saatte en az 4 personel

## Not

Bu sürüm backend/veritabanı gerektirmeyen, GitHub ve Streamlit Cloud'a doğrudan yüklenebilir çalışan prototiptir. Gerçek personel listesi ve gerçek servis saatleri Yönetim Paneli'nden içe aktarılabilir.
