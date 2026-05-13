# Çelebi Akıllı Vardiya ve Lojistik Planlama Sistemi

Bu klasör Streamlit tabanlı ilk prototipi içerir. Uygulama Departure, Qualifications, hakediş, servis ve güzergah CSV dosyalarını okuyarak haftalık vardiya/servis planı üretir.

## İçerik

- `app.py` — Streamlit arayüzü
- `core.py` — veri okuma, hakediş hesaplama, yetkinlik eşleştirme, vardiya ve servis algoritması
- `data/` — örnek CSV dosyaları
- `assets/` — logo ve uçak görselleri
- `requirements.txt` — gerekli Python paketleri

## Lokal Kurulum

```bash
cd celebi_yhm_shift_system
python -m venv .venv
.venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud Deploy

1. Bu klasörü GitHub reposuna yükle.
2. Streamlit Cloud'da repository seç.
3. Branch: `main`
4. Main file path: `app.py`
5. Deploy.

## Ana Özellikler

- Kurumsal lacivert/beyaz tema
- Çelebi logosu ve hareketli uçak arka planı
- CSV/Excel veri yükleme paneli
- Kontuar hakediş hesaplama
- Qualifications dosyasına göre yetkinlik kontrolü
- Havuz uçakları için Supervisor zorunluluğu
- Personel rota koduna göre servis seçimi
- Servis 4 kişi altı ise Toplu Taşıma notu
- DO/izin/tatil talepleri
- Manuel personel ve atama düzenleme
- Excel ve CSV rapor indirme
- Delay/devir öneri paneli

## Not

Bu bir ilk çalışan prototiptir. Gerçek operasyon öncesinde hakediş kuralları, dinlenme/shift blokları ve servis saatleri saha yöneticisi tarafından test edilmelidir.
