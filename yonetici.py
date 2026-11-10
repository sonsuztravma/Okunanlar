# -*- coding: utf-8 -*-
"""Sonsuz Okumalar - Kitap Yönetim & Güncelleme Paneli
1. ElevenReader / Harici JSON Yükleme
2. Storytel CSV Yükleme
3. Tek Tek Kitap Ekleme (Ad/Yazar veya ISBN)
4. GitHub'a Gönderme (Canlıya Alma)
"""

import os, sys, json, csv, time, shutil, subprocess, threading, hashlib
from flask import Flask, request, jsonify, render_template_string

KOK_DIZIN = os.path.dirname(os.path.abspath(__file__))
ARSIV_DIZIN = os.path.join(KOK_DIZIN, 'KitapArsivi')
sys.path.insert(0, ARSIV_DIZIN)

import toplayici
import olustur

app = Flask(__name__)

islem_durumu = {"mesaj": "Hazır", "calisiyor": False, "son_hata": None}

def log(msg):
    islem_durumu["mesaj"] = msg
    print(f"[*] {msg}", flush=True)

def guncelleme_sureci(csv_dosya_yolu=None, eleven_json_yolu=None, tek_kitap_bilgi=None):
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

        # 2. ElevenReader JSON İçe Aktarma
        if eleven_json_yolu:
            log(f"ElevenReader JSON okunuyor: {os.path.basename(eleven_json_yolu)}")
            with open(eleven_json_yolu, 'r', encoding='utf8') as f:
                eleven_data = json.load(f)
                kitap_dizisi = eleven_data if isinstance(eleven_data, list) else eleven_data.get('books', [])
                for b in kitap_dizisi:
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
            log(f"{len(yeni_kitaplar)} adet yeni kitap internetten taranıyor...")
            for i, yk in enumerate(yeni_kitaplar, 1):
                baslik = yk.get('baslik_csv') or yk['isbn']
                yazar = yk.get('yazar_belirtilen', '')
                log(f"[{i}/{len(yeni_kitaplar)}] Taranıyor: {baslik}")

                st = toplayici.storytel(yk['isbn']) if yk['isbn'].isdigit() else {}
                if not st and baslik:
                    try:
                        s_arama = toplayici.indir('https://www.storytel.com/api/search.action?request_locale=tr&q=' + toplayici.up.quote(f"{baslik} {yazar}".strip()))
                        if s_arama:
                            s_json = json.loads(s_arama)
                            for sb in s_json.get('books', []):
                                st = sb
                                break
                    except: pass

                st_kitap = st.get('book', {}) if st else {}
                st_yazar = st_kitap.get('authorsAsString') or yazar
                st_baslik = st_kitap.get('name') or baslik

                ky = toplayici.kitapyurdu(yk['isbn'], st_baslik, st_yazar)

                kap_s = None
                if st_kitap.get('largeCover'):
                    kap_s = toplayici.kapak_indir(yk['isbn'], '_s', 'https://www.storytel.com' + st_kitap['largeCover'])
                elif yk.get('kapak_url'):
                    kap_s = toplayici.kapak_indir(yk['isbn'], '_e', yk['kapak_url'])

                kap_b = toplayici.kapak_indir(yk['isbn'], '_b', ky.get('kapak')) if ky else None

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

@app.route('/eleven-yukle', methods=['POST'])
def eleven_yukle():
    if islem_durumu["calisiyor"]:
        return jsonify({"hata": "Şu an başka bir işlem devam ediyor."}), 400
    if 'dosya' not in request.files:
        return jsonify({"hata": "Dosya seçilmedi."}), 400
    dosya = request.files['dosya']
    if not dosya.filename.endswith('.json'):
        return jsonify({"hata": "Lütfen geçerli bir .json dosyası yükleyin."}), 400
    
    hedef = os.path.join(KOK_DIZIN, f"eleven_{int(time.time())}.json")
    dosya.save(hedef)
    threading.Thread(target=guncelleme_sureci, kwargs={'eleven_json_yolu': hedef}).start()
    return jsonify({"mesaj": "ElevenReader kütüphanesi içe aktarılıyor..."})

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
<style>
  :root {
    --bg: #0c0e16;
    --panel: #151926;
    --panel2: #1e2436;
    --yazi: #f1f3f9;
    --soluk: #8e97b4;
    --vurgu: #f59e0b;
    --vurgu2: #10b981;
    --mor: #8b5cf6;
    --kenar: rgba(255, 255, 255, 0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  body { background: var(--bg); color: var(--yazi); padding: 24px 16px; min-height: 100vh; }
  .kutu { max-width: 820px; margin: 0 auto; }
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
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .kod-kutu { background: #08090f; border: 1px solid #232a3e; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 0.78rem; color: #a5b4fc; word-break: break-all; margin-bottom: 14px; user-select: all; }
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
    <div>
      <h1>Sonsuz Okumalar - Kitap Yönetim Paneli</h1>
      <span style="font-size:0.8rem;color:var(--soluk)">Storytel & ElevenReader Kütüphane Yöneticisi</span>
    </div>
    <div class="sayac-kutu">Arşivde: <strong id="toplamKitap">{{ toplam_kitap }}</strong> kitap</div>
  </header>

  <!-- BÖLÜM 1: ElevenReader / Harici JSON Yükleme -->
  <div class="kart vurgulu-mor">
    <h2 style="color: #c4b5fd;">🎧 ElevenReader / Harici Kitap Ekle (.json)</h2>
    <p>ElevenReader kütüphanenizdeki kitapları tek tıkla arşive ekleyebilirsiniz. Tarayıcınızda <strong><a href="https://elevenreader.io/reader/library" target="_blank" style="color:#a78bfa">elevenreader.io/reader/library</a></strong> sayfasında <strong>F12 -> Console</strong> sekmesine aşağıdaki kodu yapıştırıp Enter'a basın. İnen <code>elevenreader_kitaplar.json</code> dosyasını buraya yükleyin:</p>
    <div class="kod-kutu">
(async function(){console.log("ElevenReader taranıyor...");let t=null;try{for(let i=0;i<localStorage.length;i++){let k=localStorage.key(i);if(k.startsWith("firebase:authUser")){t=JSON.parse(localStorage.getItem(k)).stsTokenManager.accessToken;break;}}}catch(e){}let list=[];if(t){try{let r=await fetch("https://api.elevenlabs.io/v1/reader/reads?limit=200",{headers:{"authorization":"Bearer "+t}});if(r.ok){let d=await r.json();(d.reads||d||[]).forEach(x=>list.push({title:x.title||x.name||"",author:x.author||"",duration_seconds:x.duration_seconds||0,cover_url:x.cover_image_url||x.image_url||""}));}}catch(err){}}if(!list.length){document.querySelectorAll("a[href*='/reader/'], div[class*='book'], div[class*='card']").forEach(el=>{let tit=el.querySelector("h2,h3,h4,strong,span");let a=el.querySelector("p,small,span:nth-child(2)");let img=el.querySelector("img");if(tit&&tit.innerText.trim().length>1){list.push({title:tit.innerText.trim(),author:a?a.innerText.trim():"",cover_url:img?img.src:""});}});}if(!list.length){alert("Kitap bulunamadı! /reader/library sayfasında olduğunuzdan emin olun.");return;}let b=new Blob([JSON.stringify(list,null,2)],{type:"application/json"});let l=document.createElement("a");l.href=URL.createObjectURL(b);l.download="elevenreader_kitaplar.json";l.click();console.log(list.length+" kitap indirildi!");})();
    </div>
    <form id="elevenForm">
      <div class="form-grup">
        <label>İndirilen JSON Dosyasını Seçin (<code>elevenreader_kitaplar.json</code>):</label>
        <input type="file" id="elevenDosya" accept=".json" required>
      </div>
      <button type="submit" class="mor">ElevenReader / Harici Kitapları Arşive Aktar</button>
    </form>
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
  </div>
</div>

<div id="durumBar" class="durum-bar">
  <div class="spinner"></div>
  <span id="durumMetin">İşlem yapılıyor...</span>
</div>

<script>
let kontrolTimer = null;

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

document.getElementById('elevenForm').onsubmit = async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('elevenDosya');
  if (!fileInput.files.length) return;
  const formData = new FormData();
  formData.append('dosya', fileInput.files[0]);
  surecBaslat();
  const res = await fetch('/eleven-yukle', { method: 'POST', body: formData });
  const data = await res.json();
  if (data.hata) alert(data.hata);
};

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
