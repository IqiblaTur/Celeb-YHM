# Teknik Gereksinim ve Mantıksal Mimari

## Proje
Çelebi Akıllı Vardiya ve Lojistik Planlama Sistemi

## Amaç
Uçak kalkış saatleri, personel yetkinlikleri, kontuar hakediş kuralları ve servis güzergah verilerini birleştirerek haftalık vardiya ve servis planı oluşturmak.

## Veri Girişleri
- Departure.csv: A/L, IN, OUT, STA, STD, A/C Type, yolcu/konfigürasyon bilgisi
- Qualifications.csv: Personel adı ve yetkinlik kodları
- hakedis.csv: Havayolu bazlı kontuar hakediş kuralları
- servis.csv: geliş/gidiş servis saatleri
- Guzergah.csv: personel güzergah kodları

## Ana Kurallar
- Hakediş kurallarına göre uçuş başına gerekli personel sayısı hesaplanır.
- Personel sadece yetkin olduğu havayoluna atanır.
- Havuz uçakları: UZB, IAW, DAH, FAD, RAM, BRU, AWG.
- Havuz uçaklarında en az bir Supervisor aranır.
- Servis kendi güzergah kodu üzerinden hesaplanır.
- Aynı güzergah + aynı servis saati için minimum 4 kişi yoksa Toplu Taşıma notu düşer.
- Full-time varsayılan haftalık üst limit: 50 saat.
- Part-time üst limit kullanıcı tarafından 25 saat yapılabilir.
- Çalışma süresinden 1 saat yemek molası düşülür.

## Çıktılar
- Haftalık personel shift tablosu
- Uçuş bazlı hakediş/atanan personel özeti
- Servis bazlı doluluk ve kalkar/kalkmaz tablosu
- Uyarılar listesi
- Excel ve CSV dışa aktarım

## Geliştirme Notları
Bu prototip açıklanabilir greedy algoritma kullanır. İleride PuLP veya OR-Tools ile tam matematiksel optimizasyon modeli eklenebilir.
