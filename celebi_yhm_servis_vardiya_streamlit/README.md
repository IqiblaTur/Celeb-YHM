# YHM-Shift | Akıllı Vardiya ve Servis Planlama Sistemi

Bu paket GitHub ve Streamlit Cloud için hazırlandı.

## İçerik

- `app.py` → Ana Streamlit uygulama kodu
- `requirements.txt` → Gerekli Python paketleri
- `.streamlit/config.toml` → Beyaz / lacivert tema ayarı
- Uçak görselleri ve Çelebi logosu
- `KURULUM.txt` → Basit kurulum adımları

## Lokal Çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud Deploy

1. Bu klasördeki tüm dosyaları GitHub reposuna yükleyin.
2. Streamlit Cloud'da yeni app oluşturun.
3. Repository seçin.
4. Branch: `main`
5. Main file path: `app.py`
6. Deploy edin.

## Not

Görseller uygulama koduyla aynı klasörde durmalıdır. Dosya adları değiştirilirse `app.py` içindeki görsel isimleri de güncellenmelidir.
