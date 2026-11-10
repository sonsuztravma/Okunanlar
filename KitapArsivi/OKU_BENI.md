# Sesli Kitap Arşivim

- **Uygulamayı açmak:** `uygulama/index.html` dosyasına çift tıklayın (internet gerekmez; kapaklar `uygulama/kapaklar/` içinde).
- **Veritabanı:** `veri/kitaplik.db` (SQLite; `arama` tablosu FTS5 tam metin arama içerir).
- **Yeni CSV ile güncelleme:** `toplayici.py` içindeki `CSV_YOL` dosyasını değiştirin, sonra:
  ```
  python toplayici.py   # internetten veri + kapak toplar (önbellekli, kaldığı yerden devam eder)
  python olustur.py     # sınıflandırır, veritabanı ve uygulama/veri.js üretir
  ```
- **Kategori/etiket kuralları:** `olustur.py` içindeki `ETIKET` ve `ALT_ONCELIK` sözlükleri.
- **Kaynaklar:** Storytel (yazar, özet/arka kapak, kapak, seslendiren, kategori, puan), Kitapyurdu (sayfa sayısı, basılı yayın tarihi, yayınevi, basılı kapak).
