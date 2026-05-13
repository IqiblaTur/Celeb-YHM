Çelebi YHM AI Servis Uyumlu Vardiya Planlama v4

Kurulum:
1) GitHub reposuna şu iki dosyayı yükle:
   - celebi_yhm_ai_servis_vardiya_app_v4.py
   - requirements.txt

2) Streamlit Cloud > New app:
   Main file path: celebi_yhm_ai_servis_vardiya_app_v4.py

3) Varsayılan giriş:
   Kullanıcı ID: YHMADMIN
   Şifre: 1234

4) Yayına almadan önce Streamlit Secrets içine güvenli kullanıcı/şifre ekle:
   AUTH_USER_IDS = "YHMADMIN,PLANLAMA,YUSUF"
   AUTH_PASSWORD = "guclu_sifre"

V4 yenilikleri:
- Modern Ana Sayfa eklendi.
- Ana Sayfadan Planlama sayfasına geçiş eklendi.
- Yüklenen Çelebi logosu arayüzde kullanılıyor. Logo yüklenmezse gömülü logo görünür.
- Kullanıcının gönderdiği uçak görselleri gömülü asset olarak koda eklendi.
- Uçaklar tüm sayfalarda düşük opaklıkla arka planda animasyonlu şekilde uçuyor.
- Planlama sayfasında v3 operasyon kuralları korunur: havuz uçakları, supervisor şartı, servis uyumu, STD-3:10, STD+20, 11 saat dinlenme, full/part saat limitleri, AI delay advisor, Excel/PDF rapor.
