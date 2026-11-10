# -*- coding: utf-8 -*-
"""Adım 1: CSV'yi oku, internetten (Storytel + Kitapyurdu) kitap bilgilerini ve kapakları topla.
Sonuçlar veri/onbellek/ altında saklanır; tekrar çalıştırılınca kaldığı yerden devam eder."""
import csv, json, os, re, sys, time, html, unicodedata, difflib, threading
import urllib.request as ur, urllib.parse as up
from concurrent.futures import ThreadPoolExecutor

KOK = os.path.dirname(os.path.abspath(__file__))
CSV_YOL = os.path.join(KOK, '..', '11kasım2026.csv')
ONB = os.path.join(KOK, 'veri', 'onbellek')
KAPAK = os.path.join(KOK, 'uygulama', 'kapaklar')
for d in (ONB, KAPAK): os.makedirs(d, exist_ok=True)
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept-Language': 'tr-TR,tr;q=0.9'}
kilit = threading.Lock()


def indir(url, ikili=False, deneme=3):
    for i in range(deneme):
        try:
            with ur.urlopen(ur.Request(url, headers=H), timeout=25) as r:
                b = r.read()
                return b if ikili else b.decode('utf8', 'ignore')
        except Exception as e:
            if i == deneme - 1: return None
            time.sleep(1.5 * (i + 1))


def norm(s):
    s = (s or '').replace('İ', 'i').replace('I', 'ı').lower()
    s = s.replace('ı', 'i')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]+', ' ', s).strip()


def csv_oku():
    kayit = {}
    with open(CSV_YOL, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            isbn = r['Kitap ISBN'].strip()
            h = r['Kitap Süresi'].split(':')
            sn = int(h[0]) * 3600 + int(h[1]) * 60 + int(h[2]) if len(h) == 3 else 0
            kayit[isbn] = dict(
                isbn=isbn, baslik_csv=r['Kitap adı'].strip(), sure_sn=sn,
                ilerleme=round(float((r['Ayraç konumu'] or '0').strip().strip('%').replace(',', '.') or 0)),
                format=r['Format'], baslangic=r['Başlangıç tarihi'][:10], son_dinleme=r['Son ayraç ekleme tarihi'][:10])
    return list(kayit.values())


def onb_oku(ad):
    y = os.path.join(ONB, ad)
    if os.path.exists(y):
        with open(y, encoding='utf8') as f: return json.load(f)


def onb_yaz(ad, v):
    with open(os.path.join(ONB, ad), 'w', encoding='utf8') as f: json.dump(v, f, ensure_ascii=False)


def storytel(isbn):
    c = onb_oku(f'st_{isbn}.json')
    if c is not None: return c
    t = indir('https://www.storytel.com/api/search.action?request_locale=tr&q=' + isbn)
    sonuc = {}
    if t:
        try:
            for b in json.loads(t).get('books', []):
                if b.get('abook') and b['abook'].get('isbn') == isbn:
                    sonuc = b; break
        except Exception: pass
    if t is not None: onb_yaz(f'st_{isbn}.json', sonuc)
    return sonuc


def kitapyurdu(isbn, baslik, yazar):
    c = onb_oku(f'ky_{isbn}.json')
    if c is not None: return c
    sonuc = {}
    ok = False
    for sorgu in dict.fromkeys([f'{baslik} {yazar}', baslik]):
        s = indir('https://www.kitapyurdu.com/index.php?route=product/search&filter_name=' + up.quote(sorgu))
        time.sleep(0.6)
        if not s: continue
        ok = True
        en_iyi, skor = None, 0
        for blok in s.split('class="ky-product"')[1:]:
            m = re.search(r'class="ky-product-title"[^>]*href="([^"]+)"|href="([^"]+)"[^>]*class="ky-product-title"', blok)
            t = re.search(r'class="ky-product-title"[^>]*>(.*?)</a>', blok, re.S)
            ya = re.findall(r'/yazar/[^"]+"[^>]*>(.*?)</a>', blok, re.S)
            if not (m and t): continue
            link = html.unescape(m.group(1) or m.group(2)).split('?')[0]
            ad = html.unescape(re.sub(r'<[^>]+>|\s+', ' ', t.group(1))).strip()
            ts = difflib.SequenceMatcher(None, norm(ad), norm(baslik)).ratio()
            ys = max([difflib.SequenceMatcher(None, norm(html.unescape(a)), norm(yazar)).ratio() for a in ya] or [0])
            if ts >= 0.8 and (ys >= 0.75 or not yazar):
                sk = ts + ys
                if sk > skor: en_iyi, skor = link, sk
        if en_iyi:
            p = indir(en_iyi)
            if p:
                sonuc = ky_ayrisitir(p, en_iyi); break
    if ok: onb_yaz(f'ky_{isbn}.json', sonuc)
    return sonuc


def baslik_harf(w):
    """Türkçe kurallarıyla 'YAYINLARI' -> 'Yayınları'."""
    k = w.replace('I', 'ı').replace('İ', 'i').lower()
    return ({'i': 'İ', 'ı': 'I'}.get(k[:1], k[:1].upper())) + k[1:]


def ky_ayrisitir(p, url):
    def nitelik(et):
        m = re.search(r'ky-pd-attributes__label">\s*' + et + r':?\s*</span>\s*<span class="ky-pd-attributes__value">(.*?)</span>', p, re.S)
        return html.unescape(re.sub(r'<[^>]+>|\s+', ' ', m.group(1))).strip() if m else None
    r = dict(url=url, sayfa=None, yayin_tarihi=None, yayinevi=None, basili_isbn=nitelik('ISBN'), dil=nitelik('Dil'), kapak=None, tanitim=None)
    sf = nitelik('Sayfa Sayısı')
    if sf and sf.isdigit(): r['sayfa'] = int(sf)
    r['yayin_tarihi'] = nitelik('Yayın Tarihi')
    # Yayınevi ve tam tanıtım metni: sayfadaki schema.org JSON-LD "Book" kaydından (og:description kısaltılmış geliyor)
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', p, re.S):
        try: d = json.loads(m.group(1))
        except Exception: continue
        for n in (d.get('@graph', [d]) if isinstance(d, dict) else []):
            if 'Book' in str(n.get('@type')):
                if not r['yayinevi'] and isinstance(n.get('publisher'), dict): r['yayinevi'] = (n['publisher'].get('name') or '').strip() or None
                if not r['tanitim'] and n.get('description'): r['tanitim'] = html.unescape(n['description']).strip()
    if not r['yayinevi']:
        ye = re.search(r'class="ky-pd-heading__author\s*"\s+href="[^"]*/yayinevi/[^"]*">\s*([^<]+?)\s*</a>', p)
        if ye: r['yayinevi'] = html.unescape(ye.group(1)).strip()
    if r['yayinevi'] and r['yayinevi'].isupper():  # BÜYÜK HARFLİ yayınevi adlarını düzgün yaz
        r['yayinevi'] = ' '.join(baslik_harf(w) for w in r['yayinevi'].split())
    k = re.search(r'property="og:image" content="([^"]+)"', p)
    if k: r['kapak'] = html.unescape(k.group(1)).replace('/miw:200/mih:200', '')
    return r


def kapak_indir(isbn, ek, url):
    yol = os.path.join(KAPAK, f'{isbn}{ek}.jpg')
    if os.path.exists(yol) and os.path.getsize(yol) > 1000: return os.path.basename(yol)
    if not url: return None
    b = indir(url, ikili=True)
    if b and len(b) > 1000:
        with open(yol, 'wb') as f: f.write(b)
        return os.path.basename(yol)


def isle(k):
    isbn = k['isbn']
    st = storytel(isbn)
    kitap = st.get('book', {}) if st else {}
    yazar = kitap.get('authorsAsString') or ''
    baslik = kitap.get('name') or k['baslik_csv']
    ky = kitapyurdu(isbn, baslik, yazar)
    kap_s = kapak_indir(isbn, '_s', 'https://www.storytel.com' + kitap['largeCover']) if kitap.get('largeCover') else None
    kap_b = kapak_indir(isbn, '_b', ky.get('kapak')) if ky else None
    k = dict(k, storytel=st, kitapyurdu=ky, kapak_sesli=kap_s, kapak_basili=kap_b)
    with kilit:
        print(f"{'OK ' if st else 'YOK'} {'KY' if ky else '--'} {baslik[:40]}", flush=True)
    return k


if __name__ == '__main__':
    liste = csv_oku()
    print(len(liste), 'kitap')
    with ThreadPoolExecutor(4) as ex: sonuc = list(ex.map(isle, liste))
    onb_yaz('hepsi.json', sonuc)
    print('Bitti. Storytel:', sum(1 for s in sonuc if s['storytel']), 'Kitapyurdu:', sum(1 for s in sonuc if s['kitapyurdu']))
