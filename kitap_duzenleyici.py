# -*- coding: utf-8 -*-
"""
Sonsuz Okumalar - Kitap Düzenleyici & Format Yöneticisi
Google Drive, Telegram, Anna's Archive ve harici kaynaklardan gelen kitapları düzenleme,
isimlendirme (Kitap Adı - Yazar), mükerrer temizleme, format filtreleme ve Calibre dönüştürme aracı.
"""

import os
import sys
import json
import re
import shutil
import subprocess
import hashlib
import time
import threading
import difflib
import unicodedata
import glob
import urllib.request as ur
import urllib.parse as up
import xml.etree.ElementTree as ET
from datetime import datetime

import fitz  # PyMuPDF
from flask import Flask, request, jsonify, render_template_string, send_from_directory, send_file, Response

# Temel Dizin Yapısı
KOK_DIZIN = os.path.dirname(os.path.abspath(__file__))
ARSIV_DIZIN = os.path.join(KOK_DIZIN, 'KitapArsivi')
DB_YOLU = os.path.join(ARSIV_DIZIN, 'veri', 'kitaplik.db')
ONBELLEK_DOSYASI = os.path.join(KOK_DIZIN, '.duzenleyici_onbellek.json')
GECMIS_DOSYASI = os.path.join(KOK_DIZIN, '.duzenleyici_gecmis.json')

# KitapArsivi modülleri (toplayici ve olustur)
if ARSIV_DIZIN not in sys.path:
    sys.path.insert(0, ARSIV_DIZIN)

try:
    import toplayici
    import olustur
except Exception as e:
    toplayici = None
    olustur = None
    print(f"[!] KitapArsivi toplayici/olustur yüklenemedi: {e}")

# Calibre ebook-convert yolu tespiti (İhtiyaç duyulduğunda dinamik sorgulanır)
CALIBRE_YOLU = None

def calibre_yolu_bul():
    olasi_calibre_yollari = [
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
        shutil.which("ebook-convert"),
    ]
    for cy in olasi_calibre_yollari:
        if cy and os.path.exists(cy):
            return cy
    return None

# Desteklenen uzantılar
DESTEKLENEN_UZANTILAR = {'.pdf', '.epub', '.mobi', '.azw3', '.txt', '.docx', '.fb2', '.cbr', '.cbz'}

# ==============================================================================
# 1. TÜRKÇE VE METİN NORMALİZASYON YARDIMCILARI
# ==============================================================================
def turkce_kucuk(s):
    if not s:
        return ""
    return s.replace('İ', 'i').replace('I', 'ı').lower()

def turkce_baslik(s):
    """Her kelimenin ilk harfini Türkçe kurallarına göre büyütür."""
    if not s:
        return ""
    kelimeler = s.split()
    sonuc = []
    kucuk_baglaclar = {'ve', 'ile', 'veya', 'yahut', 'ki', 'de', 'da', 'mi', 'mu', 'mü', 'mı'}
    for i, k in enumerate(kelimeler):
        k_lower = turkce_kucuk(k)
        if i > 0 and k_lower in kucuk_baglaclar:
            sonuc.append(k_lower)
            continue
        ilk = k[:1]
        kalan = k[1:]
        if ilk == 'i':
            ilk = 'İ'
        elif ilk == 'ı':
            ilk = 'I'
        else:
            ilk = ilk.upper()
        sonuc.append(ilk + turkce_kucuk(kalan))
    return " ".join(sonuc)

def norm(s):
    """Arama ve karşılaştırma için normalize edilmiş düz metin."""
    if not s:
        return ""
    s = turkce_kucuk(s).replace('ı', 'i')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

def dosya_adindan_gurultu_temizle(ad):
    """
    Anna's Archive, Telegram, Z-Lib gibi kaynakların eklediği etiketleri temizler.
    Örnek: 'tutunamayanlar_annas_archive' -> 'tutunamayanlar'
           'Oğuz Atay - Tutunamayanlar (z-lib.org)' -> 'Oğuz Atay - Tutunamayanlar'
    """
    ad_koks = os.path.splitext(ad)[0]
    
    # Bilinen site ve gürültü kalıpları
    desenler = [
        r'\[annas_archive\]', r'\[anna\'s archive\]', r'\(annas_archive\)', r'_annas_archive', r'-annas-archive',
        r'\(z-lib\.org\)', r'\(z-library\)', r'\[z-lib\.org\]', r'\[z-library\]',
        r'\(libgen\.li\)', r'\(libgen\.is\)', r'\(libgen\.rs\)', r'\[libgen\]',
        r'\(telegram\)', r'\[telegram\]', r'@[\w_]+',
        r'\[epub\]', r'\[pdf\]', r'\(epub\)', r'\(pdf\)',
        r'\bannas-archive\b', r'\bannas_archive\b',
        r'\bwww\.[a-z0-9\-]+\.[a-z]{2,6}\b',
        r'\(z-lib\)', r'\[z-lib\]',
        r'\(1\)$', r'\(2\)$', r'\(3\)$', r'_\d+$'
    ]
    
    temiz = ad_koks
    for d in desenler:
        temiz = re.sub(d, '', temiz, flags=re.IGNORECASE)
    
    # 32 karakterlik MD5 hash kalıpları (Anna's Archive dosyalarında sıkça olur)
    temiz = re.sub(r'_[a-f0-9]{32}\b', '', temiz, flags=re.IGNORECASE)
    temiz = re.sub(r'\b[a-f0-9]{32}_', '', temiz, flags=re.IGNORECASE)

    # Altçizgileri ve fazla tireleri düzelt
    temiz = temiz.replace('_', ' ')
    temiz = re.sub(r'\s*-\s*', ' - ', temiz)
    temiz = re.sub(r'\s+', ' ', temiz).strip()
    return temiz

# ==============================================================================
# 2. MEVCUT OKUNANLAR KÜTÜPHANESİ REFERANS HAVUZU
# ==============================================================================
class KutuphaneReferans:
    def __init__(self):
        self.kitaplar = []        # list of (baslik, yazar)
        self.baslik_haritasi = {} # norm(baslik) -> (baslik, yazar)
        self.yazar_kumesi = set() # set of norm(yazar)
        self.yazar_orijinal = {}  # norm(yazar) -> orijinal_yazar
        self.kelime_haritasi = {} # kelime -> [(baslik, yazar, norm_baslik)]
        self.onbellek_ara = {}
        self.onbellek_yazar = {}
        self.yukle()

    def yukle(self):
        self.kitaplar.clear()
        self.baslik_haritasi.clear()
        self.yazar_kumesi.clear()
        self.yazar_orijinal.clear()
        self.kelime_haritasi.clear()
        self.onbellek_ara.clear()
        self.onbellek_yazar.clear()

        # 1. SQLite kitaplik.db'den yükle
        if os.path.exists(DB_YOLU):
            try:
                import sqlite3
                conn = sqlite3.connect(DB_YOLU)
                cur = conn.cursor()
                rows = cur.execute("SELECT baslik, yazar FROM kitaplar").fetchall()
                for b, y in rows:
                    if b and b.strip():
                        b_temiz = b.strip()
                        y_temiz = (y or '').strip()
                        self._kayit_ekle(b_temiz, y_temiz)
                conn.close()
            except Exception as e:
                print(f"[!] SQLite referans yükleme hatası: {e}")

        # 2. veri.js dosyasından yükle
        veri_js = os.path.join(KOK_DIZIN, 'veri.js')
        if os.path.exists(veri_js):
            try:
                with open(veri_js, 'r', encoding='utf8') as f:
                    icerik = f.read()
                    m = re.search(r'window\.KITAPLIK\s*=\s*(\[.*?\]);?\s*$', icerik, re.DOTALL)
                    if m:
                        kitaplar_json = json.loads(m.group(1))
                        for k in kitaplar_json:
                            b = k.get('baslik')
                            y = k.get('yazar')
                            if b and b.strip():
                                self._kayit_ekle(b.strip(), (y or '').strip())
            except Exception as e:
                print(f"[!] veri.js referans yükleme hatası: {e}")

        # 3. CSV dosyalarından yükle
        for csv_yol in glob.glob(os.path.join(KOK_DIZIN, '*.csv')):
            try:
                import csv
                with open(csv_yol, encoding='utf-8-sig', newline='') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        b = r.get('Kitap adı') or r.get('Title')
                        y = r.get('Yazar') or r.get('Author')
                        if b and b.strip():
                            self._kayit_ekle(b.strip(), (y or '').strip())
            except Exception:
                pass

        print(f"[*] Kütüphane referans havuzu hazır: {len(self.baslik_haritasi)} benzersiz kitap, {len(self.yazar_kumesi)} yazar.")

    def _kayit_ekle(self, baslik, yazar):
        nb = norm(baslik)
        if not nb:
            return
        if nb not in self.baslik_haritasi or (not self.baslik_haritasi[nb][1] and yazar):
            self.baslik_haritasi[nb] = (baslik, yazar)
            self.kitaplar.append((baslik, yazar))
            for w in nb.split():
                if len(w) >= 3:
                    self.kelime_haritasi.setdefault(w, []).append((baslik, yazar, nb))
        
        if yazar:
            ny = norm(yazar)
            self.yazar_kumesi.add(ny)
            self.yazar_orijinal[ny] = yazar

    def ara(self, sorgu_metin):
        """
        Sorgu metnini referans kütüphanede ultra hızlı arar.
        Tam eşleşme, alt küme eşleşmesi ve indeksli benzerlik döndürür.
        """
        q_norm = norm(sorgu_metin)
        if not q_norm:
            return None, None, None, 0

        if q_norm in self.onbellek_ara:
            return self.onbellek_ara[q_norm]

        # 1. Tam normalize eşleşme
        if q_norm in self.baslik_haritasi:
            b, y = self.baslik_haritasi[q_norm]
            res = (b, y, "Veritabanı (Tam Eşleşme)", 1.0)
            self.onbellek_ara[q_norm] = res
            return res

        # 2. Yazar ve Kitap Adı ayrıştırma testi:
        for ny, oy in self.yazar_orijinal.items():
            if len(ny) >= 4 and ny in q_norm:
                kalan = q_norm.replace(ny, '').strip()
                if kalan in self.baslik_haritasi:
                    b, y = self.baslik_haritasi[kalan]
                    res = (b, y or oy, "Veritabanı (Yazar + Başlık)", 0.95)
                    self.onbellek_ara[q_norm] = res
                    return res

        # 3. Kelime indeksinden aday seçimi (SequenceMatcher sadece kelime paylaşanlara uygulanır)
        q_words = [w for w in q_norm.split() if len(w) >= 3]
        aday_kitaplar = {}
        for w in q_words:
            if w in self.kelime_haritasi:
                for b, y, nb in self.kelime_haritasi[w]:
                    aday_kitaplar[nb] = (b, y)

        if aday_kitaplar:
            en_iyi_oran = 0
            en_iyi_kitap = None
            for nb, (b, y) in aday_kitaplar.items():
                if nb == q_norm or (len(nb) >= 4 and nb in q_norm) or (len(q_norm) >= 4 and q_norm in nb):
                    res = (b, y, "Veritabanı (İçerik Eşleşmesi)", 0.90)
                    self.onbellek_ara[q_norm] = res
                    return res
                r = difflib.SequenceMatcher(None, q_norm, nb).ratio()
                if r > en_iyi_oran:
                    en_iyi_oran = r
                    en_iyi_kitap = (b, y)

            if en_iyi_oran >= 0.78 and en_iyi_kitap:
                res = (en_iyi_kitap[0], en_iyi_kitap[1], f"Veritabanı (Benzerlik %{int(en_iyi_oran*100)})", en_iyi_oran)
                self.onbellek_ara[q_norm] = res
                return res

        res = (None, None, None, 0)
        self.onbellek_ara[q_norm] = res
        return res

    def yazar_mi(self, metin):
        """Verilen metnin kütüphanede kayıtlı bir yazar olup olmadığını kontrol eder."""
        n = norm(metin)
        if not n:
            return None
        if n in self.onbellek_yazar:
            return self.onbellek_yazar[n]
        if n in self.yazar_kumesi:
            res = self.yazar_orijinal[n]
            self.onbellek_yazar[n] = res
            return res
        for ny, oy in self.yazar_orijinal.items():
            if len(ny) >= 4 and (ny == n or ny in n):
                self.onbellek_yazar[n] = oy
                return oy
        self.onbellek_yazar[n] = None
        return None

    def kutuphanede_var_mi(self, baslik, yazar=""):
        """Bir kitabın ana kütüphanede (veri.js veya kitaplik.db) mevcut olup olmadığını sorgular."""
        if not baslik:
            return False
        nb = norm(baslik)
        if nb in self.baslik_haritasi:
            return True
        if yazar:
            sorgu = f"{baslik} {yazar}"
            b, y, k, g = self.ara(sorgu)
            if g >= 0.80:
                return True
        else:
            b, y, k, g = self.ara(baslik)
            if g >= 0.85:
                return True
        return False

referans_havuz = KutuphaneReferans()

# ==============================================================================
# 3. DOSYA ÜSTVERİSİ (METADATA) OKUYUCU
# ==============================================================================
class DosyaMetaOkuyucu:
    @staticmethod
    def epub_oku(dosya_yolu):
        """EPUB dosyasının content.opf üstverisinden başlık ve yazarı çeker."""
        baslik = ""
        yazar = ""
        try:
            import zipfile
            with zipfile.ZipFile(dosya_yolu, 'r') as z:
                opf_yolu = None
                # container.xml kontrolü
                if 'META-INF/container.xml' in z.namelist():
                    try:
                        c_xml = ET.fromstring(z.read('META-INF/container.xml'))
                        rootfile = c_xml.find('.//{*}rootfile')
                        if rootfile is not None:
                            opf_yolu = rootfile.get('full-path')
                    except Exception:
                        pass
                
                if not opf_yolu:
                    for ad in z.namelist():
                        if ad.endswith('.opf'):
                            opf_yolu = ad
                            break

                if opf_yolu and opf_yolu in z.namelist():
                    opf_icerik = z.read(opf_yolu)
                    tree = ET.fromstring(opf_icerik)
                    
                    for el in tree.iter():
                        tag_lower = el.tag.lower()
                        metin = (el.text or '').strip()
                        if not metin:
                            continue
                        if tag_lower.endswith('title') and not baslik:
                            baslik = metin
                        elif tag_lower.endswith('creator') and not yazar:
                            # "Bilinmeyen yazar", "Unknown", "calibre" gibi gürültüleri filtrele
                            if not re.search(r'bilinmeyen|unknown|calibre|anonymous', metin, re.IGNORECASE):
                                yazar = metin
        except Exception as e:
            pass
        return baslik, yazar

    @staticmethod
    def pdf_oku(dosya_yolu):
        """PDF dosyasının PyMuPDF üstverisinden başlık ve yazarı çeker."""
        baslik = ""
        yazar = ""
        try:
            doc = fitz.open(dosya_yolu)
            meta = doc.metadata or {}
            raw_title = (meta.get('title') or '').strip()
            raw_author = (meta.get('author') or '').strip()

            # Gürültü filtreleme
            yasakli = r'^(microsoft|word|indesign|acrobat|scanner|untitled|isimsiz|writer|pdf\d*|scan\b)'
            if raw_title and not re.search(yasakli, raw_title, re.IGNORECASE) and len(raw_title) > 2:
                # UUID veya hash benzeri başlıkları ele
                if not re.match(r'^[a-f0-9\-]{20,}$', raw_title, re.IGNORECASE):
                    baslik = raw_title
            
            if raw_author and not re.search(yasakli, raw_author, re.IGNORECASE) and len(raw_author) > 2:
                if not re.search(r'calibre|adobe|canon|epson|hewlett|admin|bilinmeyen|unknown|anonymous', raw_author, re.IGNORECASE):
                    yazar = raw_author
            doc.close()
        except Exception:
            pass
        return baslik, yazar

# ==============================================================================
# 4. İNTERNET ARAMA MOTORU (OPENLIBRARY & KİTAPYURDU YEDEK)
# ==============================================================================
_onbellek_sozluk = {}
def onbellek_yukle():
    global _onbellek_sozluk
    if os.path.exists(ONBELLEK_DOSYASI):
        try:
            with open(ONBELLEK_DOSYASI, 'r', encoding='utf8') as f:
                _onbellek_sozluk = json.load(f)
        except Exception:
            _onbellek_sozluk = {}

def onbellek_kaydet():
    try:
        with open(ONBELLEK_DOSYASI, 'w', encoding='utf8') as f:
            json.dump(_onbellek_sozluk, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

onbellek_yukle()

def internette_ara(sorgu):
    """OpenLibrary API üzerinden kitap başlığı ve yazarı bulur."""
    sorgu_temiz = sorgu.strip()
    if not sorgu_temiz or len(sorgu_temiz) < 3:
        return None, None
    
    if sorgu_temiz in _onbellek_sozluk:
        c = _onbellek_sozluk[sorgu_temiz]
        return c.get('title'), c.get('author')

    # OpenLibrary Arama
    try:
        url = 'https://openlibrary.org/search.json?q=' + up.quote(sorgu_temiz)
        req = ur.Request(url, headers={'User-Agent': 'OkunanlarDuzenleyici/2.0'})
        with ur.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            docs = data.get('docs', [])
            if docs:
                for doc in docs[:3]:
                    t = doc.get('title')
                    authors = doc.get('author_name', [])
                    a = authors[0] if authors else ""
                    if t:
                        _onbellek_sozluk[sorgu_temiz] = {'title': t, 'author': a}
                        onbellek_kaydet()
                        return t, a
    except Exception:
        pass
    
    _onbellek_sozluk[sorgu_temiz] = {'title': None, 'author': None}
    onbellek_kaydet()
    return None, None

# ==============================================================================
# 5. DOSYA ADI ANALİZ VE ÖNERİ MOTORU
# ==============================================================================
def analiz_et(dosya_yolu):
    """
    Bir dosyanın mevcut adını, üstverilerini ve kütüphane referansını analiz eder.
    Hedef standart: 'Kitap Adı - Yazar.uzantı'
    """
    dosya_adi = os.path.basename(dosya_yolu)
    ad_koks, ext = os.path.splitext(dosya_adi)
    ext_lower = ext.lower()

    temiz_ad = dosya_adindan_gurultu_temizle(dosya_adi)

    # 1. Dosya üstverisi oku
    meta_baslik, meta_yazar = "", ""
    if ext_lower == '.epub':
        meta_baslik, meta_yazar = DosyaMetaOkuyucu.epub_oku(dosya_yolu)
    elif ext_lower == '.pdf':
        meta_baslik, meta_yazar = DosyaMetaOkuyucu.pdf_oku(dosya_yolu)

    # 2. İsim kalıbını ayrıştır (Yazar - Kitap veya Kitap - Yazar)
    parcalar = [p.strip() for p in temiz_ad.split(' - ') if p.strip()]
    ad_yazar = ""
    ad_baslik = ""
    
    if len(parcalar) >= 2:
        sol, sag = parcalar[0], parcalar[1]
        # Sol taraf yazar mı?
        sol_yazar_orijinal = referans_havuz.yazar_mi(sol)
        sag_yazar_orijinal = referans_havuz.yazar_mi(sag)

        if sol_yazar_orijinal and not sag_yazar_orijinal:
            # Format: Yazar - Kitap Adı
            ad_yazar = sol_yazar_orijinal
            ad_baslik = sag
        elif sag_yazar_orijinal and not sol_yazar_orijinal:
            # Format: Kitap Adı - Yazar
            ad_baslik = sol
            ad_yazar = sag_yazar_orijinal
        else:
            # Belirsiz, sol tarafı başlık sağ tarafı yazar varsay
            ad_baslik = sol
            ad_yazar = sag
    else:
        ad_baslik = temiz_ad

    # 3. Kütüphane referansı kontrolü (En güvenilir kaynak)
    ref_baslik, ref_yazar, ref_kaynak, ref_guven = None, None, None, 0

    # Önce ayrıştırılan başlıkla ara
    for aday in [ad_baslik, temiz_ad, meta_baslik]:
        if aday:
            rb, ry, rk, rg = referans_havuz.ara(aday)
            if rg > ref_guven:
                ref_baslik, ref_yazar, ref_kaynak, ref_guven = rb, ry, rk, rg

    # 4. Nihai Başlık ve Yazar Belirleme
    nihai_baslik = ""
    nihai_yazar = ""
    kaynak = "Bilinmiyor"
    guven = 0.5

    if ref_baslik and ref_yazar:
        nihai_baslik = ref_baslik
        nihai_yazar = ref_yazar
        kaynak = ref_kaynak
        guven = ref_guven
    elif ref_baslik and not ref_yazar:
        nihai_baslik = ref_baslik
        nihai_yazar = ad_yazar or meta_yazar
        kaynak = f"{ref_kaynak} (Yazar Üstveriden)"
        guven = 0.85
    else:
        # Kütüphanede doğrudan bulunamadı; dosya üstverisi veya dosya adından çıkarılan
        if ad_baslik and ad_yazar:
            nihai_baslik = ad_baslik
            nihai_yazar = ad_yazar
            kaynak = "Dosya Adı Ayrıştırma"
            guven = 0.75
        elif meta_baslik and meta_yazar:
            nihai_baslik = meta_baslik
            nihai_yazar = meta_yazar
            kaynak = "Dosya Üstverisi (Metadata)"
            guven = 0.80
        elif meta_baslik:
            nihai_baslik = meta_baslik
            nihai_yazar = ad_yazar
            kaynak = "Dosya Üstverisi Başlık"
            guven = 0.65
        else:
            nihai_baslik = ad_baslik
            nihai_yazar = ad_yazar
            kaynak = "Dosya Adı"
            guven = 0.50

    # Eğer yazar hala eksikse ve dosya üstverisinde yazar varsa kullan
    if nihai_baslik and not nihai_yazar and meta_yazar:
        nihai_yazar = meta_yazar
        kaynak = "Dosya Üstverisi (Yazar)"
        guven = 0.70

    # Başlık ve Yazar formatını güzelleştir
    nb_check = norm(nihai_baslik)
    if nb_check in referans_havuz.baslik_haritasi:
        nihai_baslik = referans_havuz.baslik_haritasi[nb_check][0]
    else:
        nihai_baslik = turkce_baslik(nihai_baslik.strip())

    if nihai_yazar:
        ny_check = norm(nihai_yazar)
        if ny_check in referans_havuz.yazar_orijinal:
            nihai_yazar = referans_havuz.yazar_orijinal[ny_check]
        else:
            nihai_yazar = turkce_baslik(nihai_yazar.strip())

    # Önerilen dosya adı: Kitap Adı - Yazar.uzantı
    if nihai_yazar:
        onerilen_ad = f"{nihai_baslik} - {nihai_yazar}{ext}"
    else:
        onerilen_ad = f"{nihai_baslik}{ext}"

    # Windows dosya adı yasaklı karakterlerini temizle: \ / : * ? " < > |
    onerilen_ad = re.sub(r'[\\/*?:"<>|]', '', onerilen_ad).strip()

    # Zaten doğru mu?
    zaten_dogru = (dosya_adi.strip() == onerilen_ad.strip())
    if zaten_dogru:
        kaynak = "Zaten Standart Formatta"
        guven = 1.0

    kutuphanede_var = referans_havuz.kutuphanede_var_mi(nihai_baslik, nihai_yazar)

    return {
        "orijinal_ad": dosya_adi,
        "temiz_ad": temiz_ad,
        "tespit_baslik": nihai_baslik,
        "tespit_yazar": nihai_yazar,
        "onerilen_ad": onerilen_ad,
        "kaynak": kaynak,
        "guven": round(guven * 100),
        "degisim_gerekli": not zaten_dogru,
        "kutuphanede_var": kutuphanede_var
    }

# ==============================================================================
# 6. MÜKERRER DOSYA ANALİZİ VE FORMAT SINIFLANDIRMASI
# ==============================================================================
def dosya_ozeti_al(dosya_yolu):
    """Hızlı MD5 özeti (Dosya boyutu + İlk 512KB + Son 512KB)."""
    try:
        boyut = os.path.getsize(dosya_yolu)
        h = hashlib.md5()
        h.update(str(boyut).encode('utf8'))
        with open(dosya_yolu, 'rb') as f:
            if boyut <= 1024 * 1024:
                h.update(f.read())
            else:
                h.update(f.read(512 * 1024))
                f.seek(-512 * 1024, os.SEEK_END)
                h.update(f.read())
        return h.hexdigest(), boyut
    except Exception:
        return "", 0

def tam_dosya_hash(dosya_yolu):
    """Tam SHA256 özeti."""
    try:
        h = hashlib.sha256()
        with open(dosya_yolu, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def klasor_tara(hedef_dizin, alt_dizinler=True):
    """
    Belirtilen klasörü tarar, kitap dosyalarını indeksler,
    formatlarına göre ayırır ve mükerrerleri tespit eder.
    """
    if not os.path.exists(hedef_dizin):
        return {"hata": "Belirtilen klasör mevcut değil."}

    dosyalar = []
    
    # 1. Dosyaları listele
    for kok, _, dosya_adlari in os.walk(hedef_dizin):
        for ad in dosya_adlari:
            _, ext = os.path.splitext(ad)
            if ext.lower() in DESTEKLENEN_UZANTILAR:
                yol = os.path.join(kok, ad)
                dosyalar.append(yol)
        if not alt_dizinler:
            break

    # 2. Dosya bazında analiz ve hash hesaplama
    kitap_listesi = []
    hash_haritasi = {}  # hash -> list of kitap_dict

    # Başlık ve yazara göre format gruplaması: norm(baslik+yazar) -> {'pdf': [], 'epub': [], 'diger': []}
    eser_formati_haritasi = {}

    for idx, yol in enumerate(dosyalar):
        ad = os.path.basename(yol)
        _, ext = os.path.splitext(ad)
        ext_lower = ext.lower()
        
        analiz = analiz_et(yol)
        h_ozet, boyut = dosya_ozeti_al(yol)
        mod_zamani = os.path.getmtime(yol)
        tarih_str = datetime.fromtimestamp(mod_zamani).strftime('%Y-%m-%d %H:%M')

        # Boyut formatla
        if boyut < 1024 * 1024:
            boyut_str = f"{boyut / 1024:.1f} KB"
        else:
            boyut_str = f"{boyut / (1024*1024):.1f} MB"

        kitap_item = {
            "id": f"k_{idx}_{int(time.time()*1000)%1000000}",
            "dosya_yolu": yol,
            "dosya_adi": ad,
            "rel_yol": os.path.relpath(yol, hedef_dizin),
            "format": ext_lower.replace('.', '').upper(),
            "ext": ext_lower,
            "boyut": boyut,
            "boyut_str": boyut_str,
            "tarih": tarih_str,
            "mod_zamani": mod_zamani,
            "hash": h_ozet,
            "analiz": analiz,
            "mukerrer": False,
            "mukerrer_grup_id": None,
            "mukerrer_nedeni": None,
            "format_durumu": "belirsiz",  # 'hem_pdf_hem_epub', 'sadece_epub', 'sadece_pdf', 'diger'
            "kutuphanede_var": analiz.get("kutuphanede_var", False)
        }

        kitap_listesi.append(kitap_item)

        # Hash haritası
        if h_ozet:
            if h_ozet not in hash_haritasi:
                hash_haritasi[h_ozet] = []
            hash_haritasi[h_ozet].append(kitap_item)

        # Eser format anahtarı
        eser_anahtar = norm(f"{analiz['tespit_baslik']} {analiz['tespit_yazar']}") or norm(analiz['temiz_ad'])
        if eser_anahtar not in eser_formati_haritasi:
            eser_formati_haritasi[eser_anahtar] = {'pdf': [], 'epub': [], 'diger': []}
        
        if ext_lower == '.pdf':
            eser_formati_haritasi[eser_anahtar]['pdf'].append(kitap_item)
        elif ext_lower == '.epub':
            eser_formati_haritasi[eser_anahtar]['epub'].append(kitap_item)
        else:
            eser_formati_haritasi[eser_anahtar]['diger'].append(kitap_item)

    # 3. Mükerrerleri Belirle
    def asli_skoru(x):
        skor = 0
        if not x['analiz']['degisim_gerekli']:
            skor += 50
        if not re.search(r'\(\d+\)|kopya|copy|_\d+\b', x['dosya_adi'], re.IGNORECASE):
            skor += 30
        if '_' not in x['dosya_adi']:
            skor += 10
        skor += min(x['boyut'] / (1024 * 1024), 20)
        return skor

    mukerrer_sayisi = 0
    grup_sayaci = 1

    for h, grup in hash_haritasi.items():
        if len(grup) > 1:
            # En temiz isimlendirilmiş olanı asıl tut, diğerlerini mükerrer işaretle
            grup.sort(key=asli_skoru, reverse=True)
            asli = grup[0]
            for kopya in grup[1:]:
                kopya['mukerrer'] = True
                kopya['mukerrer_grup_id'] = f"G_{grup_sayaci}"
                kopya['mukerrer_nedeni'] = f"Birebir içerik eşleşmesi (Hash aynı: {asli['dosya_adi']})"
                mukerrer_sayisi += 1
            asli['mukerrer_grup_id'] = f"G_{grup_sayaci}"
            grup_sayaci += 1

    # Kural B: Aynı kitap, aynı yazar ve aynı formatta olup hash'i farklı olanlar (İçeriksel kopya)
    for eser_anahtar, f_grup in eser_formati_haritasi.items():
        for fmt in ['pdf', 'epub']:
            liste = f_grup[fmt]
            if len(liste) > 1:
                isaretlenmemis = [x for x in liste if not x['mukerrer']]
                if len(isaretlenmemis) > 1:
                    isaretlenmemis.sort(key=asli_skoru, reverse=True)
                    asli = isaretlenmemis[0]
                    for kopya in isaretlenmemis[1:]:
                        kopya['mukerrer'] = True
                        kopya['mukerrer_grup_id'] = f"G_{grup_sayaci}"
                        kopya['mukerrer_nedeni'] = f"Aynı formatta tekrarlanan dosya (Asıl: {asli['dosya_adi']})"
                        mukerrer_sayisi += 1
                    asli['mukerrer_grup_id'] = f"G_{grup_sayaci}"
                    grup_sayaci += 1

    # 4. Format Durumunu Ata (Hem PDF Hem EPUB, Sadece EPUB, Sadece PDF)
    sayaclar = {
        "toplam": len(kitap_listesi),
        "hem_pdf_hem_epub": 0,
        "sadece_epub": 0,
        "sadece_pdf": 0,
        "diger": 0,
        "mukerrer": mukerrer_sayisi,
        "isim_duzeltilecek": 0,
        "kutuphanede_yok": 0
    }

    for eser_anahtar, f_grup in eser_formati_haritasi.items():
        has_pdf = len(f_grup['pdf']) > 0
        has_epub = len(f_grup['epub']) > 0

        if has_pdf and has_epub:
            durum = 'hem_pdf_hem_epub'
        elif has_epub and not has_pdf:
            durum = 'sadece_epub'
        elif has_pdf and not has_epub:
            durum = 'sadece_pdf'
        else:
            durum = 'diger'

        # Bu esere ait tüm dosyalara bu durumu ata
        for liste in [f_grup['pdf'], f_grup['epub'], f_grup['diger']]:
            for item in liste:
                item['format_durumu'] = durum

    for k in kitap_listesi:
        if k['analiz']['degisim_gerekli']:
            sayaclar['isim_duzeltilecek'] += 1
        if not k.get('kutuphanede_var'):
            sayaclar['kutuphanede_yok'] += 1
        if k['format_durumu'] == 'hem_pdf_hem_epub':
            sayaclar['hem_pdf_hem_epub'] += 1
        elif k['format_durumu'] == 'sadece_epub':
            sayaclar['sadece_epub'] += 1
        elif k['format_durumu'] == 'sadece_pdf':
            sayaclar['sadece_pdf'] += 1
        else:
            sayaclar['diger'] += 1

    return {
        "hedef_dizin": hedef_dizin,
        "sayaclar": sayaclar,
        "kitaplar": kitap_listesi,
        "calibre_mevcut": bool(CALIBRE_YOLU),
        "calibre_yolu": CALIBRE_YOLU
    }

# ==============================================================================
# 7. FLASK UYGULAMASI VE API ENDPOINT'LERİ
# ==============================================================================
app = Flask(__name__)

# Küresel tarama önbelleği
mevcut_tarama = {}
donusturme_durumlari = {} # is_id -> {'durum': 'devam', 'mesaj': '...'}

@app.route('/api/calibre-durum')
def api_calibre_durum():
    return jsonify({
        "calibre_mevcut": bool(CALIBRE_YOLU),
        "calibre_yolu": CALIBRE_YOLU
    })

@app.route('/api/klasor-sec', methods=['POST', 'GET'])
def api_klasor_sec():
    """Windows yerel klasör seçim diyaloğunu açar."""
    secilen = ""
    def _dialog():
        nonlocal secilen
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            secilen = filedialog.askdirectory(
                initialdir=os.path.join(KOK_DIZIN, 'kitaplar'),
                title="Kitapların Bulunduğu Klasörü Seçin"
            )
            root.destroy()
        except Exception as e:
            print("Klasör diyalog hatası:", e)

    t = threading.Thread(target=_dialog)
    t.start()
    t.join(timeout=30)

    if secilen:
        secilen = os.path.normpath(secilen)
        return jsonify({"basarili": True, "klasor": secilen})
    return jsonify({"basarili": False, "mesaj": "Klasör seçilmedi veya iptal edildi."})

@app.route('/api/tara', methods=['POST', 'GET'])
def api_tara():
    data = request.get_json(silent=True) or {}
    klasor = data.get('klasor', '').strip()
    if not klasor:
        klasor = os.path.join(KOK_DIZIN, 'kitaplar')
    
    klasor = os.path.normpath(klasor)
    alt_dizinler = data.get('alt_dizinler', True)

    sonuc = klasor_tara(klasor, alt_dizinler=alt_dizinler)
    if "hata" in sonuc:
        body = json.dumps(sonuc)
        return Response(body, status=400, mimetype='application/json')
    
    global mevcut_tarama
    mevcut_tarama = sonuc

    # Frontend tablosu için optimize edilmiş temiz kopya (hızlı aktarım ve sıfır soket hatası)
    kitaplar_hafif = []
    for k in sonuc.get('kitaplar', []):
        a = k.get('analiz', {})
        kitaplar_hafif.append({
            'id': k['id'],
            'dosya_yolu': k['dosya_yolu'],
            'dosya_adi': k['dosya_adi'],
            'rel_yol': k['rel_yol'],
            'format': k['format'],
            'boyut_str': k['boyut_str'],
            'mukerrer': k['mukerrer'],
            'mukerrer_nedeni': k.get('mukerrer_nedeni'),
            'format_durumu': k['format_durumu'],
            'kutuphanede_var': k.get('kutuphanede_var', False),
            'analiz': {
                'tespit_baslik': a.get('tespit_baslik', ''),
                'tespit_yazar': a.get('tespit_yazar', ''),
                'onerilen_ad': a.get('onerilen_ad', ''),
                'degisim_gerekli': a.get('degisim_gerekli', False),
                'kaynak': a.get('kaynak', ''),
                'guven': a.get('guven', 50)
            }
        })

    yanit = {
        'hedef_dizin': sonuc.get('hedef_dizin', klasor),
        'sayaclar': sonuc.get('sayaclar', {}),
        'kitaplar': kitaplar_hafif,
        'calibre_mevcut': sonuc.get('calibre_mevcut', False),
        'calibre_yolu': sonuc.get('calibre_yolu')
    }

    body = json.dumps(yanit)
    return Response(body, status=200, mimetype='application/json')

@app.route('/api/adlandir', methods=['POST'])
def api_adlandir():
    """
    Seçili dosyaları 'Kitap Adı - Yazar.uzantı' standardına göre yeniden adlandırır.
    İşlemleri geri alınabilir şekilde .duzenleyici_gecmis.json dosyasına kaydeder.
    """
    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])
    ozel_adlar = data.get('ozel_adlar', {}) # id -> yeni_ad

    if not mevcut_tarama or 'kitaplar' not in mevcut_tarama:
        return jsonify({"hata": "Önce bir klasör taraması yapmalısınız."}), 400

    degistirilenler = []
    hatalar = []

    # Geçmiş kaydı hazırla
    gecmis_kayit = {
        "tarih": datetime.now().isoformat(),
        "islemler": []
    }

    kitap_haritasi = {k['id']: k for k in mevcut_tarama['kitaplar']}

    for fid in dosya_idleri:
        if fid not in kitap_haritasi:
            continue
        k = kitap_haritasi[fid]
        eski_yol = k['dosya_yolu']
        dizin = os.path.dirname(eski_yol)

        yeni_ad = ozel_adlar.get(fid) or k['analiz']['onerilen_ad']
        # Windows yasaklı karakter temizliği
        yeni_ad = re.sub(r'[\\/*?:"<>|]', '', yeni_ad).strip()
        if not yeni_ad:
            continue

        # Kullanıcı manuel isimlendirmede uzantıyı yazmadıysa mevcut uzantıyı koru
        giris_kok, giris_uzanti = os.path.splitext(yeni_ad)
        eski_kok, eski_uzanti = os.path.splitext(k['dosya_adi'])
        if not giris_uzanti and eski_uzanti:
            yeni_ad += eski_uzanti

        yeni_yol = os.path.join(dizin, yeni_ad)

        if eski_yol == yeni_yol:
            continue

        # Hedefte dosya zaten varsa isim çakışmasını önle
        if os.path.exists(yeni_yol) and os.path.normcase(eski_yol) != os.path.normcase(yeni_yol):
            kok_ad, uzanti = os.path.splitext(yeni_ad)
            sayac = 1
            while os.path.exists(yeni_yol):
                yeni_ad = f"{kok_ad} ({sayac}){uzanti}"
                yeni_yol = os.path.join(dizin, yeni_ad)
                sayac += 1

        try:
            os.rename(eski_yol, yeni_yol)
            degistirilenler.append({"eski": k['dosya_adi'], "yeni": yeni_ad, "yeni_yol": yeni_yol})
            gecmis_kayit["islemler"].append({"eski_yol": eski_yol, "yeni_yol": yeni_yol})
            # Önbellekteki bilgileri güncelle
            k['dosya_yolu'] = yeni_yol
            k['dosya_adi'] = yeni_ad
            k['analiz']['onerilen_ad'] = yeni_ad
            k['analiz']['degisim_gerekli'] = False
            k['analiz']['kaynak'] = "Yeni Adlandırıldı"
        except Exception as e:
            hatalar.append(f"{k['dosya_adi']} adlandırılamadı: {e}")

    # Geçmişe kaydet
    if gecmis_kayit["islemler"]:
        gecmis_listesi = []
        if os.path.exists(GECMIS_DOSYASI):
            try:
                with open(GECMIS_DOSYASI, 'r', encoding='utf8') as f:
                    gecmis_listesi = json.load(f)
            except: pass
        gecmis_listesi.append(gecmis_kayit)
        try:
            with open(GECMIS_DOSYASI, 'w', encoding='utf8') as f:
                json.dump(gecmis_listesi, f, ensure_ascii=False, indent=2)
        except: pass

    return jsonify({
        "basarili": True,
        "degistirilen_sayisi": len(degistirilenler),
        "degistirilenler": degistirilenler,
        "hatalar": hatalar
    })

@app.route('/api/geri-al', methods=['POST'])
def api_geri_al():
    """Son yapılan adlandırma işlemlerini geri alır."""
    if not os.path.exists(GECMIS_DOSYASI):
        return jsonify({"basarili": False, "mesaj": "Geri alınacak adlandırma geçmişi bulunamadı."})

    try:
        with open(GECMIS_DOSYASI, 'r', encoding='utf8') as f:
            gecmis_listesi = json.load(f)
        
        if not gecmis_listesi:
            return jsonify({"basarili": False, "mesaj": "Geri alınacak işlem kalmadı."})

        son_islem = gecmis_listesi.pop()
        geri_alinanlar = []
        hatalar = []

        for item in reversed(son_islem.get('islemler', [])):
            eski_yol = item['eski_yol']
            yeni_yol = item['yeni_yol']
            if os.path.exists(yeni_yol):
                try:
                    os.rename(yeni_yol, eski_yol)
                    geri_alinanlar.append({"eski": os.path.basename(yeni_yol), "yeni": os.path.basename(eski_yol)})
                except Exception as e:
                    hatalar.append(str(e))

        with open(GECMIS_DOSYASI, 'w', encoding='utf8') as f:
            json.dump(gecmis_listesi, f, ensure_ascii=False, indent=2)

        return jsonify({
            "basarili": True,
            "geri_alinan_sayisi": len(geri_alinanlar),
            "hatalar": hatalar
        })
    except Exception as e:
        return jsonify({"basarili": False, "mesaj": f"Geri alma hatası: {e}"}), 500

@app.route('/api/mukerrer-temizle', methods=['POST'])
def api_mukerrer_temizle():
    """
    Seçili mükerrer dosyaları güvenli bir şekilde '_mukerrer_arsiv' klasörüne taşır veya siler.
    """
    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])
    islem_turu = data.get('islem', 'arsivle')  # 'arsivle' veya 'sil'

    if not mevcut_tarama or 'kitaplar' not in mevcut_tarama:
        return jsonify({"hata": "Önce bir klasör taraması yapmalısınız."}), 400

    kitap_haritasi = {k['id']: k for k in mevcut_tarama['kitaplar']}
    hedef_arsiv = os.path.join(mevcut_tarama['hedef_dizin'], '_mukerrer_arsiv')

    if islem_turu == 'arsivle':
        os.makedirs(hedef_arsiv, exist_ok=True)

    islem_gorenler = []
    hatalar = []

    for fid in dosya_idleri:
        if fid not in kitap_haritasi:
            continue
        k = kitap_haritasi[fid]
        yol = k['dosya_yolu']
        if not os.path.exists(yol):
            continue

        try:
            if islem_turu == 'arsivle':
                hedef_yol = os.path.join(hedef_arsiv, k['dosya_adi'])
                if os.path.exists(hedef_yol):
                    kok_ad, ext = os.path.splitext(k['dosya_adi'])
                    hedef_yol = os.path.join(hedef_arsiv, f"{kok_ad}_{int(time.time())}{ext}")
                shutil.move(yol, hedef_yol)
                islem_gorenler.append(k['dosya_adi'])
            elif islem_turu == 'sil':
                os.remove(yol)
                islem_gorenler.append(k['dosya_adi'])
        except Exception as e:
            hatalar.append(f"{k['dosya_adi']}: {e}")

    return jsonify({
        "basarili": True,
        "islem_turu": islem_turu,
        "islem_goren_sayisi": len(islem_gorenler),
        "hatalar": hatalar
    })

@app.route('/api/kopyala-tasi', methods=['POST'])
def api_kopyala_tasi():
    """Seçili dosyaları başka bir klasöre kopyalar veya taşır."""
    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])
    hedef_klasor = data.get('hedef_klasor', '').strip()
    eylem = data.get('eylem', 'kopyala') # 'kopyala' veya 'tasi'

    if not hedef_klasor or not os.path.exists(hedef_klasor):
        return jsonify({"hata": "Hedef klasör mevcut değil."}), 400

    kitap_haritasi = {k['id']: k for k in mevcut_tarama.get('kitaplar', [])}
    basarili_sayisi = 0
    hatalar = []

    for fid in dosya_idleri:
        if fid not in kitap_haritasi:
            continue
        k = kitap_haritasi[fid]
        kaynak_yol = k['dosya_yolu']
        hedef_yol = os.path.join(hedef_klasor, k['dosya_adi'])

        try:
            if eylem == 'kopyala':
                shutil.copy2(kaynak_yol, hedef_yol)
            else:
                shutil.move(kaynak_yol, hedef_yol)
            basarili_sayisi += 1
        except Exception as e:
            hatalar.append(f"{k['dosya_adi']}: {e}")

    return jsonify({
        "basarili": True,
        "eylem": eylem,
        "sayi": basarili_sayisi,
        "hatalar": hatalar
    })

@app.route('/api/sil', methods=['POST'])
def api_sil():
    """Seçilen dosyaları çöp kutusuna / '_silinenler' klasörüne taşır veya siler."""
    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])
    kalici = data.get('kalici', False)

    kitap_haritasi = {k['id']: k for k in mevcut_tarama.get('kitaplar', [])}
    hedef_cop = os.path.join(mevcut_tarama.get('hedef_dizin', KOK_DIZIN), '_silinenler')
    
    if not kalici:
        os.makedirs(hedef_cop, exist_ok=True)

    silinenler = []
    hatalar = []

    for fid in dosya_idleri:
        if fid not in kitap_haritasi:
            continue
        k = kitap_haritasi[fid]
        yol = k['dosya_yolu']
        if not os.path.exists(yol):
            continue

        try:
            if kalici:
                os.remove(yol)
            else:
                hedef_yol = os.path.join(hedef_cop, k['dosya_adi'])
                shutil.move(yol, hedef_yol)
            silinenler.append(k['dosya_adi'])
        except Exception as e:
            hatalar.append(f"{k['dosya_adi']}: {e}")

    return jsonify({
        "basarili": True,
        "silinen_sayisi": len(silinenler),
        "hatalar": hatalar
    })

@app.route('/api/dosya-eylem', methods=['POST'])
def api_dosya_eylem():
    """Dosyayı Windows varsayılan uygulamasıyla açar veya Windows Gezgini'nde gösterir."""
    data = request.json or {}
    dosya_yolu = data.get('dosya_yolu', '')
    eylem = data.get('eylem', 'ac') # 'ac' veya 'klasorde_goster'

    if not dosya_yolu or not os.path.exists(dosya_yolu):
        return jsonify({"hata": "Dosya bulunamadı."}), 404

    try:
        if eylem == 'ac':
            os.startfile(dosya_yolu)
        elif eylem == 'klasorde_goster':
            p = os.path.normpath(dosya_yolu)
            try:
                subprocess.Popen(f'explorer.exe /select,"{p}"')
            except Exception:
                os.startfile(os.path.dirname(p))
        return jsonify({"basarili": True})
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route('/api/kutuphaneye-ekle', methods=['POST'])
def api_kutuphaneye_ekle():
    """
    Seçili kitap dosyalarını ana kütüphaneye (hepsi.json, kitaplik.db, veri.js) ekler,
    kapaklarını çıkarır ve arşivi anında günceller.
    """
    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])

    if not dosya_idleri:
        return jsonify({"basarili": False, "mesaj": "Eklenecek kitap seçilmedi."}), 400

    if not mevcut_tarama or 'kitaplar' not in mevcut_tarama:
        return jsonify({"basarili": False, "mesaj": "Önce bir klasör taraması yapmalısınız."}), 400

    kitap_haritasi = {k['id']: k for k in mevcut_tarama['kitaplar']}
    eklenenler = []
    hatalar = []

    # hepsi.json oku
    hepsi_yolu = os.path.join(ARSIV_DIZIN, 'veri', 'onbellek', 'hepsi.json')
    ham_arsiv = []
    if os.path.exists(hepsi_yolu):
        try:
            with open(hepsi_yolu, 'r', encoding='utf8') as f:
                ham_arsiv = json.load(f)
        except Exception as e:
            print(f"[!] hepsi.json okuma hatası: {e}")

    mevcut_isbnler = {str(k.get('isbn')) for k in ham_arsiv if k.get('isbn')}

    for fid in dosya_idleri:
        if fid not in kitap_haritasi:
            continue
        k = kitap_haritasi[fid]
        dosya_yolu = k['dosya_yolu']
        analiz = k.get('analiz', {})
        baslik = analiz.get('tespit_baslik') or os.path.splitext(k['dosya_adi'])[0]
        yazar = analiz.get('tespit_yazar') or ''
        ext = os.path.splitext(dosya_yolu)[1].lower()

        # Zaten kütüphanede var mı kontrolü
        if k.get('kutuphanede_var') and not data.get('zorla'):
            continue

        # Benzersiz ISBN / ID oluştur
        hash_id = hashlib.md5(f"{norm(baslik)}_{norm(yazar)}".encode('utf-8')).hexdigest()[:10].upper()
        yeni_isbn = f"DOSYA_{hash_id}"
        
        # Eğer bu ISBN zaten hepsi.json içinde varsa
        if yeni_isbn in mevcut_isbnler and not data.get('zorla'):
            k['kutuphanede_var'] = True
            continue

        # Kapak görseli çıkarma (PyMuPDF / fitz)
        kapak_dosya_adi = None
        try:
            import fitz
            doc = fitz.open(dosya_yolu)
            if len(doc) > 0:
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=150)
                k_ad = f"{yeni_isbn}_b.jpg"
                for k_diz in [os.path.join(ARSIV_DIZIN, 'uygulama', 'kapaklar'), os.path.join(KOK_DIZIN, 'kapaklar')]:
                    os.makedirs(k_diz, exist_ok=True)
                    pix.save(os.path.join(k_diz, k_ad))
                kapak_dosya_adi = k_ad
            doc.close()
        except Exception as e:
            pass

        yeni_kayit = {
            'isbn': yeni_isbn,
            'baslik_csv': baslik,
            'yazar_belirtilen': yazar,
            'sure_sn': 0,
            'ilerleme': 100,
            'format': ext.replace('.', '').upper() if ext else 'E-Kitap',
            'baslangic': datetime.now().strftime('%Y-%m-%d'),
            'son_dinleme': datetime.now().strftime('%Y-%m-%d'),
            'storytel': {},
            'kitapyurdu': {
                'yayinevi': '',
                'tanitim': f"{baslik} - {yazar} ({ext.upper()} formatında yerel kütüphane dosyası)",
                'kapak': None
            },
            'kapak_sesli': None,
            'kapak_basili': kapak_dosya_adi
        }

        ham_arsiv.append(yeni_kayit)
        mevcut_isbnler.add(yeni_isbn)
        eklenenler.append(f"{baslik} - {yazar}")
        k['kutuphanede_var'] = True

    if eklenenler and olustur:
        try:
            # 1. hepsi.json'ı kaydet
            with open(hepsi_yolu, 'w', encoding='utf8') as f:
                json.dump(ham_arsiv, f, ensure_ascii=False, indent=2)

            # 2. olustur ile donustur ve kitaplik.db oluştur
            liste = [olustur.donustur(item) for item in ham_arsiv]
            olustur.veritabani(liste)

            # 3. veri.js güncelle (hem uygulama/veri.js hem ana veri.js)
            veri_js_icerik = 'window.KITAPLIK = ' + json.dumps(liste, ensure_ascii=False) + ';\n'
            with open(os.path.join(ARSIV_DIZIN, 'uygulama', 'veri.js'), 'w', encoding='utf8') as f:
                f.write(veri_js_icerik)
            ust_veri_js = os.path.join(KOK_DIZIN, 'veri.js')
            with open(ust_veri_js, 'w', encoding='utf8') as f:
                f.write(veri_js_icerik)

            # 4. Referans havuzunu yeniden yükle
            referans_havuz.yukle()

            # 5. Sayacı güncelle
            if 'sayaclar' in mevcut_tarama:
                mevcut_tarama['sayaclar']['kutuphanede_yok'] = max(0, mevcut_tarama['sayaclar'].get('kutuphanede_yok', 0) - len(eklenenler))

        except Exception as e:
            hatalar.append(f"Kütüphane güncelleme hatası: {e}")

    return jsonify({
        "basarili": len(hatalar) == 0,
        "eklenen_sayisi": len(eklenenler),
        "eklenenler": eklenenler,
        "hatalar": hatalar
    })

@app.route('/api/donustur', methods=['POST'])
def api_donustur():
    """
    Calibre ebook-convert kullanarak seçili kitapları hedef formata dönüştürür.
    Örn: EPUB -> PDF veya PDF -> EPUB.
    """
    if not CALIBRE_YOLU:
        return jsonify({"hata": "Calibre programı sistemde bulunamadı. Lütfen Calibre yükleyin."}), 400

    data = request.json or {}
    dosya_idleri = data.get('id_listesi', [])
    hedef_format = data.get('hedef_format', 'pdf').lower().replace('.', '')

    islem_id = f"donus_{int(time.time())}"
    donusturme_durumlari[islem_id] = {
        "durum": "basladi",
        "toplam": len(dosya_idleri),
        "tamamlanan": 0,
        "hatali": 0,
        "loglar": [],
        "bitti": False
    }

    def _arka_plan_donustur():
        st = donusturme_durumlari[islem_id]
        kitap_haritasi = {k['id']: k for k in mevcut_tarama.get('kitaplar', [])}

        for fid in dosya_idleri:
            if fid not in kitap_haritasi:
                continue
            k = kitap_haritasi[fid]
            girdi_yolu = k['dosya_yolu']
            girdi_dizin = os.path.dirname(girdi_yolu)
            kok_ad, _ = os.path.splitext(k['dosya_adi'])
            cikti_yolu = os.path.join(girdi_dizin, f"{kok_ad}.{hedef_format}")

            st['loglar'].append(f"Dönüştürülüyor: {k['dosya_adi']} -> {hedef_format.upper()}...")
            cmd = [CALIBRE_YOLU, girdi_yolu, cikti_yolu]

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0 and os.path.exists(cikti_yolu):
                    st['tamamlanan'] += 1
                    st['loglar'].append(f"[OK] Tamamlandı: {os.path.basename(cikti_yolu)}")
                else:
                    st['hatali'] += 1
                    hata_mesaji = res.stderr or res.stdout or "Bilinmeyen hata"
                    st['loglar'].append(f"[HATA] {k['dosya_adi']}: {hata_mesaji[:200]}")
            except Exception as e:
                st['hatali'] += 1
                st['loglar'].append(f"[HATA] {k['dosya_adi']}: {e}")

        st['bitti'] = True
        st['durum'] = "tamamlandi"

    threading.Thread(target=_arka_plan_donustur).start()
    return jsonify({"basarili": True, "islem_id": islem_id})

@app.route('/api/donustur-durum/<islem_id>')
def api_donustur_durum(islem_id):
    st = donusturme_durumlari.get(islem_id)
    if not st:
        return jsonify({"hata": "İşlem bulunamadı."}), 404
    return jsonify(st)

# ==============================================================================
# 8. MODERN WEB ARAYÜZÜ (HTML & CSS & JAVASCRIPT)
# ==============================================================================
HTML_SABLON = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Sonsuz Okumalar - Kitap Düzenleyici & Format Yöneticisi</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>
:root {
  --arka-koyu: #0d1117;
  --panel-koyu: #161b22;
  --panel-kenar: #30363d;
  --metin-ana: #c9d1d9;
  --metin-soluk: #8b949e;
  --metin-baslik: #f0f6fc;
  --vurgu-mavi: #58a6ff;
  --vurgu-yesil: #3fb950;
  --vurgu-sari: #d29922;
  --vurgu-kirmizi: #f85149;
  --vurgu-mor: #bc8cff;
  --kart-arkaplan: #21262d;
  --tablo-hover: #1c2128;
  --tablo-secili: rgba(56, 139, 253, 0.15);
}

[data-tema="acik"] {
  --arka-koyu: #f6f8fa;
  --panel-koyu: #ffffff;
  --panel-kenar: #d0d7de;
  --metin-ana: #24292f;
  --metin-soluk: #57606a;
  --metin-baslik: #1f2328;
  --vurgu-mavi: #0969da;
  --vurgu-yesil: #1a7f37;
  --vurgu-sari: #9a6700;
  --vurgu-kirmizi: #cf222e;
  --vurgu-mor: #8250df;
  --kart-arkaplan: #f3f4f6;
  --tablo-hover: #f1f3f5;
  --tablo-secili: rgba(9, 105, 218, 0.1);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--arka-koyu);
  color: var(--metin-ana);
  line-height: 1.5;
  padding-bottom: 90px;
}

header {
  background-color: var(--panel-koyu);
  border-bottom: 1px solid var(--panel-kenar);
  padding: 12px 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.ust-cubuk {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.marka {
  display: flex;
  align-items: center;
  gap: 12px;
}
.marka img {
  width: 36px;
  height: 36px;
  border-radius: 8px;
}
.marka h1 {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--metin-baslik);
}
.marka span {
  font-size: 0.8rem;
  color: var(--vurgu-mavi);
  display: block;
}

.ust-araclar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--panel-kenar);
  background: var(--panel-koyu);
  color: var(--metin-baslik);
  transition: all 0.2s;
  text-decoration: none;
}
.btn:hover {
  background: var(--kart-arkaplan);
  border-color: var(--metin-soluk);
}
.btn-primer {
  background: var(--vurgu-mavi);
  color: #fff;
  border-color: transparent;
}
.btn-primer:hover {
  filter: brightness(1.1);
  background: var(--vurgu-mavi);
}
.btn-yesil {
  background: var(--vurgu-yesil);
  color: #fff;
  border-color: transparent;
}
.btn-kirmizi {
  background: var(--vurgu-kirmizi);
  color: #fff;
  border-color: transparent;
}
.btn-sari {
  background: var(--vurgu-sari);
  color: #fff;
  border-color: transparent;
}
.btn-mor {
  background: var(--vurgu-mor);
  color: #fff;
  border-color: transparent;
}

.ana-icerik {
  max-width: 1400px;
  margin: 20px auto;
  padding: 0 20px;
}

/* Klasör Seçim Çubuğu */
.klasor-kapsul {
  background: var(--panel-koyu);
  border: 1px solid var(--panel-kenar);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.klasor-girdi {
  flex: 1;
  min-width: 280px;
  display: flex;
  align-items: center;
  position: relative;
}
.klasor-girdi input {
  width: 100%;
  padding: 9px 12px;
  background: var(--arka-koyu);
  border: 1px solid var(--panel-kenar);
  border-radius: 6px;
  color: var(--metin-baslik);
  font-size: 0.9rem;
}
.hizli-kisayol {
  font-size: 0.8rem;
  color: var(--metin-soluk);
}
.hizli-kisayol a {
  color: var(--vurgu-mavi);
  text-decoration: none;
  cursor: pointer;
  margin: 0 4px;
}
.hizli-kisayol a:hover {
  text-decoration: underline;
}

/* İstatistik Kartları */
.kartlar-izgara {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.kart {
  background: var(--panel-koyu);
  border: 1px solid var(--panel-kenar);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s;
}
.kart:hover {
  transform: translateY(-2px);
  border-color: var(--vurgu-mavi);
}
.kart.aktif {
  border-color: var(--vurgu-mavi);
  background: var(--kart-arkaplan);
}
.kart-baslik {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--metin-soluk);
  text-transform: uppercase;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.kart-deger {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--metin-baslik);
}

.rozet {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 12px;
  font-size: 0.72rem;
  font-weight: 700;
}
.rozet-pdf { background: rgba(248, 81, 73, 0.2); color: var(--vurgu-kirmizi); border: 1px solid var(--vurgu-kirmizi); }
.rozet-epub { background: rgba(88, 166, 255, 0.2); color: var(--vurgu-mavi); border: 1px solid var(--vurgu-mavi); }
.rozet-cift { background: rgba(63, 185, 80, 0.2); color: var(--vurgu-yesil); border: 1px solid var(--vurgu-yesil); }
.rozet-mukerrer { background: rgba(210, 153, 34, 0.2); color: var(--vurgu-sari); border: 1px solid var(--vurgu-sari); }
.rozet-kaynak { background: rgba(188, 140, 255, 0.15); color: var(--vurgu-mor); }

/* Filtreleme ve Arama Çubuğu */
.liste-baslik-alani {
  background: var(--panel-koyu);
  border: 1px solid var(--panel-kenar);
  border-radius: 10px 10px 0 0;
  padding: 12px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.sekmeler {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.sekme-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--metin-soluk);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}
.sekme-btn:hover {
  background: var(--kart-arkaplan);
  color: var(--metin-baslik);
}
.sekme-btn.aktif {
  background: var(--vurgu-mavi);
  color: #fff;
}

.hizli-ara {
  padding: 6px 12px;
  border-radius: 6px;
  background: var(--arka-koyu);
  border: 1px solid var(--panel-kenar);
  color: var(--metin-baslik);
  font-size: 0.85rem;
  width: 240px;
}

/* Tablo Yapısı */
.tablo-kapsul {
  background: var(--panel-koyu);
  border: 1px solid var(--panel-kenar);
  border-top: none;
  border-radius: 0 0 10px 10px;
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.88rem;
}
th {
  background: var(--kart-arkaplan);
  color: var(--metin-soluk);
  padding: 10px 14px;
  font-size: 0.8rem;
  font-weight: 600;
  border-bottom: 1px solid var(--panel-kenar);
  position: sticky;
  top: 61px;
  z-index: 10;
}
td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--panel-kenar);
  vertical-align: middle;
}
tr:hover {
  background-color: var(--tablo-hover);
}
tr.secili {
  background-color: var(--tablo-secili);
}

.dosya-adi-hucre {
  font-weight: 600;
  color: var(--metin-baslik);
  word-break: break-all;
}
.onerilen-hucre {
  color: var(--vurgu-yesil);
  font-weight: 600;
  word-break: break-all;
}
.onerilen-hucre input {
  width: 100%;
  padding: 4px 8px;
  background: var(--arka-koyu);
  border: 1px solid var(--vurgu-yesil);
  border-radius: 4px;
  color: var(--metin-baslik);
  font-size: 0.85rem;
}

/* Yüzen İşlem Çubuğu */
.yuzen-arac-cubugu {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--panel-koyu);
  border: 2px solid var(--vurgu-mavi);
  border-radius: 30px;
  padding: 10px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  z-index: 1000;
  animation: slideUp 0.25s ease-out;
}
@keyframes slideUp {
  from { bottom: -60px; opacity: 0; }
  to { bottom: 20px; opacity: 1; }
}

/* Modal Dialog */
.modal-perde {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(3px);
}
.modal-kutu {
  background: var(--panel-koyu);
  border: 1px solid var(--panel-kenar);
  border-radius: 12px;
  max-width: 650px;
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 12px 36px rgba(0,0,0,0.6);
  padding: 24px;
}
.modal-baslik {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--metin-baslik);
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-kapat {
  background: none;
  border: none;
  color: var(--metin-soluk);
  font-size: 1.4rem;
  cursor: pointer;
}
.konsol-cikti {
  background: #000;
  color: #00ff66;
  font-family: monospace;
  font-size: 0.8rem;
  padding: 12px;
  border-radius: 6px;
  max-height: 250px;
  overflow-y: auto;
  white-space: pre-wrap;
  margin: 12px 0;
}

/* Bildirim Kutusu */
.bildirim-kutusu {
  position: fixed;
  top: 75px;
  right: 20px;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bildirim {
  padding: 12px 18px;
  border-radius: 8px;
  color: #fff;
  font-weight: 600;
  font-size: 0.88rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  animation: fadeIn 0.3s;
}
.bildirim-basari { background: var(--vurgu-yesil); }
.bildirim-hata { background: var(--vurgu-kirmizi); }
.bildirim-bilgi { background: var(--vurgu-mavi); }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
</head>
<body data-tema="koyu">

<header>
  <div class="ust-cubuk">
    <div class="marka">
      <img src="/logo.png" alt="Sonsuz Okumalar Logo" onerror="this.style.display='none'">
      <div>
        <h1>Sonsuz Okumalar - Kitap Düzenleyici</h1>
        <span>Google Drive, Telegram &amp; Anna's Archive Dosya Yöneticisi</span>
      </div>
    </div>
    
    <div class="ust-araclar">
      <a href="/yonetici_paneli.html" class="btn" style="border-color:var(--vurgu-sari);color:var(--vurgu-sari);font-weight:700;" title="Merkezi Yönetici Paneli (Şifreli)">🔒 Yönetici Paneli</a>
      <a href="/index.html" class="btn" title="Ana Kütüphaneye Dön">📚 Kütüphaneyi Aç</a>
      <button id="btnGeriAl" class="btn" onclick="adlandirmaGeriAl()" title="Son yapılan yeniden adlandırmayı geri al">↩️ Son İşlemi Geri Al</button>
      <button id="btnTema" class="btn" onclick="temaDegistir()">☀️ Açık Mod</button>
    </div>
  </div>
</header>

<div class="bildirim-kutusu" id="bildirimKutusu"></div>

<main class="ana-icerik">
  <!-- Klasör Seçimi -->
  <div class="klasor-kapsul">
    <button class="btn btn-primer" onclick="klasorDiyaloguAc()">📁 Klasör Seç...</button>
    <div class="klasor-girdi">
      <input type="text" id="hedefKlasor" placeholder="Düzenlenecek klasörün tam yolu (Örn: C:\\Kitaplar)..." value="{{ varsayilan_klasor }}">
    </div>
    <label style="display:flex;align-items:center;gap:6px;font-size:0.85rem;cursor:pointer;">
      <input type="checkbox" id="altDizinler" checked>
      <span>Alt Klasörleri de Tara</span>
    </label>
    <button class="btn btn-yesil" onclick="klasorTara()">🔍 Klasörü Tara &amp; Çözümle</button>
    <button class="btn btn-mor" onclick="secilenleriKutuphaneyeEkle()" title="Seçilen kitapları ana kütüphaneye (veri.js, kitaplik.db) ekle">➕ Seçilenleri Kütüphaneye Ekle</button>
    
    <div style="width:100%;margin-top:6px;" class="hizli-kisayol">
      Hızlı Seçim: 
      <a onclick="hizliSec('varsayilan')">Okunanlar / kitaplar</a> | 
      <a onclick="hizliSec('indirilenler')">İndirilenler / Downloads</a> | 
      <a onclick="hizliSec('telegram')">Telegram Desktop</a>
    </div>
  </div>

  <!-- İstatistik Kartları -->
  <div class="kartlar-izgara">
    <div class="kart aktif" onclick="sekmeDegistir('hepsi')">
      <div class="kart-baslik">Toplam Dosya</div>
      <div class="kart-deger" id="sayacToplam">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('hem_pdf_hem_epub')">
      <div class="kart-baslik">Hem PDF Hem EPUB <span class="rozet rozet-cift">Tam Set</span></div>
      <div class="kart-deger" id="sayacCift" style="color:var(--vurgu-yesil);">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('sadece_epub')">
      <div class="kart-baslik">Sadece EPUB <span class="rozet rozet-epub">EPUB</span></div>
      <div class="kart-deger" id="sayacSadeceEpub" style="color:var(--vurgu-mavi);">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('sadece_pdf')">
      <div class="kart-baslik">Sadece PDF <span class="rozet rozet-pdf">PDF</span></div>
      <div class="kart-deger" id="sayacSadecePdf" style="color:var(--vurgu-kirmizi);">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('mukerrer')">
      <div class="kart-baslik">Mükerrerler <span class="rozet rozet-mukerrer">Tekrar</span></div>
      <div class="kart-deger" id="sayacMukerrer" style="color:var(--vurgu-sari);">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('isim_degisecek')">
      <div class="kart-baslik">İsim Düzeltilecek <span class="rozet rozet-kaynak">Format</span></div>
      <div class="kart-deger" id="sayacIsim" style="color:var(--vurgu-mor);">0</div>
    </div>
    <div class="kart" onclick="sekmeDegistir('kutuphanede_yok')">
      <div class="kart-baslik">Kütüphanede Yok <span class="rozet rozet-kaynak" style="background:rgba(239,68,68,0.15);color:#f87171;">Eksik</span></div>
      <div class="kart-deger" id="sayacKutuphanedeYok" style="color:#f87171;">0</div>
    </div>
  </div>

  <!-- Liste ve Tablo -->
  <div class="liste-baslik-alani">
    <div class="sekmeler">
      <button class="sekme-btn aktif" data-sekme="hepsi" onclick="sekmeDegistir('hepsi')">📑 Tümü (<span id="sekmeToplam">0</span>)</button>
      <button class="sekme-btn" data-sekme="hem_pdf_hem_epub" onclick="sekmeDegistir('hem_pdf_hem_epub')">🔄 Hem PDF Hem EPUB (<span id="sekmeCift">0</span>)</button>
      <button class="sekme-btn" data-sekme="sadece_epub" onclick="sekmeDegistir('sadece_epub')">📗 Sadece EPUB (<span id="sekmeSadeceEpub">0</span>)</button>
      <button class="sekme-btn" data-sekme="sadece_pdf" onclick="sekmeDegistir('sadece_pdf')">📕 Sadece PDF (<span id="sekmeSadecePdf">0</span>)</button>
      <button class="sekme-btn" data-sekme="mukerrer" onclick="sekmeDegistir('mukerrer')">⚠️ Mükerrer Dosyalar (<span id="sekmeMukerrer">0</span>)</button>
      <button class="sekme-btn" data-sekme="isim_degisecek" onclick="sekmeDegistir('isim_degisecek')">✏️ İsim Düzenlenecekler (<span id="sekmeIsim">0</span>)</button>
      <button class="sekme-btn" data-sekme="kutuphanede_yok" onclick="sekmeDegistir('kutuphanede_yok')">➕ Kütüphanede Olmayanlar (<span id="sekmeKutuphanedeYok">0</span>)</button>
    </div>
    <input type="search" id="filtreArama" class="hizli-ara" placeholder="Listede filtrele veya ara…" oninput="tabloyuFiltrele()">
  </div>

  <div class="tablo-kapsul">
    <table id="kitapTablosu">
      <thead>
        <tr>
          <th style="width:40px;"><input type="checkbox" id="tumunuSecKutusu" onchange="tumunuSecToggle(this)"></th>
          <th>Mevcut Dosya Adı</th>
          <th style="width:80px;">Format</th>
          <th style="width:85px;">Boyut</th>
          <th>Tespit Edilen Kitap Adı &amp; Yazar</th>
          <th>Önerilen İsim (Kitap Adı - Yazar)</th>
          <th style="width:130px;">Eşleşme Kaynağı</th>
          <th style="width:190px;text-align:right;">İşlemler</th>
        </tr>
      </thead>
      <tbody id="tabloGovde">
        <tr>
          <td colspan="8" style="text-align:center;padding:40px;color:var(--metin-soluk);">
            Yukarıdaki "🔍 Klasörü Tara &amp; Çözümle" butonuna basarak kitaplarınızı tarayın.
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</main>

<!-- Yüzen Toplu İşlem Çubuğu -->
<div id="yuzenCubuk" class="yuzen-arac-cubugu" style="display:none;">
  <span style="font-weight:700;color:var(--metin-baslik);"><span id="seciliSayisi">0</span> dosya seçildi</span>
  <button class="btn btn-yesil" onclick="secilenleriKutuphaneyeEkle()" title="Seçilen kitapları ana kütüphaneye ekle">➕ Kütüphaneye Ekle</button>
  <button class="btn btn-yesil" onclick="secilenleriAdlandir()" title="Seçili dosyaların adını Kitap Adı - Yazar.uzantı formatına çevir">🏷️ İsimleri Düzelt (Kitap - Yazar)</button>
  <button class="btn btn-mor" onclick="formatDonusturmeModaliAc()" title="Seçilenleri Calibre ile PDF veya EPUB formatına dönüştür">🔄 Format Dönüştür</button>
  <button class="btn btn-sari" onclick="secilenMukerrerleriArsivle()" title="Seçili mükerrer kopyaları _mukerrer_arsiv klasörüne taşı">🧹 Mükerrerleri Arşivle</button>
  <button class="btn btn-primer" onclick="kopyalaTasiModaliAc('kopyala')">📋 Kopyala</button>
  <button class="btn btn-primer" onclick="kopyalaTasiModaliAc('tasi')">🚚 Taşı</button>
  <button class="btn btn-kirmizi" onclick="secilenleriSil()">🗑️ Sil</button>
  <button class="btn" onclick="secimiTemizle()">✕</button>
</div>

<!-- Format Dönüştürme Modalı -->
<div id="donusturmeModal" class="modal-perde" style="display:none;">
  <div class="modal-kutu">
    <div class="modal-baslik">
      <span>🔄 Calibre ile Format Dönüştürme</span>
      <button class="modal-kapat" onclick="modalKapat('donusturmeModal')">✕</button>
    </div>
    <div id="modalCalibreDurum" style="display:block;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:0.85rem;font-weight:600;background:rgba(88,166,255,0.08);border:1px solid var(--panel-kenar);">
      ⚙️ Calibre Dönüştürücü kontrol ediliyor...
    </div>
    <p style="margin-bottom:12px;font-size:0.9rem;color:var(--metin-soluk);">
      Seçilen <strong id="donusturulecekSayi" style="color:var(--metin-baslik);">0</strong> adet dosya dönüştürülecek.
    </p>
    <div style="margin-bottom:16px;">
      <label style="font-weight:600;font-size:0.85rem;display:block;margin-bottom:6px;">Hedef Format:</label>
      <select id="hedefFormatSecim" style="padding:8px 12px;border-radius:6px;background:var(--arka-koyu);border:1px solid var(--panel-kenar);color:var(--metin-baslik);width:100%;">
        <option value="pdf">PDF Belgesi (.pdf)</option>
        <option value="epub">EPUB E-Kitap (.epub)</option>
        <option value="mobi">MOBI (.mobi)</option>
        <option value="azw3">Kindle AZW3 (.azw3)</option>
        <option value="txt">Düz Metin (.txt)</option>
      </select>
    </div>
    <div id="donusturmeKonsolKutusu" style="display:none;">
      <div style="font-size:0.8rem;font-weight:600;color:var(--metin-soluk);">Canlı Konsol Çıktısı:</div>
      <div id="donusturmeKonsol" class="konsol-cikti">Dönüştürme başlatılıyor...</div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:16px;">
      <button class="btn" onclick="modalKapat('donusturmeModal')">İptal</button>
      <button id="btnDonusturBaslat" class="btn btn-mor" onclick="donusturmeBaslat()">Dönüştürmeyi Başlat</button>
    </div>
  </div>
</div>

<!-- Kopyala / Taşı Modalı -->
<div id="kopyalaTasiModal" class="modal-perde" style="display:none;">
  <div class="modal-kutu">
    <div class="modal-baslik">
      <span id="kopyalaTasiBaslik">📋 Dosyaları Kopyala</span>
      <button class="modal-kapat" onclick="modalKapat('kopyalaTasiModal')">✕</button>
    </div>
    <p style="margin-bottom:12px;font-size:0.9rem;color:var(--metin-soluk);">
      Seçilen <strong id="kopyalaTasiSayi">0</strong> dosya aşağıdaki klasöre aktarılacak.
    </p>
    <div style="margin-bottom:16px;">
      <label style="font-weight:600;font-size:0.85rem;display:block;margin-bottom:6px;">Hedef Klasör Yolu:</label>
      <input type="text" id="kopyalaTasiHedef" placeholder="C:\\HedefKlasor..." style="width:100%;padding:8px 12px;border-radius:6px;background:var(--arka-koyu);border:1px solid var(--panel-kenar);color:var(--metin-baslik);">
    </div>
    <div style="display:flex;justify-content:flex-end;gap:10px;">
      <button class="btn" onclick="modalKapat('kopyalaTasiModal')">İptal</button>
      <button id="btnKopyalaTasiOnay" class="btn btn-primer" onclick="kopyalaTasiUygula()">Uygula</button>
    </div>
  </div>
</div>

<script>
let tumKitaplar = [];
let aktifSekme = 'hepsi';
let seciliIdler = new Set();
let mevcutDonusumId = null;

document.addEventListener('DOMContentLoaded', () => {
  klasorTara();
});

function temaDegistir() {
  const b = document.body;
  const btn = document.getElementById('btnTema');
  if (b.getAttribute('data-tema') === 'koyu') {
    b.setAttribute('data-tema', 'acik');
    btn.textContent = '🌙 Koyu Mod';
  } else {
    b.setAttribute('data-tema', 'koyu');
    btn.textContent = '☀️ Açık Mod';
  }
}

function bildirimGoster(mesaj, tip = 'bilgi') {
  const k = document.getElementById('bildirimKutusu');
  const d = document.createElement('div');
  d.className = `bildirim bildirim-${tip}`;
  d.textContent = mesaj;
  k.appendChild(d);
  setTimeout(() => d.remove(), 4000);
}

function hizliSec(tur) {
  const inp = document.getElementById('hedefKlasor');
  if (tur === 'varsayilan') {
    inp.value = {{ varsayilan_klasor|tojson }};
  } else if (tur === 'indirilenler') {
    inp.value = {{ downloads_klasor|tojson }};
  } else if (tur === 'telegram') {
    inp.value = {{ telegram_klasor|tojson }};
  }
  klasorTara();
}

async function calibreDurumunuGetir() {
  try {
    const res = await fetch('/api/calibre-durum');
    const data = await res.json();
    const kutu = document.getElementById('calibreDurumKutusu');
    const yazi = document.getElementById('calibreDurumYazi');
    const rozet = document.getElementById('calibreRozet');

    kutu.style.display = 'flex';
    if (data.calibre_mevcut) {
      yazi.textContent = `${data.calibre_yolu} (Hazır)`;
      rozet.className = 'rozet rozet-cift';
      rozet.textContent = 'Calibre Algılandı';
    } else {
      yazi.textContent = 'Calibre yüklü değil veya bulunamadı. Dönüştürme için Calibre önerilir.';
      rozet.className = 'rozet rozet-pdf';
      rozet.textContent = 'Calibre Eksik';
    }
  } catch(e) {}
}

async function klasorDiyaloguAc() {
  bildirimGoster('Windows klasör seçim penceresi açılıyor...', 'bilgi');
  try {
    const res = await fetch('/api/klasor-sec');
    const data = await res.json();
    if (data.basarili && data.klasor) {
      document.getElementById('hedefKlasor').value = data.klasor;
      klasorTara();
    }
  } catch(e) {
    bildirimGoster('Klasör diyalog hatası: ' + e, 'hata');
  }
}

function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function klasorTara() {
  const inp = document.getElementById('hedefKlasor');
  const klasor = inp ? inp.value.trim() : '';
  const altDizinler = document.getElementById('altDizinler') ? document.getElementById('altDizinler').checked : true;
  const btnTara = document.querySelector('.btn-yesil[onclick*="klasorTara"]');

  if (btnTara) {
    btnTara.disabled = true;
    btnTara.textContent = '⏳ Taranıyor...';
  }
  bildirimGoster('Kitap dosyaları taranıyor...', 'bilgi');

  const govde = document.getElementById('tabloGovde');
  if (govde) {
    govde.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:50px;color:var(--vurgu-mavi);">
      <div style="font-size:2rem;margin-bottom:10px;">⏳</div>
      <div style="font-weight:600;font-size:1.1rem;margin-bottom:6px;">Kitaplar taranıyor ve analiz ediliyor...</div>
      <div style="font-size:0.85rem;color:var(--metin-soluk);">Lütfen bekleyin, kitap sayısı fazla olduğunda birkaç saniye sürebilir.</div>
    </td></tr>`;
  }

  try {
    const res = await fetch('/api/tara', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({klasor, alt_dizinler: altDizinler})
    });
    const data = await res.json();
    if (data.hata) {
      bildirimGoster(data.hata, 'hata');
      if (govde) {
        govde.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:40px;color:#f85149;">❌ Hata: ${escHtml(data.hata)}</td></tr>`;
      }
      return;
    }

    tumKitaplar = data.kitaplar || [];
    sayaclariGuncelle(data.sayaclar);
    secimiTemizle();
    tabloyuYenile();
    bildirimGoster(`Tarama tamamlandı: ${tumKitaplar.length} dosya incelendi.`, 'basari');
  } catch(e) {
    bildirimGoster('Tarama sırasında hata oluştu: ' + e, 'hata');
    if (govde) {
      govde.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:40px;color:#f85149;">❌ Bağlantı hatası: ${escHtml(e)}</td></tr>`;
    }
  } finally {
    if (btnTara) {
      btnTara.disabled = false;
      btnTara.textContent = '🔍 Klasörü Tara & Çözümle';
    }
  }
}

function sayaclariGuncelle(s) {
  if (!s) return;
  document.getElementById('sayacToplam').textContent = s.toplam || 0;
  document.getElementById('sayacCift').textContent = s.hem_pdf_hem_epub || 0;
  document.getElementById('sayacSadeceEpub').textContent = s.sadece_epub || 0;
  document.getElementById('sayacSadecePdf').textContent = s.sadece_pdf || 0;
  document.getElementById('sayacMukerrer').textContent = s.mukerrer || 0;
  document.getElementById('sayacIsim').textContent = s.isim_duzeltilecek || 0;
  const cYok = document.getElementById('sayacKutuphanedeYok');
  if (cYok) cYok.textContent = s.kutuphanede_yok || 0;

  document.getElementById('sekmeToplam').textContent = s.toplam || 0;
  document.getElementById('sekmeCift').textContent = s.hem_pdf_hem_epub || 0;
  document.getElementById('sekmeSadeceEpub').textContent = s.sadece_epub || 0;
  document.getElementById('sekmeSadecePdf').textContent = s.sadece_pdf || 0;
  document.getElementById('sekmeMukerrer').textContent = s.mukerrer || 0;
  document.getElementById('sekmeIsim').textContent = s.isim_duzeltilecek || 0;
  const sYok = document.getElementById('sekmeKutuphanedeYok');
  if (sYok) sYok.textContent = s.kutuphanede_yok || 0;
}

function sekmeDegistir(sekmeAdi) {
  aktifSekme = sekmeAdi;
  document.querySelectorAll('.sekme-btn').forEach(btn => {
    btn.classList.toggle('aktif', btn.getAttribute('data-sekme') === sekmeAdi);
  });
  document.querySelectorAll('.kart').forEach(kart => {
    kart.classList.remove('aktif');
  });
  tabloyuYenile();
}

function tabloyuFiltrele() {
  tabloyuYenile();
}

function tabloyuYenile() {
  const govde = document.getElementById('tabloGovde');
  if (!govde) return;
  const aramaInput = document.getElementById('filtreArama');
  const arama = (aramaInput ? aramaInput.value : '').toLowerCase().trim();

  let filtrelenmis = tumKitaplar.filter(k => {
    // Sekme filtresi
    if (aktifSekme === 'hem_pdf_hem_epub' && k.format_durumu !== 'hem_pdf_hem_epub') return false;
    if (aktifSekme === 'sadece_epub' && k.format_durumu !== 'sadece_epub') return false;
    if (aktifSekme === 'sadece_pdf' && k.format_durumu !== 'sadece_pdf') return false;
    if (aktifSekme === 'mukerrer' && !k.mukerrer) return false;
    if (aktifSekme === 'isim_degisecek' && !(k.analiz && k.analiz.degisim_gerekli)) return false;
    if (aktifSekme === 'kutuphanede_yok' && k.kutuphanede_var) return false;

    // Arama filtresi
    if (arama) {
      const baslik = (k.analiz && k.analiz.tespit_baslik) ? k.analiz.tespit_baslik : '';
      const yazar = (k.analiz && k.analiz.tespit_yazar) ? k.analiz.tespit_yazar : '';
      const onerilen = (k.analiz && k.analiz.onerilen_ad) ? k.analiz.onerilen_ad : '';
      const txt = `${k.dosya_adi || ''} ${baslik} ${yazar} ${onerilen}`.toLowerCase();
      if (!txt.includes(arama)) return false;
    }
    return true;
  });

  if (filtrelenmis.length === 0) {
    govde.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--metin-soluk);">Bu kategoride veya filtrede dosya bulunamadı.</td></tr>`;
    return;
  }

  let html = '';
  filtrelenmis.forEach(k => {
    const isSecili = seciliIdler.has(k.id);
    const formatRozet = k.format === 'PDF' ? 'rozet-pdf' : (k.format === 'EPUB' ? 'rozet-epub' : 'rozet-cift');
    const degisimGerekli = k.analiz ? k.analiz.degisim_gerekli : false;
    const tespitBaslik = (k.analiz && k.analiz.tespit_baslik) ? k.analiz.tespit_baslik : '-';
    const tespitYazar = (k.analiz && k.analiz.tespit_yazar) ? k.analiz.tespit_yazar : '-';
    const onerilenAd = (k.analiz && k.analiz.onerilen_ad) ? k.analiz.onerilen_ad : (k.dosya_adi || '');
    const kaynak = (k.analiz && k.analiz.kaynak) ? k.analiz.kaynak : 'Dosya Adı';
    const guven = (k.analiz && k.analiz.guven) ? k.analiz.guven : 50;

    html += `
    <tr class="${isSecili ? 'secili' : ''}" id="satir_${escHtml(k.id)}">
      <td><input type="checkbox" class="satir-secim" data-id="${escHtml(k.id)}" ${isSecili ? 'checked' : ''} onchange="satirSecimDegisti('${escHtml(k.id)}', this.checked)"></td>
      
      <td class="dosya-adi-hucre">
        <div style="display:flex;align-items:center;gap:6px;">
          <span>${escHtml(k.dosya_adi)}</span>
          ${k.mukerrer ? `<span class="rozet rozet-mukerrer" title="${escHtml(k.mukerrer_nedeni || 'Mükerrer dosya')}">⚠️ Mükerrer</span>` : ''}
        </div>
        <div style="font-size:0.75rem;color:var(--metin-soluk);">${escHtml(k.rel_yol)}</div>
      </td>

      <td><span class="rozet ${formatRozet}">${escHtml(k.format)}</span></td>
      <td style="color:var(--metin-soluk);font-size:0.8rem;">${escHtml(k.boyut_str)}</td>

      <td>
        <div style="font-weight:600;color:var(--metin-baslik);">${escHtml(tespitBaslik)}</div>
        <div style="font-size:0.8rem;color:var(--vurgu-mavi);">${escHtml(tespitYazar)}</div>
        <div style="margin-top:4px;">
          ${k.kutuphanede_var 
            ? '<span class="rozet" style="background:rgba(16,185,129,0.15);color:#10b981;font-size:0.7rem;padding:2px 6px;">✅ Kütüphanede</span>' 
            : '<span class="rozet" style="background:rgba(239,68,68,0.15);color:#f87171;font-size:0.7rem;padding:2px 6px;">⚪ Kütüphanede Yok</span>'}
        </div>
      </td>

      <td class="onerilen-hucre">
        <input type="text" id="onerilen_${escHtml(k.id)}" value="${escHtml(onerilenAd)}" title="İsmi değiştirmek isterseniz buradan düzenleyip Enter'a basabilir veya 💾 butonuna tıklayabilirsiniz" onkeydown="if(event.key==='Enter') tekilAdlandir('${escHtml(k.id)}')">
      </td>

      <td>
        <span class="rozet rozet-kaynak" title="Güven Puanı: %${guven}">
          ${escHtml(kaynak)}
        </span>
      </td>

      <td style="text-align:right;">
        <div style="display:inline-flex;gap:4px;align-items:center;justify-content:flex-end;">
          ${!k.kutuphanede_var 
            ? `<button class="btn btn-yesil" style="padding:4px 7px;" onclick="tekilKutuphaneyeEkle('${escHtml(k.id)}')" title="Bu kitabı ana kütüphaneye ekle">➕</button>` 
            : `<button class="btn" style="padding:4px 7px;opacity:0.4;cursor:default;" title="Zaten kütüphanede mevcut" disabled>✅</button>`}
          <button class="btn" style="padding:4px 7px;" onclick="tekilAdlandir('${escHtml(k.id)}')" title="Yeni ismi kaydet / yeniden adlandır">💾</button>
          <button class="btn" style="padding:4px 7px;" onclick="dosyaEylemById('${escHtml(k.id)}', 'ac')" title="Dosyayı sistem okuyucusuyla aç">📖</button>
          <button class="btn" style="padding:4px 7px;" onclick="dosyaEylemById('${escHtml(k.id)}', 'klasorde_goster')" title="Windows Gezgini'nde klasörü aç ve dosyayı seç">📂</button>
          <button class="btn" style="padding:4px 7px;" onclick="tekilTasiModaliAc('${escHtml(k.id)}')" title="Bu dosyayı başka bir klasöre taşı">🚚</button>
          <button class="btn btn-kirmizi" style="padding:4px 7px;" onclick="tekilSil('${escHtml(k.id)}')" title="Bu dosyayı silinenler klasörüne taşı">🗑️</button>
        </div>
      </td>
    </tr>
    `;
  });

  govde.innerHTML = html;
  yuzenCubuguGuncelle();
}

function dosyaEylemById(id, eylem) {
  const k = tumKitaplar.find(item => item.id === id);
  if (k && k.dosya_yolu) {
    dosyaEylem(k.dosya_yolu, eylem);
  }
}

function satirSecimDegisti(id, secildi) {
  if (secildi) {
    seciliIdler.add(id);
  } else {
    seciliIdler.delete(id);
  }
  const satir = document.getElementById(`satir_${id}`);
  if (satir) satir.classList.toggle('secili', secildi);
  yuzenCubuguGuncelle();
}

function tumunuSecToggle(masterKutu) {
  const cbxs = document.querySelectorAll('.satir-secim');
  cbxs.forEach(cb => {
    cb.checked = masterKutu.checked;
    const id = cb.getAttribute('data-id');
    if (masterKutu.checked) {
      seciliIdler.add(id);
    } else {
      seciliIdler.delete(id);
    }
    const satir = document.getElementById(`satir_${id}`);
    if (satir) satir.classList.toggle('secili', masterKutu.checked);
  });
  yuzenCubuguGuncelle();
}

function secimiTemizle() {
  seciliIdler.clear();
  const master = document.getElementById('tumunuSecKutusu');
  if (master) master.checked = false;
  document.querySelectorAll('.satir-secim').forEach(c => c.checked = false);
  document.querySelectorAll('tr.secili').forEach(r => r.classList.remove('secili'));
  yuzenCubuguGuncelle();
}

function yuzenCubuguGuncelle() {
  const cubuk = document.getElementById('yuzenCubuk');
  const sayiSpan = document.getElementById('seciliSayisi');
  const adet = seciliIdler.size;

  if (adet > 0) {
    cubuk.style.display = 'flex';
    sayiSpan.textContent = adet;
  } else {
    cubuk.style.display = 'none';
  }
}

async function dosyaEylem(yol, eylem) {
  try {
    await fetch('/api/dosya-eylem', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dosya_yolu: yol, eylem: eylem})
    });
  } catch(e) {}
}

async function tekilAdlandir(id) {
  const inputEl = document.getElementById(`onerilen_${id}`);
  const yeniAd = inputEl ? inputEl.value.trim() : '';

  try {
    const res = await fetch('/api/adlandir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: [id], ozel_adlar: {[id]: yeniAd}})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster('Dosya başarıyla adlandırıldı!', 'basari');
      klasorTara();
    } else {
      bildirimGoster('Adlandırma hatası: ' + (data.hatalar||[]).join(', '), 'hata');
    }
  } catch(e) {
    bildirimGoster('Hata: ' + e, 'hata');
  }
}

async function secilenleriAdlandir() {
  if (seciliIdler.size === 0) return;
  const ozelAdlar = {};
  seciliIdler.forEach(id => {
    const inputEl = document.getElementById(`onerilen_${id}`);
    if (inputEl) ozelAdlar[id] = inputEl.value.trim();
  });

  bildirimGoster(`${seciliIdler.size} dosya standart formata dönüştürülüyor...`, 'bilgi');
  try {
    const res = await fetch('/api/adlandir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler), ozel_adlar: ozelAdlar})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.degistirilen_sayisi} dosya 'Kitap Adı - Yazar' formatında yeniden adlandırıldı!`, 'basari');
      klasorTara();
    }
  } catch(e) {
    bildirimGoster('Hata: ' + e, 'hata');
  }
}

async function adlandirmaGeriAl() {
  try {
    const res = await fetch('/api/geri-al', {method: 'POST'});
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.geri_alinan_sayisi} dosyanın ismi eski haline getirildi!`, 'basari');
      klasorTara();
    } else {
      bildirimGoster(data.mesaj, 'bilgi');
    }
  } catch(e) {
    bildirimGoster('Geri alma hatası: ' + e, 'hata');
  }
}

async function secilenMukerrerleriArsivle() {
  if (seciliIdler.size === 0) {
    bildirimGoster('Lütfen arşivlenecek mükerrer dosyaları seçin.', 'bilgi');
    return;
  }
  if (!confirm(`Seçili ${seciliIdler.size} mükerrer dosya '_mukerrer_arsiv' klasörüne taşınsın mı?`)) return;

  try {
    const res = await fetch('/api/mukerrer-temizle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler), islem: 'arsivle'})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.islem_goren_sayisi} mükerrer dosya güvenle arşivlendi!`, 'basari');
      klasorTara();
    }
  } catch(e) {
    bildirimGoster('Mükerrer arşivleme hatası: ' + e, 'hata');
  }
}

async function secilenleriSil() {
  if (seciliIdler.size === 0) return;
  if (!confirm(`Seçilen ${seciliIdler.size} dosyayı '_silinenler' çöp klasörüne taşımak istediğinizden emin misiniz?`)) return;

  try {
    const res = await fetch('/api/sil', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler), kalici: false})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.silinen_sayisi} dosya silinenler klasörüne taşındı.`, 'basari');
      klasorTara();
    }
  } catch(e) {
    bildirimGoster('Silme hatası: ' + e, 'hata');
  }
}

async function tekilSil(id) {
  const k = tumKitaplar.find(item => item.id === id);
  const dosyaAdi = k ? k.dosya_adi : 'Bu dosya';
  if (!confirm(`"${dosyaAdi}" dosyasını '_silinenler' çöp klasörüne taşımak istediğinizden emin misiniz?`)) return;

  try {
    const res = await fetch('/api/sil', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: [id], kalici: false})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`"${dosyaAdi}" silinenler klasörüne taşındı.`, 'basari');
      klasorTara();
    } else {
      bildirimGoster('Silme hatası: ' + (data.hatalar||[]).join(', '), 'hata');
    }
  } catch(e) {
    bildirimGoster('Silme hatası: ' + e, 'hata');
  }
}

function tekilTasiModaliAc(id) {
  seciliIdler = new Set([id]);
  kopyalaTasiModaliAc('tasi');
}

async function tekilKutuphaneyeEkle(id) {
  const k = tumKitaplar.find(item => item.id === id);
  const isim = (k && k.analiz && k.analiz.tespit_baslik) ? `${k.analiz.tespit_baslik} (${k.dosya_adi})` : (k ? k.dosya_adi : 'Kitap');
  
  bildirimGoster(`"${isim}" kütüphaneye ekleniyor...`, 'bilgi');
  try {
    const res = await fetch('/api/kutuphaneye-ekle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: [id]})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`"${isim}" ana kütüphaneye başarıyla eklendi!`, 'basari');
      if (k) k.kutuphanede_var = true;
      klasorTara();
    } else {
      bildirimGoster('Kütüphaneye ekleme hatası: ' + (data.hatalar||[]).join(', '), 'hata');
    }
  } catch(e) {
    bildirimGoster('Hata: ' + e, 'hata');
  }
}

async function secilenleriKutuphaneyeEkle() {
  if (seciliIdler.size === 0) {
    bildirimGoster('Lütfen kütüphaneye eklenecek kitapları seçin.', 'bilgi');
    return;
  }
  
  bildirimGoster(`Seçilen ${seciliIdler.size} kitap kütüphaneye ekleniyor...`, 'bilgi');
  try {
    const res = await fetch('/api/kutuphaneye-ekle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler)})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.eklenen_sayisi} kitap ana kütüphaneye başarıyla eklendi!`, 'basari');
      secimiTemizle();
      klasorTara();
    } else {
      bildirimGoster('Kütüphaneye ekleme hatası: ' + (data.hatalar||[]).join(', '), 'hata');
    }
  } catch(e) {
    bildirimGoster('Hata: ' + e, 'hata');
  }
}

// Modal Yönetimi
async function formatDonusturmeModaliAc() {
  if (seciliIdler.size === 0) return;
  document.getElementById('donusturulecekSayi').textContent = seciliIdler.size;
  document.getElementById('donusturmeKonsolKutusu').style.display = 'none';
  document.getElementById('donusturmeModal').style.display = 'flex';

  const uyari = document.getElementById('modalCalibreDurum');
  const btn = document.getElementById('btnDonusturBaslat');
  if (uyari) {
    uyari.style.display = 'block';
    uyari.style.color = 'var(--vurgu-mavi)';
    uyari.textContent = '⚙️ Calibre Dönüştürücü kontrol ediliyor...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/calibre-durum');
    const data = await res.json();
    if (data.calibre_mevcut) {
      if (uyari) {
        uyari.style.color = '#10b981';
        uyari.textContent = '✅ Calibre hazır: ' + data.calibre_yolu;
      }
      if (btn) btn.disabled = false;
    } else {
      if (uyari) {
        uyari.style.color = '#ef4444';
        uyari.textContent = '⚠️ Calibre programı bulunamadı. E-kitap dönüştürme için Calibre kurulu olmalıdır.';
      }
      if (btn) btn.disabled = true;
    }
  } catch(e) {
    if (uyari) {
      uyari.style.color = '#ef4444';
      uyari.textContent = 'Calibre durumu sorgulanamadı.';
    }
  }
}

function kopyalaTasiModaliAc(eylem) {
  if (seciliIdler.size === 0) return;
  document.getElementById('kopyalaTasiSayi').textContent = seciliIdler.size;
  document.getElementById('kopyalaTasiBaslik').textContent = eylem === 'kopyala' ? '📋 Dosyaları Kopyala' : '🚚 Dosyaları Taşı';
  document.getElementById('kopyalaTasiModal').setAttribute('data-eylem', eylem);
  document.getElementById('kopyalaTasiModal').style.display = 'flex';
}

function modalKapat(modalId) {
  document.getElementById(modalId).style.display = 'none';
}

async function kopyalaTasiUygula() {
  const eylem = document.getElementById('kopyalaTasiModal').getAttribute('data-eylem');
  const hedef = document.getElementById('kopyalaTasiHedef').value.trim();

  if (!hedef) {
    alert('Lütfen bir hedef klasör yolu girin.');
    return;
  }

  try {
    const res = await fetch('/api/kopyala-tasi', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler), hedef_klasor: hedef, eylem: eylem})
    });
    const data = await res.json();
    if (data.basarili) {
      bildirimGoster(`${data.sayi} dosya başarıyla ${eylem === 'kopyala' ? 'kopyalandı' : 'taşındı'}.`, 'basari');
      modalKapat('kopyalaTasiModal');
      klasorTara();
    } else {
      bildirimGoster(data.hata, 'hata');
    }
  } catch(e) {
    bildirimGoster('İşlem hatası: ' + e, 'hata');
  }
}

async function donusturmeBaslat() {
  const fmt = document.getElementById('hedefFormatSecim').value;
  const btn = document.getElementById('btnDonusturBaslat');
  const konsolKutu = document.getElementById('donusturmeKonsolKutusu');
  const konsol = document.getElementById('donusturmeKonsol');

  btn.disabled = true;
  konsolKutu.style.display = 'block';
  konsol.textContent = 'Dönüştürme başlatıldı...\\n';

  try {
    const res = await fetch('/api/donustur', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id_listesi: Array.from(seciliIdler), hedef_format: fmt})
    });
    const data = await res.json();
    if (data.basarili && data.islem_id) {
      mevcutDonusumId = data.islem_id;
      donusturmeDurumuTakip();
    } else {
      konsol.textContent += '\\nHATA: ' + data.hata;
      btn.disabled = false;
    }
  } catch(e) {
    konsol.textContent += '\\nBağlantı hatası: ' + e;
    btn.disabled = false;
  }
}

function donusturmeDurumuTakip() {
  if (!mevcutDonusumId) return;
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/donustur-durum/${mevcutDonusumId}`);
      const data = await res.json();
      const konsol = document.getElementById('donusturmeKonsol');
      konsol.textContent = (data.loglar || []).join('\\n');
      konsol.scrollTop = konsol.scrollHeight;

      if (data.bitti) {
        clearInterval(timer);
        document.getElementById('btnDonusturBaslat').disabled = false;
        bildirimGoster(`Dönüştürme tamamlandı: ${data.tamamlanan} başarılı, ${data.hatali} hatalı.`, 'basari');
        klasorTara();
      }
    } catch(e) {
      clearInterval(timer);
    }
  }, 1000);
}
</script>
</body>
</html>
"""

@app.route('/')
def ana_sayfa():
    varsayilan_k = os.path.join(KOK_DIZIN, 'kitaplar')
    downloads_k = os.path.join(os.path.expanduser('~'), 'Downloads')
    telegram_k = os.path.join(os.path.expanduser('~'), 'Downloads', 'Telegram Desktop')
    return render_template_string(
        HTML_SABLON,
        varsayilan_klasor=varsayilan_k,
        downloads_klasor=downloads_k,
        telegram_klasor=telegram_k
    )

@app.route('/logo.png')
def statik_logo():
    return send_from_directory(KOK_DIZIN, 'logo.png')

@app.route('/favicon.png')
def statik_favicon():
    return send_from_directory(KOK_DIZIN, 'favicon.png')

@app.route('/favicon.ico')
def statik_favicon_ico():
    return send_from_directory(KOK_DIZIN, 'favicon.ico')

@app.route('/index.html')
def statik_index_html():
    return send_from_directory(KOK_DIZIN, 'index.html')

@app.route('/yonetici_paneli.html')
def statik_yonetici_paneli():
    return send_from_directory(KOK_DIZIN, 'yonetici_paneli.html')

def bos_port_bul(baslangic=5050):
    import socket
    for p in range(baslangic, baslangic + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return baslangic

if __name__ == '__main__':
    import webbrowser
    port = bos_port_bul(5050)
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print("  Sonsuz Okumalar - Kitap Düzenleyici & Format Yöneticisi")
    print(f"  Tarayıcınızda açılıyor: {url}")
    print("=" * 60)
    
    try:
        with open(os.path.join(KOK_DIZIN, '.duzenleyici_port.txt'), 'w', encoding='utf8') as pf:
            pf.write(str(port))
    except Exception:
        pass

    def _tarayici_ac():
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=_tarayici_ac, daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
