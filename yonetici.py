# -*- coding: utf-8 -*-
"""Sonsuz Okumalar - Kitap Yönetim & Güncelleme Paneli
1. ElevenReader / Harici JSON Önizleme, Seçme, Hariç Tutma ve Canlı Başlık/Yazar Düzenleme
2. Storytel CSV Yükleme
3. Tek Tek Kitap Ekleme (Ad/Yazar veya ISBN)
4. GitHub'a Gönderme (Canlıya Alma)
"""

import os, sys, json, csv, time, shutil, subprocess, threading, hashlib, zipfile, re
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, render_template_string, send_from_directory

KOK_DIZIN = os.path.dirname(os.path.abspath(__file__))
ARSIV_DIZIN = os.path.join(KOK_DIZIN, 'KitapArsivi')
sys.path.insert(0, ARSIV_DIZIN)

import toplayici
import olustur
try:
    import psikoloji_topla
except Exception:
    psikoloji_topla = None

app = Flask(__name__)

islem_durumu = {"mesaj": "Hazır", "calisiyor": False, "son_hata": None}

def log(msg):
    islem_durumu["mesaj"] = msg
    print(f"[*] {msg}", flush=True)

def guncelleme_sureci(csv_dosya_yolu=None, eleven_secili_kitaplar=None, tek_kitap_bilgi=None, psk_kitap_listesi=None):
    islem_durumu["calisiyor"] = True
    islem_durumu["son_hata"] = None
    try:
        hepsi_yol = os.path.join(toplayici.ONB, 'hepsi.json')
        mevcut_havuz = {}
        if os.path.exists(hepsi_yol):
            with open(hepsi_yol, 'r', encoding='utf8') as f:
                for k in json.load(f):
                    mevcut_havuz[k['isbn']] = k

        yeni_kitaplar = []

        # 0. Akademik & Psikoloji Kitap Listesi (.docx veya Metin)
        if psk_kitap_listesi and psikoloji_topla:
            dil_tipi = psk_kitap_listesi.get('dil', 'en')
            satirlar = psk_kitap_listesi.get('kitaplar', [])
            log(f"{len(satirlar)} adet Akademik/Psikoloji kitabı Amazon, Goodreads ve Apple Books üzerinden taranıyor...")
            for idx, item in enumerate(satirlar, 1):
                baslik = (item.get('title') or '').strip()
                yazar = (item.get('author') or '').strip()
                if not baslik:
                    continue
                h_kod = hashlib.md5(f"psk:{baslik.lower()}:{yazar.lower()}".encode('utf8')).hexdigest()[:6].upper()
                on_ek = "PSK_EN_" if dil_tipi == 'en' else "PSK_TR_"
                kod = f"{on_ek}{h_kod}"
                if kod in mevcut_havuz:
                    continue
                log(f"[{idx}/{len(satirlar)}] Psikoloji/Akademik taranıyor: {baslik} ({yazar})")
                try:
                    if dil_tipi == 'en':
                        kayit = psikoloji_topla.yabanci_kitap_tara(idx, baslik, yazar)
                    else:
                        kayit = psikoloji_topla.turkce_kitap_tara(idx, baslik, yazar)
                    kayit['isbn'] = kod
                    mevcut_havuz[kod] = kayit
                except Exception as e:
                    log(f"Uyarı ({baslik}): {e}")

        # 1. Storytel CSV İçe Aktarma
        if csv_dosya_yolu:
            log(f"CSV okunuyor: {os.path.basename(csv_dosya_yolu)}")
            with open(csv_dosya_yolu, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    isbn = (r.get('Kitap ISBN') or '').strip()
                    if not isbn: continue
                    h = (r.get('Kitap Süresi') or '0:0:0').split(':')
                    sn = int(h[0]) * 3600 + int(h[1]) * 60 + int(h[2]) if len(h) == 3 else 0
                    baslik = (r.get('Kitap adı') or '').strip()
                    ilerleme = round(float((r.get('Ayraç konumu') or '0').strip().strip('%').replace(',', '.') or 0))
                    baslangic = (r.get('Başlangıç tarihi') or '')[:10]
                    son = (r.get('Son ayraç ekleme tarihi') or '')[:10]
                    
                    if isbn in mevcut_havuz:
                        mevcut_havuz[isbn]['sure_sn'] = sn or mevcut_havuz[isbn].get('sure_sn', 0)
                        mevcut_havuz[isbn]['ilerleme'] = ilerleme
                        if son: mevcut_havuz[isbn]['son_dinleme'] = son
                    else:
                        yeni_kitaplar.append({
                            'isbn': isbn,
                            'baslik_csv': baslik,
                            'sure_sn': sn,
                            'ilerleme': ilerleme,
                            'format': r.get('Format', 'Sesli Kitap'),
                            'baslangic': baslangic,
                            'son_dinleme': son
                        })

        # 2. ElevenReader Seçili ve Düzenlenmiş Kitaplar
        if eleven_secili_kitaplar:
            log(f"{len(eleven_secili_kitaplar)} adet seçilen ElevenReader kitabı işleniyor...")
            for b in eleven_secili_kitaplar:
                baslik = (b.get('title') or b.get('baslik') or '').strip()
                if not baslik: continue
                yazar = (b.get('author') or b.get('yazar') or '').strip()
                isbn = (b.get('isbn') or '').strip()
                if not isbn:
                    h = hashlib.md5(f"eleven:{baslik}:{yazar}".encode('utf8')).hexdigest()[:10]
                    isbn = f"ELV{h}"

                sure_sn = int(b.get('duration_seconds') or b.get('sure_sn') or 0)
                bugun = time.strftime('%Y-%m-%d')
                tarih = b.get('date') or b.get('baslangic') or bugun

                if isbn in mevcut_havuz:
                    if sure_sn: mevcut_havuz[isbn]['sure_sn'] = sure_sn
                else:
                    yeni_kitaplar.append({
                        'isbn': isbn,
                        'baslik_csv': baslik,
                        'yazar_belirtilen': yazar,
                        'sure_sn': sure_sn,
                        'ilerleme': 100,
                        'format': 'ElevenReader',
                        'baslangic': tarih,
                        'son_dinleme': tarih,
                        'kapak_url': b.get('cover_url') or b.get('kapak')
                    })

        # 3. Tek Kitap Ekleme
        if tek_kitap_bilgi:
            isbn = tek_kitap_bilgi['isbn'].strip()
            if isbn in mevcut_havuz:
                mevcut_havuz[isbn]['sure_sn'] = tek_kitap_bilgi.get('sure_sn') or mevcut_havuz[isbn].get('sure_sn', 0)
            else:
                yeni_kitaplar.append(tek_kitap_bilgi)

        # Yeni kitapları Storytel / Kitapyurdu üzerinde tara
        if yeni_kitaplar:
            log(f"{len(yeni_kitaplar)} adet yeni kitap taranıyor...")
            for i, yk in enumerate(yeni_kitaplar, 1):
                baslik = yk.get('baslik_csv') or yk['isbn']
                yazar = yk.get('yazar_belirtilen', '')
                log(f"[{i}/{len(yeni_kitaplar)}] İnceleniyor: {baslik}")

                st = toplayici.storytel(yk['isbn']) if yk['isbn'].isdigit() else {}
                if not st and baslik:
                    try:
                        sorgu = f"{baslik} {yazar}".strip() if yazar else baslik
                        s_arama = toplayici.indir('https://www.storytel.com/api/search.action?request_locale=tr&q=' + toplayici.up.quote(sorgu))
                        if s_arama:
                            s_json = json.loads(s_arama)
                            for sb in s_json.get('books', []):
                                st = sb
                                break
                    except: pass

                st_kitap = st.get('book', {}) if st else {}
                # Eğer kullanıcı kendi yazarını girdiyse veya düzelttiyse öncelik ver
                nihai_yazar = yazar or st_kitap.get('authorsAsString') or ''
                nihai_baslik = baslik or st_kitap.get('name') or ''

                ky = toplayici.kitapyurdu(yk['isbn'], nihai_baslik, nihai_yazar)

                kap_s = None
                if st_kitap.get('largeCover'):
                    kap_s = toplayici.kapak_indir(yk['isbn'], '_s', 'https://www.storytel.com' + st_kitap['largeCover'])
                elif yk.get('kapak_url'):
                    kap_s = toplayici.kapak_indir(yk['isbn'], '_e', yk['kapak_url'])

                kap_b = toplayici.kapak_indir(yk['isbn'], '_b', ky.get('kapak')) if ky else None

                # Kitap objesini birleştirirken elle girilen yazar/başlığı koru
                if not st_kitap:
                    st_kitap = {'name': nihai_baslik, 'authorsAsString': nihai_yazar}
                    st = {'book': st_kitap, 'abook': {}}
                else:
                    if yazar: st_kitap['authorsAsString'] = nihai_yazar
                    if baslik: st_kitap['name'] = nihai_baslik

                islenmis = dict(yk, storytel=st, kitapyurdu=ky, kapak_sesli=kap_s, kapak_basili=kap_b)
                mevcut_havuz[yk['isbn']] = islenmis
                time.sleep(0.4)

        birlesik_liste = list(mevcut_havuz.values())
        toplayici.onb_yaz('hepsi.json', birlesik_liste)

        log("Veritabanı ve arayüz güncelleniyor...")
        donusturulmus = [olustur.donustur(k) for k in birlesik_liste]
        olustur.veritabani(donusturulmus)

        veri_js_icerik = 'window.KITAPLIK = ' + json.dumps(donusturulmus, ensure_ascii=False) + ';\n'
        
        # 1. KitapArsivi/uygulama/ içine yaz
        with open(os.path.join(ARSIV_DIZIN, 'uygulama', 'veri.js'), 'w', encoding='utf8') as f:
            f.write(veri_js_icerik)
            
        # 2. Kök dizine (GitHub Pages için) yaz
        with open(os.path.join(KOK_DIZIN, 'veri.js'), 'w', encoding='utf8') as f:
            f.write(veri_js_icerik)

        # Kapakları kök kapaklar/ dizinine eşitle
        src_kapak = os.path.join(ARSIV_DIZIN, 'uygulama', 'kapaklar')
        dst_kapak = os.path.join(KOK_DIZIN, 'kapaklar')
        if os.path.exists(src_kapak):
            for k_dosya in os.listdir(src_kapak):
                s_yol = os.path.join(src_kapak, k_dosya)
                d_yol = os.path.join(dst_kapak, k_dosya)
                if not os.path.exists(d_yol):
                    shutil.copy2(s_yol, d_yol)

        log(f"İşlem tamamlandı! Toplam {len(donusturulmus)} kitap hazır.")
    except Exception as e:
        islem_durumu["son_hata"] = str(e)
        log(f"Hata oluştu: {e}")
    finally:
        islem_durumu["calisiyor"] = False

@app.route('/logo.png')
def logo_dosya():
    return send_from_directory(KOK_DIZIN, 'logo.png')

@app.route('/favicon.png')
def favicon_dosya():
    return send_from_directory(KOK_DIZIN, 'favicon.png')

@app.route('/')
def index():
    hepsi_yol = os.path.join(toplayici.ONB, 'hepsi.json')
    toplam_kitap = 0
    if os.path.exists(hepsi_yol):
        try:
            with open(hepsi_yol, 'r', encoding='utf8') as f:
                toplam_kitap = len(json.load(f))
        except: pass

    return render_template_string(HTML_TEMPLATE, toplam_kitap=toplam_kitap)

@app.route('/durum')
def durum():
    return jsonify(islem_durumu)

@app.route('/tek-kitap-ekle', methods=['POST'])
def tek_kitap_ekle():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Şu an başka bir işlem devam ediyor."}), 400
    veri = request.json or {}
    isbn = veri.get('isbn', '').strip()
    baslik = veri.get('baslik', '').strip()
    yazar = veri.get('yazar', '').strip()
    if not isbn and not baslik:
        return jsonify({"hata": "Lütfen en azından ISBN veya Kitap Adı girin."}), 400
    
    if not isbn:
        isbn = "KITAP" + hashlib.md5(f"{baslik}:{yazar}".encode('utf8')).hexdigest()[:10]

    sure_saat = float(veri.get('sure_saat', 0) or 0)
    sn = int(sure_saat * 3600)
    bugun = time.strftime('%Y-%m-%d')
    
    k_bilgi = {
        'isbn': isbn,
        'baslik_csv': baslik or f"ISBN-{isbn}",
        'yazar_belirtilen': yazar,
        'sure_sn': sn,
        'ilerleme': 100,
        'format': 'Sesli Kitap',
        'baslangic': veri.get('baslangic') or bugun,
        'son_dinleme': veri.get('son_dinleme') or bugun
    }
    threading.Thread(target=guncelleme_sureci, kwargs={'tek_kitap_bilgi': k_bilgi}).start()
    return jsonify({"mesaj": "Kitap ekleme süreci başlatıldı."})

@app.route('/csv-yukle', methods=['POST'])
def csv_yukle():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Şu an başka bir işlem devam ediyor."}), 400
    if 'dosya' not in request.files:
        return jsonify({"hata": "Dosya seçilmedi."}), 400
    dosya = request.files['dosya']
    if not dosya.filename.endswith('.csv'):
        return jsonify({"hata": "Lütfen geçerli bir .csv dosyası yükleyin."}), 400
    
    hedef = os.path.join(KOK_DIZIN, f"yuklenen_{int(time.time())}.csv")
    dosya.save(hedef)
    threading.Thread(target=guncelleme_sureci, kwargs={'csv_dosya_yolu': hedef}).start()
    return jsonify({"mesaj": "CSV yükleme ve güncelleme süreci başlatıldı."})

@app.route('/eleven-secilenleri-ekle', methods=['POST'])
def eleven_secilenleri_ekle():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Şu an başka bir işlem devam ediyor."}), 400
    veri = request.json or {}
    kitaplar = veri.get('kitaplar', [])
    if not kitaplar:
        return jsonify({"hata": "Lütfen listeye eklemek için en az bir kitap seçin."}), 400
    
    threading.Thread(target=guncelleme_sureci, kwargs={'eleven_secili_kitaplar': kitaplar}).start()
    return jsonify({"mesaj": f"{len(kitaplar)} adet kitap için aktarma süreci başlatıldı."})

@app.route('/docx-coz', methods=['POST'])
def docx_coz():
    if 'dosya' not in request.files:
        return jsonify({"hata": "Dosya seçilmedi."}), 400
    dosya = request.files['dosya']
    gecici_yol = os.path.join(KOK_DIZIN, f"gecici_{int(time.time())}.docx")
    dosya.save(gecici_yol)
    satirlar = []
    try:
        with zipfile.ZipFile(gecici_yol) as z:
            xml_icerik = z.read('word/document.xml')
        agac = ET.fromstring(xml_icerik)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        for p in agac.findall('.//w:p', ns):
            parcalar = [t.text for t in p.findall('.//w:t', ns) if t.text]
            tam = ''.join(parcalar).strip()
            if tam and len(tam) > 3:
                satirlar.append(tam)
    except Exception as e:
        return jsonify({"hata": f"DOCX okunamadı: {e}"}), 400
    finally:
        if os.path.exists(gecici_yol):
            os.remove(gecici_yol)
    return jsonify({"satirlar": satirlar})

@app.route('/psikoloji-ekle', methods=['POST'])
def psikoloji_ekle():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Şu an başka bir işlem devam ediyor."}), 400
    veri = request.json or {}
    metin = (veri.get('metin') or '').strip()
    dil = veri.get('dil', 'en')
    if not metin:
        return jsonify({"hata": "Lütfen eklenecek kitap listesini girin veya .docx yükleyin."}), 400

    kitaplar = []
    for raw in metin.splitlines():
        s = re.sub(r'^\s*\d+[\.\)\-\s]+', '', raw.strip()).strip()
        if not s or len(s) < 3:
            continue
        baslik, yazar = s, ""
        for ayirac in [' – ', ' — ', ' - ']:
            if ayirac in s:
                parca = s.rsplit(ayirac, 1)
                baslik, yazar = parca[0].strip(), parca[1].strip()
                break
        kitaplar.append({'title': baslik, 'author': yazar})

    if not kitaplar:
        return jsonify({"hata": "Geçerli kitap satırı bulunamadı."}), 400

    threading.Thread(
        target=guncelleme_sureci,
        kwargs={'psk_kitap_listesi': {'dil': dil, 'kitaplar': kitaplar}}
    ).start()
    return jsonify({"mesaj": f"{len(kitaplar)} adet Akademik/Psikoloji kitabı için tarama ve çeviri başlatıldı."})

@app.route('/githuba-gonder', methods=['POST'])
def githuba_gonder():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Bir işlem devam ederken GitHub'a gönderilemez."}), 400
    try:
        log("GitHub'a commit ve push yapılıyor...")
        subprocess.run(["git", "add", "."], cwd=KOK_DIZIN, check=True)
        t = time.strftime('%d.%m.%Y %H:%M')
        subprocess.run(["git", "commit", "-m", f"update: Yeni kitaplar eklendi ({t})"], cwd=KOK_DIZIN, check=False)
        p = subprocess.run(["git", "push", "origin", "main"], cwd=KOK_DIZIN, capture_output=True, text=True)
        if p.returncode == 0:
            log("Başarıyla GitHub'a gönderildi!")
            return jsonify({"mesaj": "GitHub Pages başarıyla güncellendi!"})
        else:
            hata = p.stderr or p.stdout
            log(f"GitHub hatası: {hata}")
            return jsonify({"hata": f"Push hatası: {hata}"}), 500
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sonsuz Okumalar - Kitap Yönetim Paneli</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>
  :root {
    --bg: #0c0e16;
    --panel: #151926;
    --panel2: #1e2436;
    --panel3: #283048;
    --yazi: #f1f3f9;
    --soluk: #8e97b4;
    --vurgu: #f59e0b;
    --vurgu2: #10b981;
    --mor: #8b5cf6;
    --kirmizi: #ef4444;
    --kenar: rgba(255, 255, 255, 0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  body { background: var(--bg); color: var(--yazi); padding: 24px 16px; min-height: 100vh; }
  .kutu { max-width: 880px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--kenar); }
  h1 { font-size: 1.4rem; color: var(--vurgu); }
  .sayac-kutu { background: var(--panel2); padding: 6px 14px; border-radius: 999px; font-size: 0.85rem; }
  .kart { background: var(--panel); border: 1px solid var(--kenar); border-radius: 14px; padding: 20px; margin-bottom: 20px; }
  .kart.vurgulu-mor { border-color: rgba(139, 92, 246, 0.4); box-shadow: 0 4px 20px rgba(139, 92, 246, 0.1); }
  h2 { font-size: 1.15rem; margin-bottom: 12px; color: var(--yazi); display: flex; align-items: center; gap: 8px; }
  p { font-size: 0.88rem; color: var(--soluk); margin-bottom: 14px; line-height: 1.5; }
  .form-grup { margin-bottom: 12px; }
  label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--soluk); margin-bottom: 4px; }
  input, button { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--kenar); background: var(--bg); color: var(--yazi); font-size: 0.9rem; }
  .izgara { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  button { background: var(--vurgu); color: #0c0e16; font-weight: 700; border: none; cursor: pointer; transition: opacity 0.2s; margin-top: 6px; }
  button:hover { opacity: 0.9; }
  button.yesil { background: var(--vurgu2); }
  button.mor { background: var(--mor); color: #fff; }
  button.gri { background: var(--panel2); color: var(--yazi); border: 1px solid var(--kenar); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .kod-kutu { background: #08090f; border: 1px solid #232a3e; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 0.78rem; color: #a5b4fc; word-break: break-all; margin-bottom: 14px; user-select: all; }
  
  /* Seçim & Düzenleme Listesi Stilleri */
  .onizleme-kapsul { margin-top: 16px; border: 1px solid var(--kenar); border-radius: 12px; background: rgba(12, 14, 22, 0.6); padding: 16px; display: none; }
  .onizleme-ust { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 10px; flex-wrap: wrap; }
  .arama-filtre { padding: 8px 12px; border-radius: 8px; border: 1px solid var(--kenar); background: var(--bg); color: var(--yazi); font-size: 0.85rem; width: 220px; }
  .buton-grubu { display: flex; gap: 6px; }
  .buton-grubu button { width: auto; padding: 6px 12px; margin: 0; font-size: 0.78rem; border-radius: 6px; }
  
  .secim-listesi { max-height: 420px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; padding-right: 4px; }
  .secim-kart { display: flex; gap: 12px; padding: 12px; border-radius: 10px; background: var(--panel); border: 1px solid var(--kenar); align-items: flex-start; transition: border-color 0.15s; }
  .secim-kart:hover { border-color: rgba(139, 92, 246, 0.45); }
  .secim-kart input[type="checkbox"] { width: 20px; height: 20px; accent-color: var(--mor); cursor: pointer; margin-top: 4px; }
  
  .kart-form { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .kart-satir { display: grid; grid-template-columns: 2fr 1.3fr; gap: 8px; }
  .duzen-girdi { padding: 7px 10px; border-radius: 6px; border: 1px solid var(--kenar); background: rgba(12, 14, 22, 0.8); color: var(--yazi); font-size: 0.85rem; }
  .duzen-girdi:focus { border-color: var(--mor); outline: none; }
  .kart-alt-bilgi { display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--soluk); }
  
  .satir-haric { background: none; border: none; color: var(--soluk); width: auto; padding: 4px 8px; font-size: 0.75rem; cursor: pointer; border-radius: 6px; margin: 0; }
  .satir-haric:hover { color: var(--kirmizi); background: rgba(239, 68, 68, 0.12); }
  
  .durum-bar { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1f2937; border: 1px solid var(--vurgu); padding: 12px 24px; border-radius: 999px; font-size: 0.9rem; box-shadow: 0 10px 25px rgba(0,0,0,0.5); display: none; z-index: 100; }
  .durum-bar.aktif { display: flex; align-items: center; gap: 10px; }
  .spinner { width: 14px; height: 14px; border: 2px solid var(--vurgu); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .link-bar { margin-top: 24px; text-align: center; font-size: 0.85rem; }
  .link-bar a { color: var(--vurgu); text-decoration: none; margin: 0 8px; }
</style>
</head>
<body>
<div class="kutu">
  <header>
    <div style="display:flex;align-items:center;gap:12px;">
      <img src="/logo.png" alt="Sonsuz Travma Logo" style="width:46px;height:46px;border-radius:11px;object-fit:cover;border:1px solid rgba(245,158,11,0.4);">
      <div>
        <h1>Sonsuz Okumalar - Kitap Yönetim Paneli</h1>
        <span style="font-size:0.8rem;color:var(--soluk)">Storytel, ElevenReader & Akademik Kütüphane Yöneticisi</span>
      </div>
    </div>
    <div class="sayac-kutu">Arşivde: <strong id="toplamKitap">{{ toplam_kitap }}</strong> kitap</div>
  </header>

  <!-- BÖLÜM 1: ElevenReader / Harici JSON Yükleme, Düzenleme ve Seçme -->
  <div class="kart vurgulu-mor">
    <h2 style="color: #c4b5fd;">🎧 ElevenReader / Harici Kitap Ekle (.json)</h2>
    <p>ElevenReader'dan indirdiğiniz <code>elevenreader_kitaplar.json</code> dosyasını seçin. Kitap adı ve yazarları <strong>kutucuklardan anında düzenleyebilir</strong>, istemediğiniz dosyaları hariç tutabilirsiniz:</p>
    
    <details style="margin-bottom: 14px; font-size: 0.82rem; color: var(--soluk);">
      <summary style="cursor: pointer; color: #a78bfa; font-weight: 600; margin-bottom: 8px;">Tarayıcı Konsol Kodunu Göster (Henüz indirmediyseniz)</summary>
      <div class="kod-kutu">
(async function(){console.log("ElevenReader taranıyor...");let t=null;try{for(let i=0;i<localStorage.length;i++){let k=localStorage.key(i);if(k.startsWith("firebase:authUser")){t=JSON.parse(localStorage.getItem(k)).stsTokenManager.accessToken;break;}}}catch(e){}let list=[];if(t){try{let r=await fetch("https://api.elevenlabs.io/v1/reader/reads?limit=200",{headers:{"authorization":"Bearer "+t}});if(r.ok){let d=await r.json();(d.reads||d||[]).forEach(x=>list.push({title:x.title||x.name||"",author:x.author||"",duration_seconds:x.duration_seconds||0,cover_url:x.cover_image_url||x.image_url||""}));}}catch(err){}}if(!list.length){document.querySelectorAll("a[href*='/reader/'], div[class*='book'], div[class*='card']").forEach(el=>{let tit=el.querySelector("h2,h3,h4,strong,span");let a=el.querySelector("p,small,span:nth-child(2)");let img=el.querySelector("img");if(tit&&tit.innerText.trim().length>1){list.push({title:tit.innerText.trim(),author:a?a.innerText.trim():"",cover_url:img?img.src:""});}});}if(!list.length){alert("Kitap bulunamadı! /reader/library sayfasında olduğunuzdan emin olun.");return;}let b=new Blob([JSON.stringify(list,null,2)],{type:"application/json"});let l=document.createElement("a");l.href=URL.createObjectURL(b);l.download="elevenreader_kitaplar.json";l.click();console.log(list.length+" kitap indirildi!");})();
      </div>
    </details>

    <div class="form-grup">
      <label>1. Adım: JSON Dosyasını Seçin:</label>
      <input type="file" id="elevenDosyaGirdi" accept=".json">
    </div>

    <!-- Kitap Seçim, Canlı Düzenleme & Hariç Tutma Listesi -->
    <div id="onizlemeKapsul" class="onizleme-kapsul">
      <div class="onizleme-ust">
        <div>
          <strong id="secimBilgi" style="color:var(--vurgu)">0 kitap seçildi</strong>
          <span id="toplamYuklenen" style="font-size:0.8rem;color:var(--soluk);margin-left:6px;">(Toplam 0)</span>
        </div>
        <div class="buton-grubu">
          <input type="text" id="filtreGirdi" class="arama-filtre" placeholder="Listede ara...">
          <button type="button" class="gri" onclick="hepsiniSec(true)">Tümünü Seç</button>
          <button type="button" class="gri" onclick="hepsiniSec(false)">Hiçbiri</button>
        </div>
      </div>

      <div style="font-size: 0.76rem; color: var(--soluk); margin-bottom: 8px;">
        💡 İpucu: Kitap adında yazar yazıyorsa ayırabilir, yazar belirtilmeyenlere yazar ekleyebilirsiniz. Bilgiler Storytel ve Kitapyurdu'nda aratılırken güncel hali kullanılacaktır.
      </div>

      <div id="secimListesi" class="secim-listesi"></div>

      <button type="button" id="secilenleriEkleBtn" class="mor" onclick="secilenleriAktar()">Seçilen Kitapları Arşive Aktar</button>
    </div>
  </div>

  <!-- BÖLÜM 2: Storytel CSV Yükleme -->
  <div class="kart">
    <h2>📁 Storytel CSV Dosyası Yükle (.csv)</h2>
    <p>Storytel'den aldığınız yeni bir CSV dosyasını seçin. <strong>Önceki kitaplarınız asla silinmez</strong>; yeni kitaplar mevcut arşive eklenir.</p>
    <form id="csvForm">
      <div class="form-grup">
        <input type="file" id="csvDosya" accept=".csv" required>
      </div>
      <button type="submit">Storytel CSV Dosyasını İçe Aktar</button>
    </form>
  </div>

  <!-- BÖLÜM 3: Tek Kitap Ekleme -->
  <div class="kart">
    <h2>➕ Tek Bir Kitap Ekle (ISBN veya Ad/Yazar)</h2>
    <p>İster Storytel ISBN'i, isterseniz doğrudan Kitap Adı ve Yazarını yazın. Kapak, özet, kategori ve yayınevi bilgileri internetten otomatik bulunup eklenir.</p>
    <form id="tekKitapForm">
      <div class="izgara">
        <div class="form-grup">
          <label>Kitap Adı</label>
          <input type="text" id="tkBaslik" placeholder="Örn: Körlük">
        </div>
        <div class="form-grup">
          <label>Yazar Adı</label>
          <input type="text" id="tkYazar" placeholder="Örn: Jose Saramago">
        </div>
      </div>
      <div class="izgara">
        <div class="form-grup">
          <label>ISBN (Varsa, yoksa boş bırakabilirsiniz)</label>
          <input type="text" id="tkIsbn" placeholder="Örn: 9789180909730">
        </div>
        <div class="form-grup">
          <label>Dinleme Süresi (Saat)</label>
          <input type="number" step="0.1" id="tkSure" placeholder="Örn: 8.5">
        </div>
      </div>
      <button type="submit">Kitabı Bul ve Arşive Ekle</button>
    </form>
  </div>

  <!-- BÖLÜM 3.5: Akademik & Psikoloji Kitap Listesi (.docx veya Metin) -->
  <div class="kart" style="border-color: rgba(16, 185, 129, 0.35);">
    <h2 style="color: #6ee7b7;">🎓 Akademik & Psikoloji Kitabı Ekle (.docx veya Metin Listesi)</h2>
    <p>Word (<code>.docx</code>) dosyası yükleyin veya her satıra <code>Kitap Adı - Yazar Adı</code> gelecek şekilde yapıştırın. Amazon, Goodreads ve Apple Books'tan kapak ve tam tanıtım yazıları çekilip otomatik Türkçeye çevrilir.</p>
    <div class="izgara" style="margin-bottom: 10px;">
      <div class="form-grup">
        <label>Word (.docx) Dosyasından Satırları Yükle (İsteğe Bağlı)</label>
        <input type="file" id="pskDocxDosya" accept=".docx">
      </div>
      <div class="form-grup">
        <label>Kaynak Kitap Dili</label>
        <select id="pskDil" style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--kenar);background:var(--bg);color:var(--yazi);font-size:0.9rem;">
          <option value="en">İngilizce / Yabancı (Otomatik Türkçe Çevirili)</option>
          <option value="tr">Türkçe (Kitapyurdu & Goodreads)</option>
        </select>
      </div>
    </div>
    <div class="form-grup">
      <label>Kitap Listesi (Her satıra: Kitap Adı - Yazar Adı)</label>
      <textarea id="pskMetin" rows="6" style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--kenar);background:var(--bg);color:var(--yazi);font-size:0.86rem;resize:vertical;" placeholder="Örn:&#10;The Body Keeps the Score - Bessel van der Kolk&#10;Trauma and Recovery - Judith Herman"></textarea>
    </div>
    <button type="button" class="yesil" onclick="psikolojiListesiEkle()">Psikoloji & Akademik Kitapları Tara ve Ekle</button>
  </div>

  <!-- BÖLÜM 4: GitHub'a Gönderme -->
  <div class="kart">
    <h2>🚀 Değişiklikleri GitHub Pages'e Yayınla</h2>
    <p>Yeni eklediğiniz kitapları tek tıkla GitHub deponuza gönderin. Böylece <code>sonsuztravma.github.io/Okunanlar</code> adresiniz hemen güncellensin.</p>
    <button id="ghBtn" class="yesil" onclick="githubaGonder()">GitHub'a Gönder (Canlıya Al)</button>
  </div>

  <div class="link-bar">
    <a href="index.html" target="_blank">📖 Kütüphaneyi Aç (Yerel)</a> •
    <a href="https://sonsuztravma.github.io/Okunanlar/" target="_blank">🌐 GitHub Pages (Canlı)</a> •
    <a href="https://github.com/sonsuztravma/Okunanlar" target="_blank">💻 GitHub Deposu</a>
    <div style="margin-top:10px;color:var(--soluk);font-size:0.82rem;">
      Görüş ve öneriler için iletişim: <a href="mailto:sonsuz.travma@gmail.com">sonsuz.travma@gmail.com</a>
    </div>
  </div>
</div>

<div id="durumBar" class="durum-bar">
  <div class="spinner"></div>
  <span id="durumMetin">İşlem yapılıyor...</span>
</div>

<script>
let kontrolTimer = null;
let yuklenenElevenKitaplar = [];

function durumKontrol() {
  fetch('/durum')
    .then(r => r.json())
    .then(d => {
      const bar = document.getElementById('durumBar');
      const metin = document.getElementById('durumMetin');
      if (d.calisiyor) {
        bar.classList.add('aktif');
        metin.textContent = d.mesaj;
      } else {
        bar.classList.remove('aktif');
        if (kontrolTimer) {
          clearInterval(kontrolTimer);
          kontrolTimer = null;
          alert(d.mesaj || "İşlem tamamlandı!");
          location.reload();
        }
      }
    });
}

function surecBaslat() {
  const bar = document.getElementById('durumBar');
  bar.classList.add('aktif');
  document.getElementById('durumMetin').textContent = "Başlatılıyor...";
  if (!kontrolTimer) {
    kontrolTimer = setInterval(durumKontrol, 1500);
  }
}

// Dosya seçildiğinde listeyi doldur
document.getElementById('elevenDosyaGirdi').onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (event) => {
    try {
      const data = JSON.parse(event.target.result);
      const list = Array.isArray(data) ? data : (data.books || []);
      yuklenenElevenKitaplar = list.map((item, idx) => {
        let t = (item.title || item.baslik || "").trim();
        let a = (item.author || item.yazar || "").trim();

        // Eğer başlık içinde tire veya iki nokta ile yazar ayrılmışsa otomatik ayıkla
        // Örn: "Dune - Frank Herbert" veya "Frank Herbert: Dune"
        if (!a && t.includes(" - ")) {
          const parts = t.split(" - ");
          if (parts.length === 2) {
            t = parts[0].trim();
            a = parts[1].trim();
          }
        }

        return {
          id: idx,
          title: t,
          author: a,
          duration_seconds: item.duration_seconds || item.sure_sn || 0,
          cover_url: item.cover_url || item.kapak || "",
          secili: true,
          silindi: false
        };
      });

      document.getElementById('onizlemeKapsul').style.display = 'block';
      secimListesiCiz();
    } catch(err) {
      alert("JSON dosyası ayrıştırılamadı: " + err);
    }
  };
  reader.readAsText(file);
};

function secimListesiCiz() {
  const container = document.getElementById('secimListesi');
  const filtre = document.getElementById('filtreGirdi').value.toLowerCase();
  container.innerHTML = '';

  let seciliSayisi = 0;
  let gorunenSayisi = 0;

  yuklenenElevenKitaplar.forEach(k => {
    if (k.silindi) return;
    gorunenSayisi++;
    if (k.secili) seciliSayisi++;

    const aramaMetin = (k.title + " " + k.author).toLowerCase();
    if (filtre && !aramaMetin.includes(filtre)) return;

    const sureDk = k.duration_seconds ? Math.round(k.duration_seconds / 60) + " dk dinleme" : "";

    const div = document.createElement('div');
    div.className = 'secim-kart';
    div.innerHTML = `
      <input type="checkbox" ${k.secili ? 'checked' : ''} onchange="secimDegistir(${k.id}, this.checked)" title="Aktarmak için seç">
      <div class="kart-form">
        <div class="kart-satir">
          <input type="text" class="duzen-girdi" value="${k.title.replace(/"/g, '&quot;')}" oninput="baslikGuncelle(${k.id}, this.value)" placeholder="Kitap Adı">
          <input type="text" class="duzen-girdi" value="${k.author.replace(/"/g, '&quot;')}" oninput="yazarGuncelle(${k.id}, this.value)" placeholder="Yazar Adı (İsteğe bağlı)">
        </div>
        <div class="kart-alt-bilgi">
          <span>${sureDk || 'Süre belirtilmemiş'}</span>
          <button type="button" class="satir-haric" onclick="haricTut(${k.id})">Listeden Hariç Tut ✕</button>
        </div>
      </div>
    `;
    container.appendChild(div);
  });

  document.getElementById('secimBilgi').textContent = `${seciliSayisi} kitap seçildi`;
  document.getElementById('toplamYuklenen').textContent = `(Toplam ${gorunenSayisi})`;
  document.getElementById('secilenleriEkleBtn').textContent = `${seciliSayisi} Seçilen Kitabı Arşive Aktar`;
  document.getElementById('secilenleriEkleBtn').disabled = seciliSayisi === 0;
}

function baslikGuncelle(id, val) {
  const k = yuklenenElevenKitaplar.find(x => x.id === id);
  if (k) k.title = val.trim();
}

function yazarGuncelle(id, val) {
  const k = yuklenenElevenKitaplar.find(x => x.id === id);
  if (k) k.author = val.trim();
}

function secimDegistir(id, val) {
  const k = yuklenenElevenKitaplar.find(x => x.id === id);
  if (k) k.secili = val;
  const seciliSayisi = yuklenenElevenKitaplar.filter(x => x.secili && !x.silindi).length;
  document.getElementById('secimBilgi').textContent = `${seciliSayisi} kitap seçildi`;
  document.getElementById('secilenleriEkleBtn').textContent = `${seciliSayisi} Seçilen Kitabı Arşive Aktar`;
  document.getElementById('secilenleriEkleBtn').disabled = seciliSayisi === 0;
}

function haricTut(id) {
  const k = yuklenenElevenKitaplar.find(x => x.id === id);
  if (k) {
    k.silindi = true;
    k.secili = false;
  }
  secimListesiCiz();
}

function hepsiniSec(durum) {
  yuklenenElevenKitaplar.forEach(k => {
    if (!k.silindi) k.secili = durum;
  });
  secimListesiCiz();
}

document.getElementById('filtreGirdi').oninput = secimListesiCiz;

async function secilenleriAktar() {
  const secilenler = yuklenenElevenKitaplar.filter(k => k.secili && !k.silindi);
  if (!secilenler.length) {
    alert("Lütfen eklenecek en az bir kitap seçin.");
    return;
  }

  if (!confirm(`${secilenler.length} adet kitap arşive aktarılacak. Onaylıyor musunuz?`)) return;

  surecBaslat();
  const res = await fetch('/eleven-secilenleri-ekle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kitaplar: secilenler })
  });
  const data = await res.json();
  if (data.hata) alert(data.hata);
}

// Storytel CSV Formu
document.getElementById('csvForm').onsubmit = async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('csvDosya');
  if (!fileInput.files.length) return;
  const formData = new FormData();
  formData.append('dosya', fileInput.files[0]);
  surecBaslat();
  const res = await fetch('/csv-yukle', { method: 'POST', body: formData });
  const data = await res.json();
  if (data.hata) alert(data.hata);
};

// Tek Kitap Formu
document.getElementById('tekKitapForm').onsubmit = async (e) => {
  e.preventDefault();
  const body = {
    isbn: document.getElementById('tkIsbn').value,
    baslik: document.getElementById('tkBaslik').value,
    yazar: document.getElementById('tkYazar').value,
    sure_saat: document.getElementById('tkSure').value
  };
  surecBaslat();
  const res = await fetch('/tek-kitap-ekle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  if (data.hata) alert(data.hata);
};

// Word (.docx) yüklenince satırları metin kutusuna aktar
document.getElementById('pskDocxDosya').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('dosya', file);
  const res = await fetch('/docx-coz', { method: 'POST', body: fd });
  const data = await res.json();
  if (data.hata) {
    alert(data.hata);
  } else if (data.satirlar) {
    document.getElementById('pskMetin').value = data.satirlar.join('\n');
  }
};

async function psikolojiListesiEkle() {
  const metin = document.getElementById('pskMetin').value.trim();
  const dil = document.getElementById('pskDil').value;
  if (!metin) {
    alert("Lütfen eklenecek kitap listesini girin veya bir .docx dosyası seçin.");
    return;
  }
  surecBaslat();
  const res = await fetch('/psikoloji-ekle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ metin, dil })
  });
  const data = await res.json();
  if (data.hata) alert(data.hata);
}

async function githubaGonder() {
  if (!confirm("Değişiklikler GitHub'a gönderilsin mi?")) return;
  const btn = document.getElementById('ghBtn');
  btn.disabled = true;
  btn.textContent = "Gönderiliyor...";
  try {
    const res = await fetch('/githuba-gonder', { method: 'POST' });
    const data = await res.json();
    alert(data.mesaj || data.hata);
  } catch (err) {
    alert("Hata: " + err);
  } finally {
    btn.disabled = false;
    btn.textContent = "GitHub'a Gönder (Canlıya Al)";
  }
}
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("=" * 60)
    print("Sonsuz Okumalar - Kitap Yönetim Paneli Başlatıldı!")
    print("Tarayıcınızda şu adresi açın: http://localhost:5000")
    print("=" * 60)
    app.run(port=5000, debug=False)
