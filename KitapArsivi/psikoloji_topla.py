# -*- coding: utf-8 -*-
"""
TRAVMA KİTAPLARI OKUNANLAR (21.04.2025).docx ve Okunan Kitaplar Türkçe Psk.docx
dosyalarındaki psikoloji ve travma kitaplarını okur;
- Türkçe olanları Kitapyurdu, Storytel TR, Goodreads/Amazon ve OpenLibrary'den,
- Yabancı dilde (İngilizce/Almanca/İtalyanca) olanları Goodreads/Amazon JSON API,
  Apple Books API ve OpenLibrary'den çeker,
- Kapak görsellerini indirir,
- İngilizce/yabancı özet ve tanıtım yazılarını Türkçeye çevirir,
- Akademik olanları tespit edip 'Akademik' etiketi ekler ve hepsi.json'a birleştirir.
"""
import zipfile, xml.etree.ElementTree as ET
import urllib.request as ur, urllib.parse as up
import json, os, re, sys, time, html, hashlib, difflib, threading, shutil
from concurrent.futures import ThreadPoolExecutor

ARSIV_DIZIN = os.path.dirname(os.path.abspath(__file__))
KOK_DIZIN = os.path.dirname(ARSIV_DIZIN)
sys.path.insert(0, ARSIV_DIZIN)

import toplayici

ONBELLEK = toplayici.ONB
PSK_ONB = os.path.join(ONBELLEK, 'psk')
KAPAK_DIZIN = toplayici.KAPAK
KOK_KAPAK_DIZIN = os.path.join(KOK_DIZIN, 'kapaklar')
os.makedirs(PSK_ONB, exist_ok=True)
os.makedirs(KAPAK_DIZIN, exist_ok=True)
os.makedirs(KOK_KAPAK_DIZIN, exist_ok=True)

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8'
}
kilit = threading.Lock()


def get_json(url, deneme=2):
    for i in range(deneme):
        try:
            with ur.urlopen(ur.Request(url, headers=H), timeout=15) as r:
                return json.loads(r.read().decode('utf8', 'ignore'))
        except Exception:
            if i == deneme - 1:
                return None
            time.sleep(0.8 * (i + 1))


def tr_cevir(metin):
    if not metin or len(metin.strip()) < 5:
        return ''
    metin = metin.strip()[:4500]
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=tr&dt=t&q=" + up.quote(metin)
        with ur.urlopen(ur.Request(url, headers=H), timeout=15) as r:
            d = json.loads(r.read().decode('utf8', 'ignore'))
            return ''.join(seg[0] for seg in d[0] if seg and seg[0]).strip()
    except Exception:
        return ''


def oku_turkce_psk_docx(yol):
    with zipfile.ZipFile(yol) as z:
        xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    satirlar = []
    for p in tree.iter(W + 'p'):
        t = ''.join(x.text for x in p.iter(W + 't') if x.text).strip()
        if t:
            satirlar.append(t)

    # 16 ve 17. satır birleşimi ("16. Keşke Hiç Olmasaydık - Var Olmanın Kötülüğü -" ve "17. David Benatar")
    temiz = []
    for s in satirlar:
        s_no = re.sub(r'^\d+\.\s*', '', s).strip()
        if temiz and temiz[-1].endswith('-'):
            temiz[-1] = temiz[-1] + ' ' + s_no
        else:
            temiz.append(s_no)

    kitaplar = []
    for s in temiz:
        parcalar = [p.strip() for p in s.split(' - ') if p.strip()]
        if len(parcalar) >= 2:
            yazar = parcalar[-1]
            baslik = ' - '.join(parcalar[:-1])
        else:
            baslik, yazar = s, ''
        # Bilinen yazım düzeltmeleri
        baslik = baslik.replace('Ruhun Yanlızlığı', 'Ruhun Yalnızlığı')
        yazar = yazar.replace('Thomaz S. Szasz', 'Thomas Szasz')
        kitaplar.append({'baslik': baslik, 'yazar': yazar, 'dil': 'tr'})
    return kitaplar


def oku_travma_docx(yol):
    with zipfile.ZipFile(yol) as z:
        xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    kitaplar = []
    gorulen = set()
    for tbl in tree.iter(W + 'tbl'):
        for r in tbl.iter(W + 'tr'):
            cells = []
            for tc in r.iter(W + 'tc'):
                txt = ' '.join(''.join(t.text for t in p.iter(W + 't') if t.text).strip() for p in tc.iter(W + 'p')).strip()
                cells.append(txt)
            if len(cells) >= 2 and cells[1]:
                baslik = cells[1].strip()
                yazar = (cells[2] if len(cells) > 2 else '').strip()
                anahtar = toplayici.norm(baslik)[:35] + '|' + toplayici.norm(yazar)[:15]
                if anahtar in gorulen:
                    continue
                gorulen.add(anahtar)
                kitaplar.append({'baslik': baslik, 'yazar': yazar, 'dil': 'en'})
    return kitaplar


AKADEMIK_YAYINEVLERI = [
    'routledge', 'guilford', 'springer', 'oxford university', 'cambridge university',
    'norton', 'american psychological', 'apa ', 'wiley', 'academic press', 'karnac',
    'palgrave', 'harvard university', 'johns hopkins', 'mit press', 'jessica kingsley',
    'hogrefe', 'klett-cotta', 'bağlam', 'baglam', 'metis', 'psikoterapi enstitüsü',
    'litera', 'nobel akademik', 'elsevier', 'sage ', 'taylor & francis', 'baylor',
    'princeton university', 'yale university', 'columbia university', 'jason aronson',
    'analytic press', 'international universities press', 'basic books', 'free press'
]

POPULER_ANAHTARLAR = [
    'memoir', 'personal stories', 'my story', 'my journey', 'my trauma', 'workbook',
    'self-help', 'self help', 'step-by-step', 'for dummies', 'practical guide for',
    'novel', 'a novel', 'stories of healing', 'surviving my', 'confessions of'
]

AKADEMIK_ANAHTARLAR = [
    'psychoanalysis', 'psychoanalytic', 'psychotherapy', 'clinical', 'disorder',
    'psychiatric', 'psychiatry', 'dissociation', 'dissociative', 'neurobiology',
    'neurobiological', 'psychoneuroimmunological', 'developmental trauma',
    'intervention', 'treatment of', 'syndrome', 'theory', 'model of', 'study of',
    'phenomenology', 'empirical', 'dsm', 'emdr', 'trimb', 'somatic', 'attachment',
    'borderline', 'anhedonia', 'depersonalization', 'psikanaliz', 'nöropsikanaliz',
    'psikiyatri', 'klinik', 'psikoterapi', 'fenomenoloji', 'patoloji', 'neuroscience',
    'brain', 'epigenetics', 'transgenerational', 'intergenerational', 'perspectives on',
    'handbook', 'pathology', 'therapeutic', 'relational', 'jungian', 'freud', 'lacan',
    'traumatology', 'posttraumatic', 'ptsd', 'c-ptsd', 'complex trauma'
]


def akademik_mi(baslik, yazar, yayinevi, ozet_en, ozet_tr):
    m_baslik = toplayici.norm(baslik)
    m_yayin = (yayinevi or '').lower()
    m_tum = toplayici.norm(f"{baslik} {ozet_en} {ozet_tr}")

    # Eğer açıkça kişisel anı / memoir ise ve akademik yayınevi değilse
    yayin_akademik = any(y in m_yayin for y in AKADEMIK_YAYINEVLERI)
    if yayin_akademik:
        return True

    populer_baslik = any(p in baslik.lower() for p in ['memoir', 'personal stories', 'my trauma', 'letters from a trauma survivor'])
    if populer_baslik:
        return False

    # Başlıkta güçlü akademik terim varsa
    if any(toplayici.norm(k) in m_baslik for k in AKADEMIK_ANAHTARLAR):
        return True

    # Özette en az 2 farklı akademik anahtar kelime geçiyorsa
    sayac = sum(1 for k in AKADEMIK_ANAHTARLAR if toplayici.norm(k) in m_tum)
    return sayac >= 2


gr_semafor = threading.Semaphore(3)
apple_kilit = threading.Lock()


def yarim_mi(metin):
    if not metin:
        return True
    m = metin.strip()
    if len(m) < 230:
        return True
    if m.endswith('…') or m.endswith('...'):
        return True
    if 'A specialized psychology and trauma book.' in m:
        return True
    return False


def goodreads_tam_detay(book_id):
    """Goodreads book/show/{book_id} sayfasındaki __NEXT_DATA__ apolloState içinden
    kesintisiz tam açıklamayı, yayınevini, yayın yılını ve ISBN bilgisini çeker."""
    if not book_id:
        return {}
    url = f"https://www.goodreads.com/book/show/{book_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8'
    }
    with gr_semafor:
        for deneme in range(3):
            try:
                time.sleep(0.25 * (deneme + 1))
                with ur.urlopen(ur.Request(url, headers=headers), timeout=15) as r:
                    body = r.read().decode('utf8', 'ignore')
                m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', body, re.S)
                if not m:
                    continue
                nd = json.loads(m.group(1))
                apollo = (nd.get('props') or {}).get('pageProps', {}).get('apolloState') or {}
                for k, v in apollo.items():
                    if k.startswith('Book:') and isinstance(v, dict) and (v.get('description') or v.get('details')):
                        desc_raw = v.get('description') or ''
                        desc_clean = html.unescape(re.sub(r'<br\s*/?>|</p>', '\n', desc_raw))
                        desc_clean = re.sub(r'<[^>]+>', '', desc_clean).strip()
                        det = v.get('details') or {}
                        pub = det.get('publisher') or ''
                        isbn = det.get('isbn13') or det.get('isbn') or det.get('asin') or ''
                        pages = det.get('numPages')
                        pub_year = None
                        pt = det.get('publicationTime')
                        if isinstance(pt, (int, float)) and pt > 0:
                            try:
                                import datetime
                                pub_year = datetime.datetime.fromtimestamp(pt / 1000.0, tz=datetime.timezone.utc).year
                            except Exception:
                                pass
                        return {
                            'ozet': desc_clean,
                            'yayinevi': pub,
                            'basili_isbn': isbn,
                            'sayfa': int(pages) if pages else None,
                            'yayin_yili': pub_year
                        }
            except Exception:
                time.sleep(0.6 * (deneme + 1))
    return {}


def yabanci_kitap_tara(isbn_id, baslik, yazar):
    onb_yol = os.path.join(PSK_ONB, f"{isbn_id}.json")
    eski = {}
    if os.path.exists(onb_yol):
        try:
            with open(onb_yol, encoding='utf8') as f:
                eski = json.load(f)
            if not yarim_mi(eski.get('ozet_orijinal')) and not yarim_mi(eski.get('ozet_tr')) and eski.get('kapak_url'):
                return eski
        except Exception:
            eski = {}

    # Parantez içindeki Türkçe çeviriyi arama sorgusundan çıkar
    temiz_baslik = re.sub(r'\s*\([^)]*\)', '', baslik).strip()
    temiz_baslik = re.sub(r'^TR\s+', '', temiz_baslik).strip()
    ana_baslik = temiz_baslik.split(':')[0].split(' - ')[0].strip()
    kisa_baslik = ' '.join(ana_baslik.split()[:6])
    dort_kelime = ' '.join(ana_baslik.split()[:4])
    temiz_yazar = re.sub(r'^Dr\.\s*', '', yazar).split('&')[0].split(',')[0].strip()
    yazar_soyad = temiz_yazar.split()[-1] if temiz_yazar else ''

    sonuc = {
        'baslik_tam': baslik,
        'yazar': eski.get('yazar') or yazar,
        'sayfa': eski.get('sayfa'),
        'yayin_yili': eski.get('yayin_yili'),
        'yayinevi': eski.get('yayinevi') or '',
        'basili_isbn': eski.get('basili_isbn') or '',
        'puan': eski.get('puan'),
        'puan_sayisi': eski.get('puan_sayisi') or 0,
        'kapak_url': eski.get('kapak_url') or '',
        'ozet_orijinal': '' if yarim_mi(eski.get('ozet_orijinal')) else eski.get('ozet_orijinal'),
        'ozet_tr': '',
        'baslik_tr': eski.get('baslik_tr') or ''
    }

    # 1. Goodreads AutoComplete + Goodreads Tam Sayfa (__NEXT_DATA__ apolloState)
    gr_book_id = None
    for q_str in dict.fromkeys([f"{kisa_baslik} {temiz_yazar}".strip(), f"{dort_kelime} {yazar_soyad}".strip(), kisa_baslik, temiz_baslik[:50]]):
        if not q_str:
            continue
        gr_liste = get_json("https://www.goodreads.com/book/auto_complete?format=json&q=" + up.quote(q_str)) or []
        if gr_liste and isinstance(gr_liste, list):
            en_iyi, en_skor = None, -1
            for item in gr_liste:
                it_title = item.get('bookTitleBare') or item.get('title') or ''
                it_author = (item.get('author') or {}).get('name') or ''
                ts = difflib.SequenceMatcher(None, toplayici.norm(kisa_baslik), toplayici.norm(it_title[:len(kisa_baslik)+10])).ratio()
                ys = difflib.SequenceMatcher(None, toplayici.norm(temiz_yazar), toplayici.norm(it_author)).ratio() if temiz_yazar else 0.5
                skor = ts * 1.2 + ys
                if skor > en_skor and (ts >= 0.42 or ys >= 0.72):
                    en_iyi, en_skor = item, skor
            if not en_iyi and gr_liste:
                en_iyi = gr_liste[0]
            if en_iyi:
                gr_book_id = en_iyi.get('bookId')
                if not sonuc['yazar'] and (en_iyi.get('author') or {}).get('name'):
                    sonuc['yazar'] = en_iyi['author']['name']
                if en_iyi.get('numPages') and not sonuc['sayfa']:
                    sonuc['sayfa'] = int(en_iyi['numPages'])
                if en_iyi.get('avgRating') and not sonuc['puan']:
                    try:
                        p = float(en_iyi['avgRating'])
                        if p > 0:
                            sonuc['puan'] = p
                            sonuc['puan_sayisi'] = int(en_iyi.get('ratingsCount') or 0)
                    except Exception:
                        pass
                img = en_iyi.get('imageUrl') or ''
                if img and 'nophoto' not in img and not sonuc['kapak_url']:
                    sonuc['kapak_url'] = re.sub(r'\._S[XY]\d+_\.', '.', img)
                desc_obj = en_iyi.get('description') or {}
                desc_html = desc_obj.get('html') or ''
                if desc_html and not desc_obj.get('truncated') and not sonuc['ozet_orijinal']:
                    sonuc['ozet_orijinal'] = html.unescape(re.sub(r'<[^>]+>', ' ', desc_html)).strip()
                break

    # Goodreads tam sayfa detayını çek (kesintisiz tam açıklama + yayınevi + yıl + ISBN)
    if gr_book_id and (yarim_mi(sonuc['ozet_orijinal']) or not sonuc['yayinevi'] or not sonuc['yayin_yili']):
        tam = goodreads_tam_detay(gr_book_id)
        if tam.get('ozet') and len(tam['ozet']) > len(sonuc['ozet_orijinal'] or ''):
            sonuc['ozet_orijinal'] = tam['ozet']
        if tam.get('yayinevi') and not sonuc['yayinevi']:
            sonuc['yayinevi'] = tam['yayinevi']
        if tam.get('basili_isbn') and not sonuc['basili_isbn']:
            sonuc['basili_isbn'] = tam['basili_isbn']
        if tam.get('sayfa') and not sonuc['sayfa']:
            sonuc['sayfa'] = tam['sayfa']
        if tam.get('yayin_yili') and not sonuc['yayin_yili']:
            sonuc['yayin_yili'] = tam['yayin_yili']

    # 2. Apple Books (iTunes) API - Eğer hala özet kısa/yoksa veya kapak yoksa (rate-limit korumalı)
    if yarim_mi(sonuc['ozet_orijinal']) or not sonuc['kapak_url']:
        for q_str in dict.fromkeys([f"{dort_kelime} {yazar_soyad}".strip(), f"{kisa_baslik} {temiz_yazar}".strip(), kisa_baslik]):
            if not q_str:
                continue
            with apple_kilit:
                time.sleep(0.32)
                it_data = get_json(f"https://itunes.apple.com/search?term={up.quote(q_str)}&entity=ebook&limit=5") or {}
            it_results = it_data.get('results') or []
            for item in it_results:
                it_title = item.get('trackName') or ''
                it_author = item.get('artistName') or ''
                ts = difflib.SequenceMatcher(None, toplayici.norm(dort_kelime), toplayici.norm(it_title[:len(dort_kelime)+12])).ratio()
                ys = difflib.SequenceMatcher(None, toplayici.norm(temiz_yazar), toplayici.norm(it_author)).ratio() if temiz_yazar else 0.6
                if ts >= 0.45 or ys >= 0.65:
                    desc = item.get('description') or ''
                    desc_clean = html.unescape(re.sub(r'<br\s*/?>|</p>', '\n', desc))
                    desc_clean = re.sub(r'<[^>]+>', '', desc_clean).strip()
                    if len(desc_clean) > len(sonuc['ozet_orijinal'] or ''):
                        sonuc['ozet_orijinal'] = desc_clean
                    art = item.get('artworkUrl100') or ''
                    if art and not sonuc['kapak_url']:
                        sonuc['kapak_url'] = art.replace('100x100bb', '600x600bb')
                    rel = (item.get('releaseDate') or '')[:4]
                    if rel.isdigit() and not sonuc['yayin_yili']:
                        sonuc['yayin_yili'] = int(rel)
                    m_isbn = re.search(r'(97[89]\d{10})', art)
                    if m_isbn and not sonuc['basili_isbn']:
                        sonuc['basili_isbn'] = m_isbn.group(1)
                    break
            if not yarim_mi(sonuc['ozet_orijinal']):
                break

    # 3. Storytel Uluslararası API (EN / DE) - Eğer hala özet kısaysa
    if yarim_mi(sonuc['ozet_orijinal']):
        for loc in ('en', 'de', 'tr'):
            try:
                st_raw = toplayici.indir(f"https://www.storytel.com/api/search.action?request_locale={loc}&q=" + up.quote(f"{dort_kelime} {yazar_soyad}".strip()))
                if st_raw:
                    for sb in (json.loads(st_raw).get('books') or [])[:3]:
                        b_obj = sb.get('book') or {}
                        ab_obj = sb.get('abook') or {}
                        eb_obj = sb.get('ebk') or {}
                        b_ad = b_obj.get('name') or ''
                        if difflib.SequenceMatcher(None, toplayici.norm(dort_kelime), toplayici.norm(b_ad[:len(dort_kelime)+10])).ratio() >= 0.5:
                            st_desc = (ab_obj.get('description') or eb_obj.get('description') or '').strip()
                            if len(st_desc) > len(sonuc['ozet_orijinal'] or ''):
                                sonuc['ozet_orijinal'] = st_desc
                            if not sonuc['kapak_url'] and b_obj.get('largeCover'):
                                sonuc['kapak_url'] = 'https://www.storytel.com' + b_obj['largeCover']
                            break
                if not yarim_mi(sonuc['ozet_orijinal']):
                    break
            except Exception:
                pass

    # 4. OpenLibrary Search + Work Description API
    ol_q = up.quote(f"{kisa_baslik} {temiz_yazar}".strip())
    if yarim_mi(sonuc['ozet_orijinal']) or not sonuc['yayinevi'] or not sonuc['yayin_yili']:
        ol_data = get_json(f"https://openlibrary.org/search.json?q={ol_q}&limit=3&fields=key,title,author_name,first_publish_year,number_of_pages_median,publisher,isbn,cover_i") or {}
        ol_docs = ol_data.get('docs') or []
        if ol_docs:
            d0 = ol_docs[0]
            if not sonuc['yayin_yili'] and d0.get('first_publish_year'):
                sonuc['yayin_yili'] = int(d0['first_publish_year'])
            if not sonuc['sayfa'] and d0.get('number_of_pages_median'):
                sonuc['sayfa'] = int(d0['number_of_pages_median'])
            pubs = d0.get('publisher') or []
            if pubs and not sonuc['yayinevi']:
                sec_pub = pubs[0]
                for p in pubs:
                    if any(ak in p.lower() for ak in AKADEMIK_YAYINEVLERI):
                        sec_pub = p
                        break
                sonuc['yayinevi'] = sec_pub
            isbns = d0.get('isbn') or []
            if isbns and not sonuc['basili_isbn']:
                isbn13 = [x for x in isbns if len(x) == 13 and x.startswith('97')]
                sonuc['basili_isbn'] = isbn13[0] if isbn13 else isbns[0]
            if not sonuc['kapak_url'] and d0.get('cover_i'):
                sonuc['kapak_url'] = f"https://covers.openlibrary.org/b/id/{d0['cover_i']}-L.jpg"
            if yarim_mi(sonuc['ozet_orijinal']) and d0.get('key'):
                w_data = get_json(f"https://openlibrary.org{d0['key']}.json") or {}
                w_desc = w_data.get('description')
                if isinstance(w_desc, dict):
                    w_desc = w_desc.get('value') or ''
                if isinstance(w_desc, str) and len(w_desc.strip()) > len(sonuc['ozet_orijinal'] or ''):
                    sonuc['ozet_orijinal'] = w_desc.strip()

    # 5. Crossref Abstract kontrolü
    if yarim_mi(sonuc['ozet_orijinal']) or not sonuc['yayinevi']:
        cr = get_json(f"https://api.crossref.org/works?query.bibliographic={ol_q}&rows=2") or {}
        items = (cr.get('message') or {}).get('items') or []
        for it in items:
            if not sonuc['yayinevi'] and it.get('publisher'):
                sonuc['yayinevi'] = it['publisher']
            if yarim_mi(sonuc['ozet_orijinal']) and it.get('abstract'):
                ab_txt = html.unescape(re.sub(r'<[^>]+>', ' ', it['abstract'])).strip()
                if len(ab_txt) > len(sonuc['ozet_orijinal'] or ''):
                    sonuc['ozet_orijinal'] = ab_txt

    # 6. Özeti ve Başlığı Türkçeye çevir
    if sonuc['ozet_orijinal']:
        sonuc['ozet_tr'] = tr_cevir(sonuc['ozet_orijinal'])
    else:
        sonuc['ozet_orijinal'] = f"{temiz_baslik} by {sonuc['yazar'] or 'unknown author'}."
        sonuc['ozet_tr'] = tr_cevir(f"{temiz_baslik} ({sonuc['yazar']}). Psikoloji, psikanaliz ve travma alanında incelenen eser.")

    if '(' not in baslik and not sonuc['baslik_tr']:
        cev_b = tr_cevir(temiz_baslik)
        if cev_b and toplayici.norm(cev_b) != toplayici.norm(temiz_baslik):
            sonuc['baslik_tr'] = cev_b

    with open(onb_yol, 'w', encoding='utf8') as f:
        json.dump(sonuc, f, ensure_ascii=False)
    return sonuc


def turkce_kitap_tara(isbn_id, baslik, yazar):
    """Türkçe psikoloji kitabını Kitapyurdu, Storytel ve Goodreads tam sayfa üzerinden tarar."""
    onb_yol = os.path.join(PSK_ONB, f"{isbn_id}.json")
    eski = {}
    if os.path.exists(onb_yol):
        try:
            with open(onb_yol, 'r', encoding='utf8') as f:
                eski = json.load(f)
            if not yarim_mi(eski.get('ozet')) and eski.get('kapak_url'):
                return eski
        except Exception:
            eski = {}

    ana_baslik = baslik.split(' - ')[0].split('(')[0].strip()
    ky = toplayici.kitapyurdu(isbn_id, baslik, yazar) or {}
    if not ky.get('tanitim') and ana_baslik != baslik:
        # Alt başlık yüzünden eşleşmediyse önbelleği silip ana başlıkla tekrar ara
        ky_onb = os.path.join(ONBELLEK, f"ky_{isbn_id}.json")
        if os.path.exists(ky_onb):
            try:
                os.remove(ky_onb)
            except Exception:
                pass
        ky = toplayici.kitapyurdu(isbn_id, ana_baslik, yazar) or {}

    # Storytel başlık/yazar araması
    st_kitap, st_ab = {}, {}
    for sorgu in dict.fromkeys([f"{ana_baslik} {yazar}".strip(), f"{baslik} {yazar}".strip(), ana_baslik]):
        try:
            s_arama = toplayici.indir('https://www.storytel.com/api/search.action?request_locale=tr&q=' + up.quote(sorgu))
            if s_arama:
                for sb in (json.loads(s_arama).get('books') or []):
                    b_obj = sb.get('book') or {}
                    b_ad = b_obj.get('name') or ''
                    if difflib.SequenceMatcher(None, toplayici.norm(ana_baslik), toplayici.norm(b_ad[:len(ana_baslik)+8])).ratio() >= 0.6:
                        st_kitap = b_obj
                        st_ab = sb.get('abook') or (sb.get('ebk') or {})
                        break
            if st_ab.get('description'):
                break
        except Exception:
            pass

    kapak_url = ky.get('kapak') or (('https://www.storytel.com' + st_kitap['largeCover']) if st_kitap.get('largeCover') else '') or eski.get('kapak_url') or ''
    ozet = (ky.get('tanitim') or '').strip() or (eski.get('ozet') if not yarim_mi(eski.get('ozet')) else '') or ''
    tanitim = (st_ab.get('description') or '').strip()
    yayinevi = ky.get('yayinevi') or ((st_ab.get('publisher') or {}).get('name') or '') or eski.get('yayinevi') or ''
    sayfa = ky.get('sayfa') or eski.get('sayfa') or 0
    ym = re.search(r'(\d{4})', (ky.get('yayin_tarihi') or st_ab.get('releaseDateFormat') or ''))
    yayin_yili = int(ym.group(1)) if ym else eski.get('yayin_yili')
    puan = st_kitap.get('grade') or eski.get('puan') or None
    puan_sayisi = st_kitap.get('nrGrade') or eski.get('puan_sayisi') or 0
    basili_isbn = ky.get('basili_isbn') or eski.get('basili_isbn') or ''

    # Eksik veya yarım özet varsa Goodreads Tam Sayfa (__NEXT_DATA__) ile tamamla
    if not kapak_url or yarim_mi(ozet) or not sayfa or not yayin_yili:
        for q_tr in dict.fromkeys([f"{ana_baslik} {yazar}".strip(), f"{baslik} {yazar}".strip(), ana_baslik]):
            gr_liste = get_json("https://www.goodreads.com/book/auto_complete?format=json&q=" + up.quote(q_tr)) or []
            if gr_liste and isinstance(gr_liste, list):
                it = gr_liste[0]
                if not kapak_url and it.get('imageUrl') and 'nophoto' not in it['imageUrl']:
                    kapak_url = re.sub(r'\._S[XY]\d+_\.', '.', it['imageUrl'])
                if not sayfa and it.get('numPages'):
                    sayfa = int(it['numPages'])
                if not puan and it.get('avgRating'):
                    try:
                        puan = float(it['avgRating'])
                        puan_sayisi = int(it.get('ratingsCount') or 0)
                    except Exception:
                        pass
                if it.get('bookId') and (yarim_mi(ozet) or not yayinevi or not yayin_yili):
                    tam = goodreads_tam_detay(it['bookId'])
                    if tam.get('ozet') and len(tam['ozet']) > len(ozet):
                        ozet = tam['ozet']
                    if tam.get('yayinevi') and not yayinevi:
                        yayinevi = tam['yayinevi']
                    if tam.get('basili_isbn') and not basili_isbn:
                        basili_isbn = tam['basili_isbn']
                    if tam.get('sayfa') and not sayfa:
                        sayfa = tam['sayfa']
                    if tam.get('yayin_yili') and not yayin_yili:
                        yayin_yili = tam['yayin_yili']
                break

    if yarim_mi(ozet) and not yarim_mi(tanitim):
        ozet, tanitim = tanitim, ''

    if not ozet:
        ozet = f"{baslik} ({yazar}). Psikoloji, psikiyatri ve insan ruhunun derinliklerini inceleyen kurgu dışı eser."

    sonuc = {
        'id': isbn_id,
        'baslik': baslik,
        'yazar': yazar or st_kitap.get('authorsAsString') or '',
        'kapak_url': kapak_url,
        'ozet': ozet,
        'tanitim': tanitim if tanitim and tanitim != ozet else '',
        'yayinevi': yayinevi,
        'sayfa': sayfa,
        'yayin_yili': yayin_yili,
        'puan': puan,
        'puan_sayisi': puan_sayisi,
        'basili_isbn': basili_isbn,
        'ky_url': ky.get('url') or '',
    }
    with open(onb_yol, 'w', encoding='utf8') as f:
        json.dump(sonuc, f, ensure_ascii=False)
    return sonuc


def kapak_kaydet(isbn_id, url):
    if not url:
        return None
    dosya_adi = f"{isbn_id}_b.jpg"
    hedef1 = os.path.join(KAPAK_DIZIN, dosya_adi)
    hedef2 = os.path.join(KOK_KAPAK_DIZIN, dosya_adi)
    if not os.path.exists(hedef1) or os.path.getsize(hedef1) < 800:
        b = toplayici.indir(url, ikili=True)
        if b and len(b) >= 800:
            with open(hedef1, 'wb') as f:
                f.write(b)
    if os.path.exists(hedef1) and os.path.getsize(hedef1) >= 800:
        try:
            shutil.copy2(hedef1, hedef2)
        except Exception:
            pass
        return dosya_adi
    return None


def calistir():
    tr_yol = os.path.join(KOK_DIZIN, 'Okunan Kitaplar Türkçe Psk.docx')
    en_yol = os.path.join(KOK_DIZIN, 'TRAVMA KİTAPLARI OKUNANLAR (21.04.2025).docx')
    tr_liste = [(i, k['baslik'], k['yazar']) for i, k in enumerate(oku_turkce_psk_docx(tr_yol), 1)]
    en_liste = [(i, k['baslik'], k['yazar']) for i, k in enumerate(oku_travma_docx(en_yol), 1)]
    print(f"Türkçe Psikoloji: {len(tr_liste)} kitap | Yabancı Travma/Psikoloji: {len(en_liste)} kitap", flush=True)

    yeni_kayitlar = {}

    # 1. Türkçe Psikoloji Kitaplarını Tara
    def is_tr(item):
        sira, baslik, yazar = item
        isbn_id = f"PSK_TR_{sira:03d}"
        d = turkce_kitap_tara(isbn_id, baslik, yazar)
        kapak_dosya = kapak_kaydet(isbn_id, d.get('kapak_url'))
        ak = akademik_mi(baslik, d.get('yazar', ''), d.get('yayinevi', ''), d.get('tanitim', ''), d.get('ozet', ''))
        return isbn_id, {
            'isbn': isbn_id,
            'baslik_csv': baslik,
            'yazar_belirtilen': d.get('yazar') or yazar,
            'sure_sn': 0,
            'ilerleme': 100,
            'format': 'Psikoloji Kitapları',
            'baslangic': '',
            'son_dinleme': '',
            'psk_kitap': True,
            'akademik': ak,
            'dil': 'tr',
            'orijinal_baslik': '',
            'storytel': {
                'book': {
                    'name': baslik,
                    'authorsAsString': d.get('yazar') or yazar,
                    'category': {'title': 'KURGU DIŞI'},
                    'grade': d.get('puan'),
                    'nrGrade': d.get('puan_sayisi') or 0,
                },
                'abook': {
                    'description': d.get('ozet') or '',
                    'releaseDateFormat': str(d.get('yayin_yili')) if d.get('yayin_yili') else None,
                    'publisher': {'name': ''},
                }
            },
            'kitapyurdu': {
                'url': d.get('ky_url') or '',
                'sayfa': d.get('sayfa') or None,
                'yayin_tarihi': str(d.get('yayin_yili')) if d.get('yayin_yili') else None,
                'yayinevi': d.get('yayinevi') or '',
                'basili_isbn': d.get('basili_isbn') or '',
                'dil': 'Türkçe',
                'kapak': d.get('kapak_url') or '',
                'tanitim': d.get('tanitim') or '',
            },
            'kapak_sesli': None,
            'kapak_basili': kapak_dosya,
        }

    print("Türkçe psikoloji kitapları taranıyor...", flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for idx, (k_id, veri) in enumerate(ex.map(is_tr, tr_liste), 1):
            yeni_kayitlar[k_id] = veri
            if idx % 10 == 0 or idx == len(tr_liste):
                print(f"  [TR] {idx}/{len(tr_liste)} tamamlandı", flush=True)

    # 2. Yabancı Psikoloji / Travma Kitaplarını Tara
    def is_en(item):
        sira, baslik, yazar = item
        isbn_id = f"PSK_EN_{sira:03d}"
        d = yabanci_kitap_tara(isbn_id, baslik, yazar)
        kapak_dosya = kapak_kaydet(isbn_id, d.get('kapak_url'))
        ak = akademik_mi(baslik, d.get('yazar', ''), d.get('yayinevi', ''), d.get('ozet_orijinal', ''), d.get('ozet_tr', ''))

        ozet_tr_tam = (d.get('ozet_tr') or '').strip()
        baslik_tr = (d.get('baslik_tr') or '').strip()

        return isbn_id, {
            'isbn': isbn_id,
            'baslik_csv': baslik,
            'yazar_belirtilen': d.get('yazar') or yazar or 'Belirtilmemiş',
            'sure_sn': 0,
            'ilerleme': 100,
            'format': 'Psikoloji Kitapları (Yabancı / Çeviri)',
            'baslangic': '',
            'son_dinleme': '',
            'psk_kitap': True,
            'akademik': ak,
            'dil': 'en',
            'orijinal_baslik': baslik_tr,
            'storytel': {
                'book': {
                    'name': baslik,
                    'authorsAsString': d.get('yazar') or yazar or 'Belirtilmemiş',
                    'category': {'title': 'KURGU DIŞI'},
                    'grade': d.get('puan'),
                    'nrGrade': d.get('puan_sayisi') or 0,
                },
                'abook': {
                    'description': ozet_tr_tam,  # Türkçe çeviri özet
                    'releaseDateFormat': str(d.get('yayin_yili')) if d.get('yayin_yili') else None,
                    'publisher': {'name': ''},
                }
            },
            'kitapyurdu': {
                'url': '',
                'sayfa': d.get('sayfa') or None,
                'yayin_tarihi': str(d.get('yayin_yili')) if d.get('yayin_yili') else None,
                'yayinevi': d.get('yayinevi') or '',
                'basili_isbn': d.get('basili_isbn') or '',
                'dil': 'İngilizce / Yabancı',
                'kapak': d.get('kapak_url') or '',
                'tanitim': d.get('ozet_orijinal') or '',  # Orijinal İngilizce tanıtım
            },
            'kapak_sesli': None,
            'kapak_basili': kapak_dosya,
        }

    print("Yabancı travma ve psikoloji kitapları taranıyor (Amazon/Goodreads/Apple Books + Türkçe Çeviri)...", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for idx, (k_id, veri) in enumerate(ex.map(is_en, en_liste), 1):
            yeni_kayitlar[k_id] = veri
            if idx % 25 == 0 or idx == len(en_liste):
                print(f"  [EN] {idx}/{len(en_liste)} tamamlandı", flush=True)

    # 3. Mevcut hepsi.json (liste formatında) ile birleştir
    hepsi_yol = os.path.join(ONBELLEK, 'hepsi.json')
    mevcut_havuz = {}
    if os.path.exists(hepsi_yol):
        with open(hepsi_yol, 'r', encoding='utf8') as f:
            okunan = json.load(f)
            if isinstance(okunan, list):
                for k in okunan:
                    mevcut_havuz[k['isbn']] = k
            elif isinstance(okunan, dict):
                mevcut_havuz = okunan

    onceki_sayi = len(mevcut_havuz)
    mevcut_havuz.update(yeni_kayitlar)
    birlesik_liste = list(mevcut_havuz.values())

    with open(hepsi_yol, 'w', encoding='utf8') as f:
        json.dump(birlesik_liste, f, ensure_ascii=False)

    ak_say = sum(1 for v in yeni_kayitlar.values() if v.get('akademik'))
    kapak_say = sum(1 for v in yeni_kayitlar.values() if v.get('kapak_basili'))
    ozet_say = sum(1 for v in yeni_kayitlar.values() if ((v.get('storytel') or {}).get('abook') or {}).get('description'))
    print(f"\nTamamlandı! Önceki kayıt: {onceki_sayi} -> Yeni toplam: {len(birlesik_liste)}", flush=True)
    print(f"Eklenen psikoloji kitabı: {len(yeni_kayitlar)} | Akademik etiketli: {ak_say} | Kapaklı: {kapak_say} | Türkçe özetli: {ozet_say}", flush=True)


if __name__ == '__main__':
    calistir()
