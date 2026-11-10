# -*- coding: utf-8 -*-
"""Adım 2: Toplanan veriyi sınıflandır (kategori/alt kategori/etiket), SQLite veritabanı (FTS5 tam metin arama)
ve çevrimdışı uygulama için uygulama/veri.js dosyalarını üret."""
import json, os, re, sqlite3
from toplayici import norm, KOK, ONB

ANA = {'ROMAN': 'Roman', 'ÖYKÜ': 'Öykü', 'KURGU DIŞI': 'Kurgu Dışı', 'BİYOGRAFİ': 'Biyografi & Anı', 'KLASİKLER': 'Klasikler',
       'TARİH': 'Tarih', 'POLİSİYE': 'Polisiye & Gizem', 'DİL ÖĞRENİMİ': 'Dil Öğrenimi', 'ÇOCUK': 'Çocuk & Gençlik',
       'GENÇLİK': 'Çocuk & Gençlik', 'KİŞİSEL GELİŞİM': 'Kişisel Gelişim', 'ŞİİR': 'Şiir'}

# etiket: (anahtar kelimeler -- normalleştirilmiş, kelime başı eşleşir)
ETIKET = {
 'Aşk & İlişkiler': ['ask', 'asik', 'sevgili', 'evlilik', 'boşanma', 'bosanma', 'ayrilik', 'sevda', 'tutku', 'kocasi', 'karisi'],
 'Aile': ['aile', 'anne', 'baba', 'kardes', 'evlat', 'dede', 'nine', 'torun', 'ogul'],
 'Kadın': ['kadin', 'kiz ', 'annelik', 'feminist'],
 'Savaş': ['savas', 'cephe', 'asker', 'mahpus', 'cete', 'bomba', 'harp'],
 'Göç & Sürgün': ['goc', 'surgun', 'multeci', 'ayrilik', 'gurbet', 'sinir'],
 'Siyaset & Toplum': ['siyas', 'darbe', 'faşizm', 'fasizm', 'iktidar', 'devrim', 'sosyal', 'sinif', 'isci', 'adalet', 'yoksul', 'ezilen', 'sansur'],
 'Tarihî': ['osmanli', 'cumhuriyet', 'padisah', 'sultan', 'tarihi', 'yuzyil', 'istiklal', 'ataturk', 'bizans'],
 'Fantastik': ['ejderha', 'fantast', 'buyucu', 'buyulu', 'buyu ', 'tilsim', 'cinler', 'periler'],
 'Bilim Kurgu': ['uzay', 'distopya', 'robot', 'yapay zeka', 'bilim kurgu', 'paralel evren', 'gelecekte', 'gezegen'],
 'Gizem & Suç': ['cinayet', 'dedektif', 'gizem', 'katil', 'polis', 'suc ', 'cani', 'soruşturma', 'sorusturma', 'kayip'],
 'Psikolojik': ['psikolo', 'travma', 'depresyon', 'yalnizlik', 'delilik', 'bunalim', 'kaygi', 'terapi', 'bilinc', 'ruh '],
 'Ölüm & Yas': ['olum', 'yas ', 'cenaze', 'mezar', 'intihar', 'olen', 'vefat', 'kaybetme'],
 'Mizah': ['mizah', 'komik', 'gulmece', 'gulunc', 'hiciv', 'espri'],
 'Felsefe & Varoluş': ['felsefe', 'varolus', 'anlam ara', 'hayatin anlami', 'filozof', 'absurd'],
 'Çocukluk & Gençlik': ['cocukluk', 'ergen', 'genclik', 'okul', 'ogrenci', 'cocuk '],
 'Doğa & Hayvanlar': ['kedi', 'doga', 'hayvan', 'kuslar', 'agac'],
 'İstanbul': ['istanbul', 'beyoglu', 'bogaz', 'kadikoy', 'galata'],
 'Anadolu & Köy': ['anadolu', 'koy ', 'koyu', 'kasaba', 'tasra', 'cukurova', 'karadeniz', 'dogu '],
 'Mitoloji & Antik': ['mitoloji', 'tanrica', 'antik', 'tanrilar', 'homeros', 'truva', 'olympos'],
 'Sanat & Müzik': ['muzik', 'ressam', 'sanat', 'sinema', 'tiyatro', 'sarki', 'oyuncu', 'film', 'resim'],
 'Din & Tasavvuf': ['tasavvuf', 'dervis', 'islam', 'tekke', 'mevlana', 'ilahi', 'allah', 'din '],
 'Edebiyat & Yazarlık': ['edebiyat', 'yazar ', 'yazarlik', 'sair', 'kutuphane', 'roman yaz'],
 'Mahalle & Gündelik Hayat': ['mahalle', 'komsu', 'apartman', 'kahve', 'cay ', 'gunluk hayat', 'sokak'],
 'Hapis & Hesaplaşma': ['hapis', 'cezaevi', 'hesaplas', 'intikam', 'zindan'],
 'Yemek': ['yemek', 'mutfak', 'lokanta', 'tarif'],
 'Seyahat': ['yolculuk', 'seyahat', 'gezi', 'yol hikayesi', 'tren', 'sehirler'],
 'İngilizce': ['ingilizce', 'english', 'grammar', 'listen up'],
 'Yapay Zekâ & Teknoloji': ['yapay zeka', 'teknoloji', 'bilgisayar', 'internet'],
 'Biyografi': ['biyografi', 'yasam oykusu', 'hatirat', 'otobiyograf', 'hayat hikayesi'],
}
# Etiketlerin ana kategoriye göre alt kategori olarak önceliği
ALT_ONCELIK = {
 'Roman': [('Fantastik', 'Fantastik'), ('Bilim Kurgu', 'Bilim Kurgu'), ('Gizem & Suç', 'Gizem & Suç'), ('Tarihî', 'Tarihî Roman'), ('Savaş', 'Savaş Romanı'),
           ('Mizah', 'Mizahî Roman'), ('Aşk & İlişkiler', 'Aşk & İlişkiler'), ('Psikolojik', 'Psikolojik Roman'), ('Siyaset & Toplum', 'Toplumsal Roman'),
           ('Aile', 'Aile Romanı'), ('Anadolu & Köy', 'Taşra & Köy Romanı'), ('Göç & Sürgün', 'Göç & Sürgün')],
 'Kurgu Dışı': [('İngilizce', 'Dil'), ('Yapay Zekâ & Teknoloji', 'Bilim & Teknoloji'), ('Psikolojik', 'Psikoloji'), ('Felsefe & Varoluş', 'Felsefe'), ('Tarihî', 'Tarih'),
                ('Siyaset & Toplum', 'Siyaset & Toplum'), ('Yemek', 'Yemek Kültürü'), ('Edebiyat & Yazarlık', 'Edebiyat & Deneme'), ('Sanat & Müzik', 'Sanat')],
 'Biyografi & Anı': [('Edebiyat & Yazarlık', 'Edebiyatçı Yaşamları'), ('Sanat & Müzik', 'Sanat İnsanları'), ('Siyaset & Toplum', 'Siyaset & Devrimciler')],
 'Öykü': [('Mizah', 'Mizahî Öykü'), ('Fantastik', 'Fantastik Öykü'), ('Aşk & İlişkiler', 'Aşk Öyküleri'), ('Aile', 'Aile Öyküleri'), ('Psikolojik', 'Psikolojik Öykü')],
}
ALT_VARSAYILAN = {'Roman': 'Çağdaş Roman', 'Öykü': 'Çağdaş Öykü', 'Kurgu Dışı': 'Genel Kurgu Dışı', 'Biyografi & Anı': 'Yaşam Öyküsü & Anı',
                  'Klasikler': 'Dünya Klasikleri', 'Tarih': 'Genel Tarih', 'Polisiye & Gizem': 'Polisiye', 'Dil Öğrenimi': 'İngilizce',
                  'Çocuk & Gençlik': 'Çocuk & Gençlik', 'Kişisel Gelişim': 'Kişisel Gelişim', 'Şiir': 'Şiir'}


def eslesir(metin, kelime):
    return (' ' + kelime) in (' ' + metin) if kelime.endswith(' ') or True else False


def etiketle(baslik, ozet):
    m = ' ' + norm(baslik) + ' ' + norm(ozet) + ' '
    baslik_n = ' ' + norm(baslik) + ' '
    sonuc = {}
    for et, kl in ETIKET.items():
        n = 0
        for k in kl:
            k = norm(k) + (' ' if k.endswith(' ') else '')
            n += m.count(' ' + k)
        if n: sonuc[et] = n
    # Zayıf (tek geçişli) eşleşmeleri ele: en az 2 geçiş ya da başlıkta geçmeli; 'İngilizce'/'Biyografi' tek geçişte de geçerli
    liste = [e for e, n in sonuc.items() if n >= (3 if e in ('Aile','Edebiyat & Yazarlık','Kadın','Sanat & Müzik','Doğa & Hayvanlar') else 2) or e in ('İngilizce', 'Biyografi', 'İstanbul') or any((' ' + norm(k)) in baslik_n for k in ETIKET[e])]
    return sorted(liste, key=lambda e: -sonuc[e])[:6]


def yil(t):
    m = re.search(r'(\d{4})', t or '')
    return int(m.group(1)) if m else None


def donustur(k):
    st = k['storytel'] or {}; kitap = st.get('book') or {}; ab = st.get('abook') or {}; ky = k['kitapyurdu'] or {}
    baslik = kitap.get('name') or k['baslik_csv']
    ozet = re.sub(r'\s*\n\s*', '\n', (ab.get('description') or '')).strip()
    tanitim = (ky.get('tanitim') or '').strip()
    ana = ANA.get(((kitap.get('category') or {}).get('title') or '').strip())
    etk = etiketle(baslik, ozet + ' ' + tanitim)
    if not ana:
        ana = 'Dil Öğrenimi' if 'İngilizce' in etk else 'Roman'
    if ana == 'Roman' and 'Gizem & Suç' in etk and etk.index('Gizem & Suç') == 0 and False: ana = 'Polisiye & Gizem'
    alt = None
    for e, ad in ALT_ONCELIK.get(ana, []):
        if e in etk: alt = ad; break
    if ana == 'Klasikler':
        alt = 'Dünya Klasikleri' if kitap.get('translatorsAsString') else 'Türk Klasikleri'
    if ana == 'Roman' and kitap.get('translatorsAsString') and not alt: alt = 'Çeviri Roman'
    alt = alt or ALT_VARSAYILAN[ana]
    for ek in (ana, alt, 'Sesli Kitap'):
        pass
    etk = [e for e in etk if e != 'Biyografi' or ana != 'Biyografi & Anı']
    if (kitap.get('abridged')) or 'kısaltılmış' in baslik.lower(): etk.append('Kısaltılmış Metin')
    if k['sure_sn'] < 2 * 3600: etk.append('Kısa Dinleme')
    elif k['sure_sn'] > 12 * 3600: etk.append('Uzun Dinleme')
    seri = None
    if kitap.get('series'):
        s = kitap['series'][0]; seri = s.get('name') or s.get('title') if isinstance(s, dict) else str(s)
    sayfa = ky.get('sayfa'); tahmini = False
    if not sayfa:
        sayfa = max(10, round(k['sure_sn'] / 3600 * 32)); tahmini = True
    sesli_t = ab.get('releaseDateFormat')
    return dict(
        isbn=k['isbn'], baslik=baslik, yazar=kitap.get('authorsAsString') or '', anlatici=ab.get('narratorAsString') or '',
        ceviren=kitap.get('translatorsAsString') or '', sesli_yayinci=(ab.get('publisher') or {}).get('name') or '',
        yayinevi=ky.get('yayinevi') or '', basili_isbn=ky.get('basili_isbn') or '',
        yayin_yili=yil(ky.get('yayin_tarihi')) or yil(sesli_t), sesli_tarih=sesli_t,
        sayfa=sayfa, sayfa_tahmini=tahmini, sure_sn=k['sure_sn'], ilerleme=k['ilerleme'],
        baslangic=k['baslangic'], son_dinleme=k['son_dinleme'], dinleme_yili=int(k['baslangic'][:4]),
        kategori=ana, alt_kategori=alt, etiketler=etk, seri=seri,
        puan=kitap.get('grade') or None, puan_sayisi=kitap.get('nrGrade') or 0,
        ozet=ozet, tanitim=tanitim, kapak_sesli=k['kapak_sesli'], kapak_basili=k['kapak_basili'],
        kaynak_storytel=bool(st), kaynak_kitapyurdu=ky.get('url') or '')


def veritabani(liste):
    yol = os.path.join(KOK, 'veri', 'kitaplik.db')
    if os.path.exists(yol): os.remove(yol)
    db = sqlite3.connect(yol)
    db.executescript('''
    CREATE TABLE kitaplar(isbn TEXT PRIMARY KEY, baslik, yazar, anlatici, ceviren, sesli_yayinci, yayinevi, basili_isbn, yayin_yili INT, sesli_tarih,
      sayfa INT, sayfa_tahmini INT, sure_sn INT, ilerleme INT, baslangic, son_dinleme, dinleme_yili INT, kategori, alt_kategori, seri,
      puan REAL, puan_sayisi INT, ozet, tanitim, kapak_sesli, kapak_basili, kaynak_kitapyurdu);
    CREATE TABLE etiketler(id INTEGER PRIMARY KEY, ad TEXT UNIQUE);
    CREATE TABLE kitap_etiket(isbn TEXT, etiket_id INT, PRIMARY KEY(isbn, etiket_id));
    CREATE VIRTUAL TABLE arama USING fts5(isbn UNINDEXED, baslik, yazar, ozet, tanitim, etiketler, tokenize="unicode61 remove_diacritics 2");
    ''')
    for k in liste:
        db.execute('INSERT INTO kitaplar VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   [k[a] for a in ('isbn', 'baslik', 'yazar', 'anlatici', 'ceviren', 'sesli_yayinci', 'yayinevi', 'basili_isbn', 'yayin_yili', 'sesli_tarih',
                                   'sayfa')] + [int(k['sayfa_tahmini'])] + [k[a] for a in ('sure_sn', 'ilerleme', 'baslangic', 'son_dinleme', 'dinleme_yili', 'kategori',
                                   'alt_kategori', 'seri', 'puan', 'puan_sayisi', 'ozet', 'tanitim', 'kapak_sesli', 'kapak_basili', 'kaynak_kitapyurdu')])
        for e in k['etiketler'] + [k['kategori'], k['alt_kategori']]:
            db.execute('INSERT OR IGNORE INTO etiketler(ad) VALUES(?)', [e])
            db.execute('INSERT OR IGNORE INTO kitap_etiket SELECT ?, id FROM etiketler WHERE ad=?', [k['isbn'], e])
        db.execute('INSERT INTO arama VALUES(?,?,?,?,?,?)', [k['isbn'], k['baslik'], k['yazar'], k['ozet'], k['tanitim'], ' '.join(k['etiketler'])])
    db.commit(); db.close()


if __name__ == '__main__':
    ham = json.load(open(os.path.join(ONB, 'hepsi.json'), encoding='utf8'))
    liste = [donustur(k) for k in ham]
    veritabani(liste)
    with open(os.path.join(KOK, 'uygulama', 'veri.js'), 'w', encoding='utf8') as f:
        f.write('window.KITAPLIK = ' + json.dumps(liste, ensure_ascii=False) + ';\n')
    import collections
    print(len(liste), 'kitap')
    print(collections.Counter(k['kategori'] for k in liste).most_common())
    print(collections.Counter((k['kategori'], k['alt_kategori']) for k in liste).most_common(30))
    print(collections.Counter(e for k in liste for e in k['etiketler']).most_common(40))
    print('özetsiz:', sum(1 for k in liste if not k['ozet'] and not k['tanitim']), 'sayfa tahmini:', sum(k['sayfa_tahmini'] for k in liste))


