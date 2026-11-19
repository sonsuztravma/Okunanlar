# Sonsuz Okumalar - Sesli Kitaplar Arşivi

2025 ve 2026 yıllarında dinlenen sesli kitapların detaylı arşivi, arama, filtreleme ve dinamik istatistik uygulaması.

Canlı Demo: [https://sonsuztravma.github.io/Okunanlar/](https://sonsuztravma.github.io/Okunanlar/)

---

## 📥 Anna's Archive Türkçe Kitap İndirici (Alt Uygulama)

Anna's Archive API tabanlı, toplu arama, format filtreleme ve doğrudan klasöre otomatik indirme uygulaması:

1. Klasördeki **`Anna_Kitap_Indirici.bat`** dosyasına çift tıklayın.
2. Web arayüzü otomatik olarak açılacaktır: (`http://localhost:3000`)
3. **Özellikler:**
   - **Toplu Kitap Arama & İndirme:** Kitap adlarını satır satır yapıştırın veya `.txt`/`.csv` listesi yükleyin.
   - **Klasör Seçimi:** Kitapların indirileceği klasörü Windows Klasör Seçici ile seçebilir veya doğrudan yol belirtebilirsiniz (Varsayılan: `D:\AI_Projelerim\Okunanlar\kitaplar`).
   - **Çoklu Format Desteği:** Her kitap için **EPUB, PDF, MOBI, AZW3, CBR/CBZ, FB2, DJVU** formatlarını seçebilir; "İlk Uygun Formatı İndir" veya "Seçilen Tüm Formatları İndir" stratejilerini kullanabilirsiniz.
   - **Canlı İlerleme Takibi:** Anlık indirme hızları, yüzdeleri ve işlem günlükleri (Server-Sent Events ile canlı akış).
   - **Tekli Arama:** Kapak görselleri ve detaylı meta verilerle tekil arama ve tek tıkla klasöre indirme.

---

## ⚡ Kolay Kitap Ekleme & Güncelleme (Yönetim Paneli)

Karmaşık komutlar çalıştırmadan, tek tıkla arayüz üzerinden kitap eklemek için:

1. Klasördeki **`Kitap_Ekle_Yonetici.bat`** dosyasına çift tıklayın.
2. Açılan web arayüzünde (`http://localhost:5000`):
   - **CSV ile Toplu Ekleme:** Storytel'den indirdiğiniz yeni bir CSV dosyasını sürükleyip bırakın. **Önceki kitaplarınız asla silinmez/kaybolmaz**, havuzda birleştirilir.
   - **Tek Kitap Ekleme:** Yalnızca sesli kitabın **ISBN** numarasını girin; kapak, yazar, arka kapak yazısı, yayınevi ve etiketler internetten otomatik çekilir.
   - **GitHub'a Gönder:** "GitHub'a Gönder" butonuna basarak canlı sitenizi tek tıkla güncelleyin.

---

## Özellikler

- **Gelişmiş Arama:** Başlık, yazar, konu etiketleri, arka kapak ve yayınevi tanıtım metinlerinde Türkçe karakter duyarsız arama ve metin içi vurgulama.
- **Kriterlere Göre Filtreleme:** Dinleme yılı, ana kategori, alt kategori, yazar, seslendiren, basılı yayınevi, yayın yılı aralığı, sayfa sayısı ve dinleme süresi.
- **Dinamik İstatistikler:**
  - Kitap sayısı, dinleme süresi (saat) veya sayfa sayısı bazında metrik seçimi
  - Dinleme yılına (2025 vs 2026) göre karşılaştırmalar
  - Tıklanabilir grafik çubukları ile anında filtreleme
  - Kategori, yazar, seslendiren, yayınevi, dinleme süresi ve yayın on yılı dağılımları
- **Çift Kapak Desteği:** Sesli kitap kapağı ve basılı kitap kapağı geçişi.
- **Mobil ve Masaüstü Uyumlu:** Modern responsive arayüz, alttan açılan mobil filtre çekmecesi ve detay kartı.
- **Tam Çevrimdışı Çalışma:** Tüm kapak görselleri ve kitap verileri yerel depolanır.
