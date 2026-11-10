# -*- coding: utf-8 -*-
"""Sonsuz Okumalar - Kitap Yönetim & Güncelleme Paneli
Bu sunucu sayesinde:
1. Tek tek yeni sesli kitap ekleyebilirsiniz (ISBN girerek Storytel ve Kitapyurdu'ndan otomatik çeker).
2. Yeni Storytel CSV dosyası yükleyip mevcut kitapların üstüne birleştirebilirsiniz (Önceki kitaplar ASLA kaybolmaz).
3. Tek tıkla verileri güncelleyip GitHub'a gönderebilirsiniz.
"""

import os, sys, json, csv, time, shutil, subprocess, threading
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

def guncelleme_sureci(csv_dosya_yolu=None, tek_kitap_bilgi=None):
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

        if tek_kitap_bilgi:
            isbn = tek_kitap_bilgi['isbn'].strip()
            if isbn not in mevcut_havuz:
                yeni_kitaplar.append(tek_kitap_bilgi)

        if yeni_kitaplar:
            log(f"{len(yeni_kitaplar)} adet yeni kitap internetten (Storytel/Kitapyurdu) taranıyor...")
            for i, yk in enumerate(yeni_kitaplar, 1):
                log(f"[{i}/{len(yeni_kitaplar)}] Taranıyor: {yk.get('baslik_csv') or yk['isbn']}")
                islenmis = toplayici.isle(yk)
                mevcut_havuz[yk['isbn']] = islenmis
                time.sleep(0.5)

        birlesik_liste = list(mevcut_havuz.values())
        toplayici.onb_yaz('hepsi.json', birlesik_liste)

        log("Kategoriler, etiketler ve veritabanı güncelleniyor...")
        donusturulmus = [olustur.donustur(k) for k in birlesik_liste]
        olustur.veritabani(donusturulmus)

        veri_js_icerik = 'window.KITAPLIK = ' + json.dumps(donusturulmus, ensure_ascii=False) + ';\n'
        
        # 1. KitapArsivi/uygulama/ içine yaz
        with open(os.path.join(ARSIV_DIZIN, 'uygulama', 'veri.js'), 'w', encoding='utf8') as f:
            f.write(veri_js_icerik)
            
        # 2. Kök dizine (GitHub Pages için) yaz
        with open(os.path.join(KOK_DIZIN, 'veri.js'), 'w', encoding='utf8') as f:
            f.write(veri_js_icerik)

        # Kapakları da kök kapaklar/ dizinine eşitle
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
    if not isbn:
        return jsonify({"hata": "ISBN boş olamaz."}), 400
    
    baslik = veri.get('baslik', '').strip() or f"ISBN-{isbn}"
    sure_saat = float(veri.get('sure_saat', 0) or 0)
    sn = int(sure_saat * 3600)
    bugun = time.strftime('%Y-%m-%d')
    
    k_bilgi = {
        'isbn': isbn,
        'baslik_csv': baslik,
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
<title>Sonsuz Okumalar - Kitap Ekleme & Yönetim</title>
<style>
  :root {
    --bg: #0c0e16;
    --panel: #151926;
    --panel2: #1e2436;
    --yazi: #f1f3f9;
    --soluk: #8e97b4;
    --vurgu: #f59e0b;
    --vurgu2: #10b981;
    --kenar: rgba(255, 255, 255, 0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  body { background: var(--bg); color: var(--yazi); padding: 24px 16px; min-height: 100vh; }
  .kutu { max-width: 800px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--kenar); }
  h1 { font-size: 1.4rem; color: var(--vurgu); }
  .sayac-kutu { background: var(--panel2); padding: 6px 14px; border-radius: 999px; font-size: 0.85rem; }
  .kart { background: var(--panel); border: 1px solid var(--kenar); border-radius: 14px; padding: 20px; margin-bottom: 20px; }
  h2 { font-size: 1.1rem; margin-bottom: 14px; color: var(--yazi); }
  p { font-size: 0.88rem; color: var(--soluk); margin-bottom: 14px; line-height: 1.5; }
  .form-grup { margin-bottom: 12px; }
  label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--soluk); margin-bottom: 4px; }
  input, button { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--kenar); background: var(--bg); color: var(--yazi); font-size: 0.9rem; }
  .izgara { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  button { background: var(--vurgu); color: #0c0e16; font-weight: 700; border: none; cursor: pointer; transition: opacity 0.2s; margin-top: 6px; }
  button:hover { opacity: 0.9; }
  button.yesil { background: var(--vurgu2); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .durum-bar { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1f2937; border: 1px solid var(--vurgu); padding: 12px 24px; border-radius: 999px; font-size: 0.9rem; box-shadow: 0 10px 25px rgba(0,0,0,0.5); display: none; z-index: 100; }
  .durum-bar.aktif { display: flex; align-items: center; gap: 10px; }
  .spinner { width: 14px; height: 14px; border: 2px solid var(--vurgu); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .link-bar { margin-top: 20px; text-align: center; font-size: 0.85rem; }
  .link-bar a { color: var(--vurgu); text-decoration: none; margin: 0 8px; }
</style>
</head>
<body>
<div class="kutu">
  <header>
    <div>
      <h1>Sonsuz Okumalar - Kitap Yönetimi</h1>
      <span style="font-size:0.8rem;color:var(--soluk)">Kütüphane Yönetim & Güncelleme Konsolu</span>
    </div>
    <div class="sayac-kutu">Mevcut: <strong id="toplamKitap">{{ toplam_kitap }}</strong> kitap</div>
  </header>

  <!-- Yöntem 1: CSV Yükleme -->
  <div class="kart">
    <h2>📁 Yeni Storytel CSV Dosyası Yükle</h2>
    <p>Storytel'den aldığınız yeni veya güncel bir CSV dosyasını seçin. <strong>Önceki kitaplarınız kesinlikle silinmez</strong>; yeni kitaplar mevcut arşive eklenir, önceden var olanların ise dinleme süreleri ve tarihleri güncellenir.</p>
    <form id="csvForm">
      <div class="form-grup">
        <input type="file" id="csvDosya" accept=".csv" required>
      </div>
      <button type="submit">CSV'yi İçe Aktar ve Kitapları Otomatik Çek</button>
    </form>
  </div>

  <!-- Yöntem 2: Tek Kitap Ekleme -->
  <div class="kart">
    <h2>➕ Tek Bir Sesli Kitap Ekle</h2>
    <p>Listeye tek bir kitap eklemek için sadece <strong>Sesli Kitap ISBN</strong> kodunu girmeniz yeterlidir. Kapak, yazar, arka kapak yazısı, konu etiketleri ve yayınevi bilgileri Storytel & Kitapyurdu'ndan otomatik bulunur.</p>
    <form id="tekKitapForm">
      <div class="form-grup">
        <label>Sesli Kitap ISBN (Zorunlu)</label>
        <input type="text" id="tkIsbn" placeholder="Örn: 9789180909730" required>
      </div>
      <div class="izgara">
        <div class="form-grup">
          <label>Kitap Adı (İsteğe bağlı, boş bırakılırsa otomatik bulunur)</label>
          <input type="text" id="tkBaslik" placeholder="Örn: HınçAhınç">
        </div>
        <div class="form-grup">
          <label>Dinleme Süresi (Saat)</label>
          <input type="number" step="0.1" id="tkSure" placeholder="Örn: 3.5">
        </div>
      </div>
      <button type="submit">Kitabı Bul ve Arşive Ekle</button>
    </form>
  </div>

  <!-- Yöntem 3: GitHub'a Gönderme -->
  <div class="kart">
    <h2>🚀 Değişiklikleri GitHub Pages'e Yayınla</h2>
    <p>Yeni eklediğiniz kitapları tek tıkla GitHub deponuza gönderin. Böylece <code>sonsuztravma.github.io/Okunanlar</code> adresiniz otomatik olarak en güncel haliyle güncellenir.</p>
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
