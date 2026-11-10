'use strict';
const K = window.KITAPLIK || [];
const $ = s => document.querySelector(s);
const HARITA = {'ı':'i','ç':'c','ğ':'g','ö':'o','ş':'s','ü':'u','â':'a','î':'i','û':'u','é':'e','è':'e','ê':'e','ô':'o','ä':'a','ë':'e'};
// Karakter sayısını koruyan Türkçe duyarsız normalleştirme (vurgulama için)
const nrm = s => Array.from(s || '').map(c => { const l = c === 'İ' ? 'i' : c === 'I' ? 'ı' : c.toLowerCase(); return HARITA[l] || l; }).join('');
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const sure = sn => { const s = Math.round(sn / 60); const sa = Math.floor(s / 60), dk = s % 60; return sa ? `${sa} sa ${String(dk).padStart(2, '0')} dk` : `${dk} dk`; };
const tarih = t => t ? t.split('-').reverse().join('.') : '—';

K.forEach(k => {
  k._ara_baslik = nrm(k.baslik + ' ' + k.yazar + ' ' + (k.seri || '') + ' ' + (k.anlatici || ''));
  k._ara_ozet = nrm([k.ozet, k.tanitim, k.etiketler.join(' '), k.kategori, k.alt_kategori, k.yayinevi].join(' '));
});

const durum = { etiketler: new Set(), gorunum: 'grid', sekme: 'kitaplar', metrik: 'kitap' };
const dolsec = (id, degerler) => { const el = $(id); degerler.forEach(v => { const o = document.createElement('option'); o.value = o.textContent = v; el.appendChild(o); }); };
const say = (liste, alan, f = k => k[alan]) => { const m = new Map(); liste.forEach(k => [].concat(f(k)).filter(Boolean).forEach(v => m.set(v, (m.get(v) || 0) + 1))); return m; };
const sirali = m => [...m.keys()].sort((a, b) => a.localeCompare(b, 'tr'));

function hazirla() {
  const yillar = [...new Set(K.map(k => k.dinleme_yili))].sort((a, b) => b - a);
  dolsec('#fDinYil', yillar);
  const katSay = say(K, 'kategori');
  dolsec('#fKat', sirali(katSay));
  dolsec('#fYayin', sirali(say(K, 'yayinevi')));
  $('#yazarlar').innerHTML = sirali(say(K, 'yazar')).map(v => `<option value="${esc(v)}">`).join('');
  $('#anlaticilar').innerHTML = sirali(say(K, 'anlatici')).map(v => `<option value="${esc(v)}">`).join('');
  $('#mobilSirala').innerHTML = $('#sirala').innerHTML;

  // İstatistik hızlı yıl seçici
  $('#istatYilSec').innerHTML = `<button data-yil="" class="aktif">Tüm Yıllar</button>` +
    yillar.map(y => `<button data-yil="${y}">${y}</button>`).join('');

  // Hızlı kategori çipleri (üst bar)
  const katSirali = [...katSay.entries()].sort((a, b) => b[1] - a[1]);
  $('#hizliKat').innerHTML = `<button class="kat-cip aktif" data-kat="">Tümü <small>${K.length}</small></button>` +
    katSirali.map(([k, n]) => `<button class="kat-cip" data-kat="${esc(k)}">${esc(k)} <small>${n}</small></button>`).join('');

  guncelleAlt();
  const et = say(K, 'etiketler', k => k.etiketler);
  $('#etiketBulut').innerHTML = [...et.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'tr'))
    .map(([e, n]) => `<span class="et" data-e="${esc(e)}">${esc(e)}<small>${n}</small></span>`).join('');
}

function guncelleAlt() {
  const kat = $('#fKat').value, el = $('#fAlt'), eski = el.value;
  el.innerHTML = '<option value="">Tümü</option>';
  dolsec('#fAlt', sirali(say(K, 'alt_kategori', k => (!kat || k.kategori === kat) ? k.alt_kategori : null)));
  if ([...el.options].some(o => o.value === eski)) el.value = eski;
}

function aktifFiltreleriListele() {
  const f = [];
  const ekle = (etiket, sifirla) => f.push({ etiket, sifirla });
  if ($('#ara').value.trim()) ekle(`Arama: "${$('#ara').value.trim()}"`, () => $('#ara').value = '');
  if ($('#fDinYil').value) ekle(`Dinleme Yılı: ${$('#fDinYil').value}`, () => $('#fDinYil').value = '');
  if ($('#fKat').value) ekle(`Kategori: ${$('#fKat').value}`, () => { $('#fKat').value = ''; guncelleAlt(); });
  if ($('#fAlt').value) ekle(`Alt: ${$('#fAlt').value}`, () => $('#fAlt').value = '');
  if ($('#fYazar').value) ekle(`Yazar: ${$('#fYazar').value}`, () => $('#fYazar').value = '');
  if ($('#fAnlatici').value) ekle(`Ses: ${$('#fAnlatici').value}`, () => $('#fAnlatici').value = '');
  if ($('#fYayin').value) ekle(`Yayınevi: ${$('#fYayin').value}`, () => $('#fYayin').value = '');
  if ($('#yilMin').value || $('#yilMax').value) ekle(`Yayın Yılı: ${$('#yilMin').value || '…'}–${$('#yilMax').value || '…'}`, () => { $('#yilMin').value = ''; $('#yilMax').value = ''; });
  if ($('#sfMin').value || $('#sfMax').value) ekle(`Sayfa: ${$('#sfMin').value || '…'}–${$('#sfMax').value || '…'}`, () => { $('#sfMin').value = ''; $('#sfMax').value = ''; });
  if ($('#srMin').value || $('#srMax').value) ekle(`Süre: ${$('#srMin').value || '…'}–${$('#srMax').value || '…'} sa`, () => { $('#srMin').value = ''; $('#srMax').value = ''; });
  durum.etiketler.forEach(e => ekle(`#${e}`, () => durum.etiketler.delete(e)));
  return f;
}

function filtreKoşulu(k, q, ozetteDe, yilHaric = false) {
  const v = id => $(id).value, n = id => $(id).value === '' ? null : parseFloat($(id).value);
  const yz = nrm(v('#fYazar')), an = nrm(v('#fAnlatici'));
  const yMin = n('#yilMin'), yMax = n('#yilMax'), sMin = n('#sfMin'), sMax = n('#sfMax'), rMin = n('#srMin'), rMax = n('#srMax');
  if (q.length && !q.every(t => k._ara_baslik.includes(t) || (ozetteDe && k._ara_ozet.includes(t)))) return false;
  if (!yilHaric && v('#fDinYil') && String(k.dinleme_yili) !== v('#fDinYil')) return false;
  if (v('#fKat') && k.kategori !== v('#fKat')) return false;
  if (v('#fAlt') && k.alt_kategori !== v('#fAlt')) return false;
  if (v('#fYayin') && k.yayinevi !== v('#fYayin')) return false;
  if (yz && !nrm(k.yazar).includes(yz)) return false;
  if (an && !nrm(k.anlatici).includes(an)) return false;
  if (yMin !== null && !(k.yayin_yili >= yMin)) return false;
  if (yMax !== null && !(k.yayin_yili <= yMax)) return false;
  if (sMin !== null && !(k.sayfa >= sMin)) return false;
  if (sMax !== null && !(k.sayfa <= sMax)) return false;
  if (rMin !== null && k.sure_sn / 3600 < rMin) return false;
  if (rMax !== null && k.sure_sn / 3600 > rMax) return false;
  for (const e of durum.etiketler) if (!k.etiketler.includes(e)) return false;
  return true;
}

function filtrele() {
  const q = nrm($('#ara').value.trim()).split(/\s+/).filter(Boolean), ozetteDe = $('#araOzet').checked;
  const r = K.filter(k => filtreKoşulu(k, q, ozetteDe, false));
  const yilKarsilastirKume = K.filter(k => filtreKoşulu(k, q, ozetteDe, true));
  const [alan, yon] = $('#sirala').value.split('-'), c = yon === 'a' ? 1 : -1;
  r.sort((a, b) => {
    let x = a[alan], y = b[alan];
    if (x == null || x === '') return 1;
    if (y == null || y === '') return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'tr') : x - y) * c;
  });
  return { r, q, yilKarsilastirKume };
}

function vurgula(metin, q) {
  if (!q.length || !metin) return esc(metin);
  const nm = nrm(metin), aralik = [];
  q.forEach(t => { let i = 0; while ((i = nm.indexOf(t, i)) >= 0) { aralik.push([i, i + t.length]); i += t.length; } });
  aralik.sort((a, b) => a[0] - b[0]);
  const bir = []; aralik.forEach(a => { const s = bir[bir.length - 1]; if (s && a[0] <= s[1]) s[1] = Math.max(s[1], a[1]); else bir.push([...a]); });
  const ch = Array.from(metin); let out = '', p = 0;
  bir.forEach(([a, b]) => { out += esc(ch.slice(p, a).join('')) + '<mark>' + esc(ch.slice(a, b).join('')) + '</mark>'; p = b; });
  return out + esc(ch.slice(p).join(''));
}

function kartHtml(k, q) {
  const kapak = k.kapak_sesli || k.kapak_basili;
  const puan = k.puan ? `<span class="puan-rozet">★ ${k.puan.toFixed(1)}</span>` : '';
  return `<article class="kart" data-id="${k.isbn}">
    <div class="kapak">
      ${kapak ? `<img loading="lazy" src="kapaklar/${kapak}" alt="${esc(k.baslik)}">` : `<div class="yok">${esc(k.baslik)}</div>`}
      ${puan}
      <span class="sure-rozet">${sure(k.sure_sn)}</span>
    </div>
    <div class="bilgi">
      <span class="kat">${esc(k.kategori)}${k.alt_kategori ? ' › ' + esc(k.alt_kategori) : ''}</span>
      <b>${vurgula(k.baslik, q)}</b>
      <span class="yz">${vurgula(k.yazar || 'Yazar belirtilmemiş', q)}</span>
      <div class="alt-meta">
        <span>${k.sayfa ? (k.sayfa_tahmini ? '≈' : '') + k.sayfa + ' sf' : ''}</span>
        <span>${k.yayin_yili || ''}</span>
      </div>
    </div>
  </article>`;
}

let aktifFilSonuc = [];
function ciz() {
  const { r, q, yilKarsilastirKume } = filtrele();
  const toplam = r.reduce((s, k) => s + k.sure_sn, 0);
  $('#araTemizle').hidden = !$('#ara').value;
  $('#sayac').innerHTML = `<b>${r.length}</b> kitap · toplam <b>${Math.round(toplam / 3600).toLocaleString('tr-TR')}</b> saat`;
  $('#filtreUygula').textContent = `Sonuçları Göster (${r.length})`;

  // Etiket bulutu, hızlı kategori ve hızlı yıl butonları durumları
  document.querySelectorAll('.et').forEach(e => e.classList.toggle('secili', durum.etiketler.has(e.dataset.e)));
  const secKat = $('#fKat').value;
  document.querySelectorAll('#hizliKat .kat-cip').forEach(b => b.classList.toggle('aktif', b.dataset.kat === secKat));
  const secYil = $('#fDinYil').value;
  document.querySelectorAll('#istatYilSec button').forEach(b => b.classList.toggle('aktif', b.dataset.yil === secYil));

  // Aktif filtre çipleri ve mobil sayaç rozeti
  aktifFilSonuc = aktifFiltreleriListele();
  const rozet = $('#aktifFiltreSayi');
  rozet.textContent = aktifFilSonuc.length;
  rozet.hidden = aktifFilSonuc.length === 0;
  const cipEl = $('#aktifChipler');
  cipEl.hidden = aktifFilSonuc.length === 0;
  cipEl.innerHTML = aktifFilSonuc.map((f, i) => `<button class="filtre-cip" data-fi="${i}">${esc(f.etiket)} <span>✕</span></button>`).join('');

  if (durum.sekme === 'istatistik') {
    istatistikCiz(r, yilKarsilastirKume);
  } else {
    $('#liste').className = durum.gorunum === 'grid' ? 'grid' : 'liste';
    $('#liste').innerHTML = r.length ? r.map(k => kartHtml(k, q)).join('') : '<div class="bos-sonuc">Arama ve filtre ölçütlerinize uygun kitap bulunamadı.</div>';
  }
}

function modalAc(isbn) {
  const k = K.find(x => x.isbn === isbn);
  if (!k) return;
  const { q } = filtrele();
  const kapaklar = [['Sesli Kitap Kapağı', k.kapak_sesli], ['Basılı Kitap Kapağı', k.kapak_basili]].filter(c => c[1]);
  const kutu = (a, d) => d ? `<div class="meta-kutu"><small>${a}</small><strong>${esc(String(d))}</strong></div>` : '';
  $('#modalIcerik').innerHTML = `<div class="detay">
    <div class="sol">
      ${kapaklar.length ? `<img id="mk" src="kapaklar/${kapaklar[0][1]}" alt="${esc(k.baslik)}">` : ''}
      ${kapaklar.length > 1 ? `<div class="kapak-sec">${kapaklar.map((c, i) => `<button class="${i === 0 ? 'aktif' : ''}" data-k="${c[1]}">${c[0]}</button>`).join('')}</div>` : ''}
    </div>
    <div class="sag">
      <span class="ust-kat">${esc(k.kategori)}${k.alt_kategori ? ' › ' + esc(k.alt_kategori) : ''}</span>
      <h2>${vurgula(k.baslik, q)}</h2>
      <div class="yz">${vurgula(k.yazar, q)}</div>
      ${k.etiketler.length ? `<div class="detay-etiketler">${k.etiketler.map(e => `<span class="et" data-modal-e="${esc(e)}">#${esc(e)}</span>`).join('')}</div>` : ''}
      <div class="meta-izgara">
        ${kutu('Seslendiren', k.anlatici)}
        ${kutu('Dinleme Süresi', sure(k.sure_sn))}
        ${kutu('Sayfa Sayısı', k.sayfa ? (k.sayfa_tahmini ? `≈ ${k.sayfa} (tahminî)` : k.sayfa) : '')}
        ${kutu('Yayın Yılı', k.yayin_yili)}
        ${kutu('Basılı Yayınevi', k.yayinevi)}
        ${kutu('Sesli Yayıncı', k.sesli_yayinci)}
        ${kutu('Çevirmen', k.ceviren)}
        ${kutu('Seri', k.seri)}
        ${kutu('Dinleme Tarihi', `${tarih(k.baslangic)} – ${tarih(k.son_dinleme)}`)}
        ${kutu('Okur Puanı', k.puan ? `★ ${k.puan} / 5 (${k.puan_sayisi} oy)` : '')}
        ${kutu('ISBN (Sesli)', k.isbn)}
        ${kutu('ISBN (Basılı)', k.basili_isbn)}
      </div>
      ${k.ozet ? `<div class="metin-kutu"><h3>Arka Kapak / Sesli Kitap Tanıtımı</h3><p>${vurgula(k.ozet, q)}</p></div>` : ''}
      ${k.tanitim && k.tanitim !== k.ozet ? `<div class="metin-kutu"><h3>Basılı Kitap Yayınevi Tanıtımı</h3><p>${vurgula(k.tanitim, q)}</p></div>` : ''}
      ${!k.ozet && !k.tanitim ? '<p style="color:var(--soluk)">Bu kitap için tanıtım metni bulunamadı.</p>' : ''}
    </div>
  </div>`;
  $('#modal').hidden = false;
  document.body.classList.add('kilitli');
}

function modalKapat() {
  $('#modal').hidden = true;
  document.body.classList.remove('kilitli');
}

function mobilFiltreAc(ac) {
  $('#filtreler').classList.toggle('acik', ac);
  $('#perde').hidden = !ac;
  document.body.classList.toggle('kilitli', ac);
}

function sekmeDegistir(hedef) {
  durum.sekme = hedef;
  const ist = hedef === 'istatistik';
  document.querySelectorAll('.sekmeler button').forEach(x => x.classList.toggle('aktif', x.dataset.sek === hedef));
  $('#sekKitaplar').hidden = ist;
  $('#kitapAracSag').hidden = ist;
  $('#sekIstatistik').hidden = !ist;
  $('#istatAracSag').hidden = !ist;
  ciz();
}

function istatistikCiz(liste, yilKume) {
  if (!liste.length) {
    $('#sekIstatistik').innerHTML = '<div class="bos-sonuc">Seçili filtrelere uygun istatistik verisi bulunamadı.</div>';
    return;
  }
  const m = durum.metrik; // 'kitap' | 'saat' | 'sayfa'
  const degerVer = k => m === 'saat' ? (k.sure_sn / 3600) : m === 'sayfa' ? (k.sayfa || 0) : 1;
  const bicimle = v => m === 'saat' ? `${Math.round(v * 10) / 10} sa` : m === 'sayfa' ? `${Math.round(v).toLocaleString('tr-TR')} sf` : `${v}`;
  const metrikEtiket = m === 'saat' ? 'Dinleme Süresi' : m === 'sayfa' ? 'Sayfa Sayısı' : 'Kitap Sayısı';

  const topla = (getter, kume = liste) => {
    const map = new Map();
    kume.forEach(k => {
      const w = degerVer(k);
      [].concat(getter(k)).filter(Boolean).forEach(anahtar => map.set(anahtar, (map.get(anahtar) || 0) + w));
    });
    return map;
  };
  const top = (map, n = 15) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
  const cubuk = (diz, tur = '') => {
    if (!diz.length) return '<small style="color:var(--soluk)">Veri yok</small>';
    const mx = Math.max(...diz.map(l => l[1]), 0.01);
    return diz.map(([a, n]) => `<div class="cubuk ${tur ? 'tiklanir' : ''}" ${tur ? `data-tur="${tur}" data-deger="${esc(String(a))}" title="Filtrelemek için tıklayın: ${esc(String(a))}"` : ''}>
      <span class="ad">${esc(String(a))}</span>
      <span class="c"><i style="width:${Math.min(100, (n / mx) * 100)}%"></i></span>
      <span class="n">${bicimle(n)}</span>
    </div>`).join('');
  };

  // Özet sayılar
  const toplamSn = liste.reduce((s, k) => s + k.sure_sn, 0);
  const toplamSayfa = liste.reduce((s, k) => s + (k.sayfa || 0), 0);
  const puanlilar = liste.filter(k => k.puan);
  const ortPuan = puanlilar.length ? (puanlilar.reduce((s, k) => s + k.puan, 0) / puanlilar.length).toFixed(2) : '—';
  const payYuzde = Math.round((liste.length / K.length) * 100);

  // Yıllara göre karşılaştırma kartları (diğer filtreler sabitken 2025 vs 2026)
  const yillar = [...new Set(K.map(k => k.dinleme_yili))].sort((a, b) => b - a);
  const secYil = $('#fDinYil').value;
  const yilKartlari = yillar.map(y => {
    const yk = yilKume.filter(k => k.dinleme_yili === y);
    const ySn = yk.reduce((s, k) => s + k.sure_sn, 0);
    const ySf = yk.reduce((s, k) => s + (k.sayfa || 0), 0);
    const secili = String(y) === secYil;
    return `<div class="yil-kart ${secili ? 'secili' : ''}" data-yil-kart="${y}" title="${y} yılını filtrelemek için tıklayın">
      <div class="yil-kart-ust"><strong>${y} Yılı</strong><span>${secili ? '✓ Seçili filtre' : 'Tıkla & filtrele'}</span></div>
      <div class="yil-metrikler">
        <div><b>${yk.length}</b>Kitap</div>
        <div><b>${Math.round(ySn / 3600).toLocaleString('tr-TR')} sa</b>Dinleme</div>
        <div><b>${ySf.toLocaleString('tr-TR')}</b>Sayfa</div>
      </div>
    </div>`;
  }).join('');

  // Süre dağılımı ve sayfa dağılımı
  const sureKat = k => {
    const sa = k.sure_sn / 3600;
    return sa < 2 ? '0 – 2 saat (Kısa)' : sa < 5 ? '2 – 5 saat' : sa < 8 ? '5 – 8 saat' : sa < 12 ? '8 – 12 saat' : '12+ saat (Uzun)';
  };
  const sureSira = ['0 – 2 saat (Kısa)', '2 – 5 saat', '5 – 8 saat', '8 – 12 saat', '12+ saat (Uzun)'];
  const sureMap = topla(sureKat);
  const sureDiz = sureSira.filter(x => sureMap.has(x)).map(x => [x, sureMap.get(x)]);

  const sayfaKat = k => {
    const sf = k.sayfa || 0;
    return sf < 150 ? '1 – 149 sayfa' : sf < 300 ? '150 – 299 sayfa' : sf < 500 ? '300 – 499 sayfa' : '500+ sayfa';
  };
  const sayfaSira = ['1 – 149 sayfa', '150 – 299 sayfa', '300 – 499 sayfa', '500+ sayfa'];
  const sayfaMap = topla(sayfaKat);
  const sayfaDiz = sayfaSira.filter(x => sayfaMap.has(x)).map(x => [x, sayfaMap.get(x)]);

  // Aylık dağılım ve Yayın on yılı
  const ayMap = topla(k => (k.baslangic || '').slice(0, 7));
  const yyMap = topla(k => k.yayin_yili ? Math.floor(k.yayin_yili / 10) * 10 + '\'lar' : null);

  // En uzun 6 kitap ve En yüksek puanlı 6 kitap
  const enUzun = [...liste].sort((a, b) => b.sure_sn - a.sure_sn).slice(0, 6);
  const enPuanli = [...liste].filter(k => k.puan && k.puan_sayisi >= 5).sort((a, b) => b.puan - a.puan || b.puan_sayisi - a.puan_sayisi).slice(0, 6);

  const filtreBilgi = aktifFilSonuc.length ? `<div class="istat-bilgi-cubuk">
    <span>Seçili filtrelere göre <b>${liste.length} kitap</b> (${payYuzde}%) üzerinden istatistikler gösteriliyor. Grafik çubuklarına tıklayarak filtreyi daraltabilirsiniz.</span>
    <button id="istatKitaplariGor">Bu ${liste.length} Kitabı Listele →</button>
  </div>` : `<div class="istat-bilgi-cubuk">
    <span>💡 İpucu: Sol panelden, üstteki kategori/yıl düğmelerinden veya <b>doğrudan grafik çubuklarına tıklayarak</b> istatistikleri istediğiniz kategori, yıl, yazar veya etikete göre filtreleyebilirsiniz.</span>
  </div>`;

  $('#sekIstatistik').innerHTML = `
    ${filtreBilgi}
    <div class="yil-izgara">${yilKartlari}</div>
    <div class="sayilar">
      <div class="sayi-kart"><b>${liste.length}</b><span>Dinlenen Kitap</span><small>Arşivin %${payYuzde}'i</small></div>
      <div class="sayi-kart"><b>${Math.round(toplamSn / 3600).toLocaleString('tr-TR')} sa</b><span>Toplam Dinleme</span><small>≈ ${(toplamSn / 86400).toFixed(1)} tam gün</small></div>
      <div class="sayi-kart"><b>${toplamSayfa.toLocaleString('tr-TR')}</b><span>Toplam Sayfa</span><small>Ort. ${Math.round(toplamSayfa / liste.length)} sf/kitap</small></div>
      <div class="sayi-kart"><b>${new Set(liste.map(k => k.yazar).filter(Boolean)).size}</b><span>Farklı Yazar</span><small>${new Set(liste.map(k => k.yayinevi).filter(Boolean)).size} yayınevi</small></div>
      <div class="sayi-kart"><b>${new Set(liste.map(k => k.anlatici).filter(Boolean)).size}</b><span>Farklı Seslendiren</span><small>Ort. ${(toplamSn / liste.length / 3600).toFixed(1)} sa/kitap</small></div>
      <div class="sayi-kart"><b>★ ${ortPuan}</b><span>Ortalama Okur Puanı</span><small>${puanlilar.length} puanlı kitap</small></div>
    </div>

    <div class="istat">
      <div class="kutu">
        <div class="kutu-ust"><h3>Ana Kategoriler</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.kategori), 20), 'kategori')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Alt Kategoriler</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.alt_kategori), 15), 'alt_kategori')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>En Çok Dinlenen Yazarlar</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.yazar), 15), 'yazar')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>En Çok Dinlenen Seslendirenler</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.anlatici), 15), 'anlatici')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Basılı Yayınevleri</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.yayinevi), 15), 'yayinevi')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Konu &amp; Tema Etiketleri</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(top(topla(k => k.etiketler), 18), 'etiket')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Aylara Göre Dinleme Dağılımı</h3><small>${metrikEtiket}</small></div>
        ${cubuk([...ayMap.entries()].sort())}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Dinleme Süresi Dağılımı</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(sureDiz, 'sure_aralik')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Sayfa Sayısı Dağılımı</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk(sayfaDiz, 'sayfa_aralik')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Yayınlandığı Dönem (On Yıllar)</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
        ${cubuk([...yyMap.entries()].sort(), 'onyil')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>En Uzun Dinlemeler</h3><small>Detay için tıklayın</small></div>
        ${enUzun.map(k => `<div class="mini-satir" data-kitap="${k.isbn}">
          <div style="min-width:0"><b>${esc(k.baslik)}</b><small>${esc(k.yazar)} · ${esc(k.kategori)}</small></div>
          <span class="mini-sag">${sure(k.sure_sn)}</span>
        </div>`).join('')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>En Yüksek Puanlılar</h3><small>Detay için tıklayın</small></div>
        ${enPuanli.map(k => `<div class="mini-satir" data-kitap="${k.isbn}">
          <div style="min-width:0"><b>${esc(k.baslik)}</b><small>${esc(k.yazar)} (${k.puan_sayisi} oy)</small></div>
          <span class="mini-sag">★ ${k.puan.toFixed(2)}</span>
        </div>`).join('')}
      </div>
    </div>`;
}

// Olay Bağlantıları
['#ara', '#araOzet', '#fDinYil', '#fAlt', '#fYayin', '#fYazar', '#fAnlatici', '#yilMin', '#yilMax', '#sfMin', '#sfMax', '#srMin', '#srMax']
  .forEach(id => $(id).addEventListener('input', ciz));

$('#sirala').addEventListener('change', () => { $('#mobilSirala').value = $('#sirala').value; ciz(); });
$('#mobilSirala').addEventListener('change', () => { $('#sirala').value = $('#mobilSirala').value; ciz(); });

$('#araTemizle').onclick = () => { $('#ara').value = ''; $('#ara').focus(); ciz(); };

$('#fKat').addEventListener('change', () => { guncelleAlt(); ciz(); });
$('#hizliKat').addEventListener('click', e => {
  const b = e.target.closest('.kat-cip');
  if (!b) return;
  $('#fKat').value = b.dataset.kat;
  guncelleAlt();
  ciz();
});

$('#istatYilSec').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  $('#fDinYil').value = b.dataset.yil;
  ciz();
});

$('#istatMetrikSec').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  durum.metrik = b.dataset.m;
  document.querySelectorAll('#istatMetrikSec button').forEach(x => x.classList.toggle('aktif', x === b));
  ciz();
});

$('#sekIstatistik').addEventListener('click', e => {
  if (e.target.id === 'istatKitaplariGor') { sekmeDegistir('kitaplar'); return; }
  const yk = e.target.closest('[data-yil-kart]');
  if (yk) {
    const y = yk.dataset.yilKart;
    $('#fDinYil').value = $('#fDinYil').value === y ? '' : y;
    ciz();
    return;
  }
  const mk = e.target.closest('[data-kitap]');
  if (mk) { modalAc(mk.dataset.kitap); return; }
  const cb = e.target.closest('.cubuk.tiklanir');
  if (!cb) return;
  const { tur, deger } = cb.dataset;
  if (tur === 'kategori') { $('#fKat').value = $('#fKat').value === deger ? '' : deger; guncelleAlt(); }
  else if (tur === 'alt_kategori') { $('#fAlt').value = $('#fAlt').value === deger ? '' : deger; }
  else if (tur === 'yazar') { $('#fYazar').value = $('#fYazar').value === deger ? '' : deger; }
  else if (tur === 'anlatici') { $('#fAnlatici').value = $('#fAnlatici').value === deger ? '' : deger; }
  else if (tur === 'yayinevi') { $('#fYayin').value = $('#fYayin').value === deger ? '' : deger; }
  else if (tur === 'etiket') { durum.etiketler.has(deger) ? durum.etiketler.delete(deger) : durum.etiketler.add(deger); }
  else if (tur === 'onyil') {
    const y = parseInt(deger, 10);
    if ($('#yilMin').value === String(y)) { $('#yilMin').value = ''; $('#yilMax').value = ''; }
    else { $('#yilMin').value = y; $('#yilMax').value = y + 9; }
  } else if (tur === 'sure_aralik') {
    const harita = {'0 – 2 saat (Kısa)':[0,2],'2 – 5 saat':[2,5],'5 – 8 saat':[5,8],'8 – 12 saat':[8,12],'12+ saat (Uzun)':[12,'']};
    const [mn, mx] = harita[deger] || ['', ''];
    $('#srMin').value = mn; $('#srMax').value = mx;
  } else if (tur === 'sayfa_aralik') {
    const harita = {'1 – 149 sayfa':[1,149],'150 – 299 sayfa':[150,299],'300 – 499 sayfa':[300,499],'500+ sayfa':[500,'']};
    const [mn, mx] = harita[deger] || ['', ''];
    $('#sfMin').value = mn; $('#sfMax').value = mx;
  }
  ciz();
});

$('#aktifChipler').addEventListener('click', e => {
  const b = e.target.closest('.filtre-cip');
  if (!b) return;
  const f = aktifFilSonuc[Number(b.dataset.fi)];
  if (f) { f.sifirla(); ciz(); }
});

$('#etiketBulut').addEventListener('click', e => {
  const t = e.target.closest('.et');
  if (!t) return;
  const v = t.dataset.e;
  durum.etiketler.has(v) ? durum.etiketler.delete(v) : durum.etiketler.add(v);
  ciz();
});

$('#liste').addEventListener('click', e => { const k = e.target.closest('.kart'); if (k) modalAc(k.dataset.id); });
$('#kapat').onclick = modalKapat;
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') modalKapat(); });

$('#mobilFiltreBtn').onclick = () => mobilFiltreAc(true);
$('#filtreKapat').onclick = () => mobilFiltreAc(false);
$('#filtreUygula').onclick = () => mobilFiltreAc(false);
$('#perde').onclick = () => mobilFiltreAc(false);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (!$('#modal').hidden) modalKapat();
    else mobilFiltreAc(false);
  }
});

$('#modalIcerik').addEventListener('click', e => {
  const b = e.target.closest('[data-k]');
  if (b) {
    $('#mk').src = 'kapaklar/' + b.dataset.k;
    b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('aktif', x === b));
  }
  const t = e.target.closest('[data-modal-e]');
  if (t) { durum.etiketler.add(t.dataset.modalE); modalKapat(); ciz(); }
});

$('#temizle').onclick = () => {
  document.querySelectorAll('#filtreler input, #filtreler select').forEach(x => { if (x.id !== 'sirala') x.value = ''; });
  $('#ara').value = '';
  durum.etiketler.clear();
  guncelleAlt();
  ciz();
};

$('#gGrid').onclick = () => { durum.gorunum = 'grid'; $('#gGrid').classList.add('aktif'); $('#gListe').classList.remove('aktif'); ciz(); };
$('#gListe').onclick = () => { durum.gorunum = 'liste'; $('#gListe').classList.add('aktif'); $('#gGrid').classList.remove('aktif'); ciz(); };

document.querySelectorAll('.sekmeler button').forEach(b => b.onclick = () => sekmeDegistir(b.dataset.sek));

hazirla();
ciz();
