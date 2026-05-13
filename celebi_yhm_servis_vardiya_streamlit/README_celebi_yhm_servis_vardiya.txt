Çelebi YHM Servise Uyumlu Vardiya Planlama Sistemi

Streamlit Cloud kurulum:
1) GitHub reposu oluştur.
2) Bu iki dosyayı repoya yükle:
   - celebi_yhm_servis_vardiya_app.py
   - requirements_celebi_yhm.txt
3) Streamlit Cloud > New app bölümünde:
   - Repository: GitHub repo linkin
   - Branch: main
   - Main file path: celebi_yhm_servis_vardiya_app.py
4) requirements_celebi_yhm.txt dosyasının adını Streamlit'in otomatik okuması için requirements.txt yapman önerilir.
5) Uygulama açılınca sol menüden şu dosyaları yükle:
   - DEPARTURE dosyası
   - QUALIFICATIONLAR-YHM dosyası
   - 20. HAFTA YHM dosyası
   - Hakediş dosyası
   - İstersen Çelebi logo PNG/JPG

Ana kurallar:
- Geliş servisleri: 02:30, 04:30, 06:30, 08:00, 10:00, 11:30, 14:00, 16:30, 20:00, 23:59
- Gidiş servisleri: 00:30, 02:30, 04:30, 08:30, 14:30, 17:00, 19:30, 20:30, 23:00
- Full-time: min 40, max 50 saat
- Part-time: max 25 saat
- Vardiyalar arası minimum 11 saat dinlenme
- 6 saat ve üzeri vardiyada varsayılan 1 saat mola düşülür

Main file path:
celebi_yhm_servis_vardiya_app.py
