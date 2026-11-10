'use strict';
const K = window.KITAPLIK || [];
const $ = s => document.querySelector(s);
const HARITA = {'ı':'i','ç':'c','ğ':'g','ö':'o','ş':'s','ü':'u','â':'a','î':'i','û':'u','é':'e','è':'e','ê':'e','ô':'o','ä':'a','ë':'e'};
// Karakter sayısını koruyan Türkçe duyarsız normalleştirme (vurgulama için)
const nrm = s => Array.from(s || '').map(c => { const l = c === 'İ' ? 'i' : c === 'I' ? 'ı' : c.toLowerCase(); return HARITA[l] || l; }).join('');
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const sure = sn => { if (!sn || sn <= 0) return 'Belirtilmemiş'; const s = Math.round(sn / 60); const sa = Math.floor(s / 60), dk = s % 60; return sa ? `${sa} sa ${String(dk).padStart(2, '0')} dk` : `${dk} dk`; };
const tarih = t => t ? t.split('-').reverse().join('.') : '—';

K.forEach(k => {
  k.etiketler = k.etiketler || [];
  k.akademik = Boolean(k.akademik || k.etiketler.includes('Akademik'));
  k._ara_baslik = nrm([k.baslik, k.orijinal_baslik, k.yazar, k.seri, k.anlatici].filter(Boolean).join(' '));
  k._ara_ozet = nrm([k.ozet, k.tanitim, k.orijinal_baslik, k.etiketler.join(' '), k.kategori, k.alt_kategori, k.yayinevi].filter(Boolean).join(' '));
});

const durum = {
  etiketler: new Set(),
  gorunum: 'grid',
  sekme: 'kitaplar',       // 'kitaplar' | 'istatistik' | 'akademik'
  istatSekme: 'genel',     // 'genel' | 'akademik'
  metrik: 'kitap',
  akAra: '',
  akDil: '',
  akKonu: '',
  akSirala: 'baslik-a'
};

const dolsec = (id, degerler) => { const el = $(id); degerler.forEach(v => { const o = document.createElement('option'); o.value = o.textContent = v; el.appendChild(o); }); };
const say = (liste, alan, f = k => k[alan]) => { const m = new Map(); liste.forEach(k => [].concat(f(k)).filter(Boolean).forEach(v => m.set(v, (m.get(v) || 0) + 1))); return m; };
const sirali = m => [...m.keys()].sort((a, b) => a.localeCompare(b, 'tr'));

function hazirla() {
  const yillar = [...new Set(K.map(k => k.dinleme_yili).filter(Boolean))].sort((a, b) => b - a);
  dolsec('#fDinYil', yillar);
  if (K.some(k => !k.dinleme_yili)) {
    const o = document.createElement('option');
    o.value = 'belirsiz';
    o.textContent = 'Tarihi Belirsiz (Psikoloji / Basılı)';
    $('#fDinYil').appendChild(o);
  }
  const katSay = say(K, 'kategori');
  dolsec('#fKat', sirali(katSay));
  dolsec('#fYayin', sirali(say(K, 'yayinevi')));
  $('#yazarlar').innerHTML = sirali(say(K, 'yazar')).map(v => `<option value="${esc(v)}">`).join('');
  $('#anlaticilar').innerHTML = sirali(say(K, 'anlatici')).map(v => `<option value="${esc(v)}">`).join('');
  $('#mobilSirala').innerHTML = $('#sirala').innerHTML;

  // İstatistik hızlı yıl seçici
  $('#istatYilSec').innerHTML = `<button data-yil="" class="aktif">Tüm Yıllar</button>` +
    yillar.map(y => `<button data-yil="${y}">${y}</button>`).join('');

  // Hızlı kategori çipleri (üst bar) + Psikoloji Kitapları ve Akademik özel kısayolları
  const pskSayi = K.filter(k => k.alt_kategori === 'Psikoloji Kitapları').length;
  const akSayi = K.filter(k => k.akademik).length;
  const katSirali = [...katSay.entries()].sort((a, b) => b[1] - a[1]);
  $('#hizliKat').innerHTML =
    `<button class="kat-cip aktif" data-kat="">Tümü <small>${K.length}</small></button>` +
    (pskSayi ? `<button class="kat-cip ozel-psk" data-ozel="psk">🧠 Psikoloji Kitapları <small>${pskSayi}</small></button>` : '') +
    (akSayi ? `<button class="kat-cip ozel-ak" data-ozel="ak">🎓 Akademik <small>${akSayi}</small></button>` : '') +
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
  if ($('#fDinYil').value) ekle(`Dinleme Yılı: ${$('#fDinYil').value === 'belirsiz' ? 'Tarihi Belirsiz' : $('#fDinYil').value}`, () => $('#fDinYil').value = '');
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
  if (!yilHaric && v('#fDinYil')) {
    if (v('#fDinYil') === 'belirsiz') { if (k.dinleme_yili) return false; }
    else if (String(k.dinleme_yili) !== v('#fDinYil')) return false;
  }
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
  const puan = k.puan ? `<span class="puan-rozet">★ ${Number(k.puan).toFixed(1)}</span>` : '';
  const altRozet = k.sure_sn > 0
    ? `<span class="sure-rozet">${sure(k.sure_sn)}</span>`
    : `<span class="sure-rozet ${k.akademik ? 'ak-rozet' : 'psk-rozet'}">${k.akademik ? '🎓 Akademik' : '🧠 Psikoloji'}</span>`;
  const dilEtiket = k.dil === 'en' ? `<span class="dil-etiket" title="Türkçe çeviri özetli yabancı eser">Çeviri Özet</span>` : '';
  return `<article class="kart" data-id="${k.isbn}">
    <div class="kapak">
      ${kapak ? `<img loading="lazy" src="kapaklar/${kapak}" alt="${esc(k.baslik)}">` : `<div class="yok">${esc(k.baslik)}</div>`}
      ${puan}
      ${altRozet}
    </div>
    <div class="bilgi">
      <span class="kat">${esc(k.kategori)}${k.alt_kategori ? ' › ' + esc(k.alt_kategori) : ''}${dilEtiket}</span>
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
  const toplam = r.reduce((s, k) => s + (k.sure_sn || 0), 0);
  const akSay = r.filter(k => k.akademik).length;
  $('#araTemizle').hidden = !$('#ara').value;
  $('#sayac').innerHTML = `<b>${r.length}</b> kitap · toplam <b>${Math.round(toplam / 3600).toLocaleString('tr-TR')}</b> saat` +
    (akSay ? ` · <b>${akSay}</b> akademik` : '');
  $('#filtreUygula').textContent = `Sonuçları Göster (${r.length})`;

  // Etiket bulutu, hızlı kategori ve hızlı yıl butonları durumları
  document.querySelectorAll('.et').forEach(e => e.classList.toggle('secili', durum.etiketler.has(e.dataset.e)));
  const secKat = $('#fKat').value;
  const secAlt = $('#fAlt').value;
  document.querySelectorAll('#hizliKat .kat-cip').forEach(b => {
    if (b.dataset.ozel === 'psk') {
      b.classList.toggle('aktif', secAlt === 'Psikoloji Kitapları');
    } else if (b.dataset.ozel === 'ak') {
      b.classList.toggle('aktif', durum.etiketler.has('Akademik'));
    } else {
      b.classList.toggle('aktif', b.dataset.kat === secKat && secAlt !== 'Psikoloji Kitapları' && !durum.etiketler.has('Akademik'));
    }
  });
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

  if (durum.sekme === 'istatistik' || durum.sekme === 'akademik') {
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
  const kapaklar = [['Sesli Kitap Kapağı', k.kapak_sesli], ['Kitap Kapağı', k.kapak_basili]].filter(c => c[1]);
  const kutu = (a, d) => d ? `<div class="meta-kutu"><small>${a}</small><strong>${esc(String(d))}</strong></div>` : '';
  const yabanciMi = k.dil === 'en';
  const ozetBaslik = yabanciMi ? '🇹🇷 Türkçe Özet & Tanıtım (Çeviri)' : 'Kitap Özeti & Arka Kapak Tanıtımı';
  const tanitimBaslik = yabanciMi ? '🇬🇧 Orijinal Tanıtım Yazısı (Amazon / Goodreads)' : 'Basılı Kitap Yayınevi Tanıtımı';
  const temizOzet = (k.ozet || '').replace(/^📌\s*\[?Türkçe Başlık Çevirisi:[^\n]*\n+/i, '').trim();

  $('#modalIcerik').innerHTML = `<div class="detay">
    <div class="sol">
      ${kapaklar.length ? `<img id="mk" src="kapaklar/${kapaklar[0][1]}" alt="${esc(k.baslik)}">` : `<div class="yok" style="min-height:260px;display:flex;align-items:center;justify-content:center;padding:16px;text-align:center;background:var(--panel2);border-radius:12px">${esc(k.baslik)}</div>`}
      ${kapaklar.length > 1 ? `<div class="kapak-sec">${kapaklar.map((c, i) => `<button class="${i === 0 ? 'aktif' : ''}" data-k="${c[1]}">${c[0]}</button>`).join('')}</div>` : ''}
    </div>
    <div class="sag">
      <span class="ust-kat">${esc(k.kategori)}${k.alt_kategori ? ' › ' + esc(k.alt_kategori) : ''}${k.akademik ? ' · 🎓 Akademik Eser' : ''}</span>
      <h2>${vurgula(k.baslik, q)}</h2>
      ${k.orijinal_baslik ? `<div class="alt-baslik-ceviri">🇹🇷 Türkçe Başlık Çevirisi: <strong>${vurgula(k.orijinal_baslik, q)}</strong></div>` : ''}
      <div class="yz">${vurgula(k.yazar || 'Yazar belirtilmemiş', q)}</div>
      ${k.etiketler.length ? `<div class="detay-etiketler">${k.etiketler.map(e => `<span class="et" data-modal-e="${esc(e)}">#${esc(e)}</span>`).join('')}</div>` : ''}
      <div class="meta-izgara">
        ${kutu('Seslendiren', k.anlatici)}
        ${k.sure_sn > 0 ? kutu('Dinleme Süresi', sure(k.sure_sn)) : kutu('Okuma / Süre', 'Süre belirtilmemiş')}
        ${kutu('Sayfa Sayısı', k.sayfa ? (k.sayfa_tahmini ? `≈ ${k.sayfa} (tahminî)` : k.sayfa) : '')}
        ${kutu('Yayın Yılı', k.yayin_yili)}
        ${kutu('Yayınevi', k.yayinevi)}
        ${kutu('Sesli Yayıncı', k.sesli_yayinci)}
        ${kutu('Çevirmen', k.ceviren)}
        ${kutu('Seri', k.seri)}
        ${k.baslangic ? kutu('Dinleme Tarihi', `${tarih(k.baslangic)} – ${tarih(k.son_dinleme)}`) : ''}
        ${kutu('Okur Puanı', k.puan ? `★ ${Number(k.puan).toFixed(2)} / 5 (${k.puan_sayisi || 0} oy)` : '')}
        ${kutu('Kayıt Kodu', k.isbn)}
        ${kutu('ISBN (Basılı)', k.basili_isbn)}
      </div>
      ${temizOzet ? `<div class="metin-kutu"><h3>${ozetBaslik}</h3><p>${vurgula(temizOzet, q)}</p></div>` : ''}
      ${k.tanitim && k.tanitim !== temizOzet && k.tanitim !== k.ozet ? `<div class="metin-kutu"><h3>${tanitimBaslik}</h3><p>${vurgula(k.tanitim, q)}</p></div>` : ''}
      ${!temizOzet && !k.tanitim ? '<p style="color:var(--soluk)">Bu kitap için tanıtım metni bulunamadı.</p>' : ''}
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
  if (hedef === 'akademik') {
    durum.istatSekme = 'akademik';
  } else if (hedef === 'istatistik' && durum.istatSekme === 'akademik') {
    durum.istatSekme = 'genel';
  }
  const istGorunum = hedef === 'istatistik' || hedef === 'akademik';
  document.querySelectorAll('.sekmeler button').forEach(x => x.classList.toggle('aktif', x.dataset.sek === hedef));
  $('#sekKitaplar').hidden = istGorunum;
  $('#kitapAracSag').hidden = istGorunum;
  $('#sekIstatistik').hidden = !istGorunum;
  $('#istatAracSag').hidden = !(istGorunum && durum.istatSekme === 'genel');
  ciz();
}

function akademikAlanBelirle(k) {
  const m = nrm([k.baslik, k.orijinal_baslik, k.ozet, k.tanitim].join(' '));
  const alanlar = [];
  if (/dissociat|dissosiy|bolunm|kimlik bozuk/.test(m)) alanlar.push('Dissosiyasyon & Kimlik');
  if (/psychoanaly|psikanali|freud|jung|lacan|object relation|nesne iliski|transference|aktarim/.test(m)) alanlar.push('Psikanaliz & Psikodinamik');
  if (/neuro|noro|brain|beyin|polyvagal|polivagal|autonomic|epigenet|kortizol/.test(m)) alanlar.push('Nörobiyoloji & Beyin');
  if (/attach|baglanma|childhood|cocukluk|developmental|gelisimsel|anne|ebeveyn/.test(m)) alanlar.push('Bağlanma & Gelişimsel Travma');
  if (/somatic|somatik|body|beden|emdr|trimb|sensorimotor|hareket/.test(m)) alanlar.push('Beden Odaklı & EMDR / Somatik');
  if (/intergenerational|transgenerational|kusaklararasi|nesiller|holocaust|soykirim|collective|kolektif/.test(m)) alanlar.push('Kuşaklararası & Kolektif Travma');
  if (/psychiatr|psikiyatr|phenomenol|fenomenolo|borderline|bipolar|schizophren|sizofren|depres|anhedoni/.test(m)) alanlar.push('Klinik Psikiyatri & Patoloji');
  if (!alanlar.length) alanlar.push('Travma Psikolojisi & Psikoterapi');
  return alanlar;
}

function akademikIstatistikCiz(ustBarHtml) {
  const akTum = K.filter(k => k.akademik);
  const trSay = akTum.filter(k => k.dil !== 'en').length;
  const enSay = akTum.filter(k => k.dil === 'en').length;
  const topSayfa = akTum.reduce((s, k) => s + (k.sayfa || 0), 0);
  const sayfalilar = akTum.filter(k => k.sayfa > 0);
  const ortSayfa = sayfalilar.length ? Math.round(topSayfa / sayfalilar.length) : 0;
  const puanlilar = akTum.filter(k => k.puan);
  const ortPuan = puanlilar.length ? (puanlilar.reduce((s, k) => s + Number(k.puan), 0) / puanlilar.length).toFixed(2) : '—';
  const yazarSay = new Set(akTum.map(k => k.yazar).filter(Boolean)).size;
  const yayinSay = new Set(akTum.map(k => k.yayinevi).filter(Boolean)).size;

  const toplaAk = getter => {
    const map = new Map();
    akTum.forEach(k => {
      [].concat(getter(k)).filter(Boolean).forEach(a => map.set(a, (map.get(a) || 0) + 1));
    });
    return map;
  };
  const top = (map, n = 12) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
  const cubukAk = (diz, akTur = '') => {
    if (!diz.length) return '<small style="color:var(--soluk)">Veri yok</small>';
    const mx = Math.max(...diz.map(l => l[1]), 1);
    return diz.map(([a, n]) => `<div class="cubuk ${akTur ? 'tiklanir' : ''}" ${akTur ? `data-ak-tur="${akTur}" data-ak-deger="${esc(String(a))}" title="Akademik katalogda filtrelemek için tıklayın"` : ''}>
      <span class="ad">${esc(String(a))}</span>
      <span class="c"><i style="width:${Math.min(100, (n / mx) * 100)}%"></i></span>
      <span class="n">${n} kitap</span>
    </div>`).join('');
  };

  const yyMap = toplaAk(k => k.yayin_yili ? Math.floor(k.yayin_yili / 10) * 10 + '\'lar' : null);
  const sayfaKat = k => {
    const sf = k.sayfa || 0;
    if (!sf) return null;
    return sf < 150 ? '1 – 149 sayfa' : sf < 300 ? '150 – 299 sayfa' : sf < 500 ? '300 – 499 sayfa' : '500+ sayfa';
  };
  const sayfaMap = toplaAk(sayfaKat);
  const sayfaSira = ['1 – 149 sayfa', '150 – 299 sayfa', '300 – 499 sayfa', '500+ sayfa'];
  const sayfaDiz = sayfaSira.filter(x => sayfaMap.has(x)).map(x => [x, sayfaMap.get(x)]);
  const enPuanliAk = [...akTum].filter(k => k.puan).sort((a, b) => b.puan - a.puan || (b.puan_sayisi || 0) - (a.puan_sayisi || 0)).slice(0, 6);

  // Akademik Katalog filtreleme
  const qAk = nrm(durum.akAra.trim()).split(/\s+/).filter(Boolean);
  const akFil = akTum.filter(k => {
    if (durum.akDil === 'en' && k.dil !== 'en') return false;
    if (durum.akDil === 'tr' && k.dil === 'en') return false;
    if (durum.akKonu && !akademikAlanBelirle(k).includes(durum.akKonu)) return false;
    if (qAk.length && !qAk.every(t => k._ara_baslik.includes(t) || k._ara_ozet.includes(t))) return false;
    return true;
  });

  const [sAlan, sYon] = durum.akSirala.split('-'), sc = sYon === 'a' ? 1 : -1;
  akFil.sort((a, b) => {
    let x = a[sAlan], y = b[sAlan];
    if (x == null || x === '') return 1;
    if (y == null || y === '') return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'tr') : x - y) * sc;
  });

  const tumKlinikAlanlar = [...toplaAk(akademikAlanBelirle).entries()].sort((a, b) => b[1] - a[1]);

  $('#sekIstatistik').innerHTML = `
    ${ustBarHtml}
    <div class="istat-bilgi-cubuk">
      <span>🎓 <b>Akademik Psikoloji, Psikanaliz, Psikiyatri ve Travma Kitapları Koleksiyonu:</b> Toplam <b>${akTum.length} akademik eser</b> (Türkçe ve İngilizce/yabancı dilde yayımlanmış, Türkçe çeviri özetli klinik &amp; kuramsal kitaplar) burada yer alır. Grafiklere tıklayarak veya aşağıdaki katalogdan arayarak inceleyebilirsiniz.</span>
      <button id="akTumunuKitapliktaGor">Kitaplık Sekmesinde Filtrele →</button>
    </div>

    <div class="sayilar">
      <div class="sayi-kart"><b>${akTum.length}</b><span>Akademik Kitap</span><small>Psikoloji &amp; Travma Koleksiyonu</small></div>
      <div class="sayi-kart"><b>${enSay}</b><span>Yabancı Dil (Çeviri Özet)</span><small>Amazon/Goodreads kaynaklı</small></div>
      <div class="sayi-kart"><b>${trSay}</b><span>Türkçe Akademik Eser</span><small>Telif &amp; Türkçe baskılar</small></div>
      <div class="sayi-kart"><b>${topSayfa.toLocaleString('tr-TR')}</b><span>Toplam Sayfa</span><small>Ort. ${ortSayfa} sf/kitap</small></div>
      <div class="sayi-kart"><b>${yazarSay}</b><span>Akademik Yazar</span><small>${yayinSay} akademik yayınevi</small></div>
      <div class="sayi-kart"><b>★ ${ortPuan}</b><span>Ortalama Okur Puanı</span><small>${puanlilar.length} puanlı eser</small></div>
    </div>

    <div class="istat">
      <div class="kutu">
        <div class="kutu-ust"><h3>Akademik &amp; Klinik Alt Alanlar</h3><small>Tıkla katalogda filtrele</small></div>
        ${cubukAk(tumKlinikAlanlar, 'konu')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Öne Çıkan Akademik Yazarlar</h3><small>Tıkla katalogda ara</small></div>
        ${cubukAk(top(toplaAk(k => k.yazar), 14), 'yazar')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Akademik Yayınevleri</h3><small>Tıkla katalogda ara</small></div>
        ${cubukAk(top(toplaAk(k => k.yayinevi), 14), 'yayinevi')}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Yayınlandığı Dönem (On Yıllar)</h3><small>Yayın tarihi dağılımı</small></div>
        ${cubukAk([...yyMap.entries()].sort())}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>Sayfa Sayısı Dağılımı</h3><small>Kapsam &amp; hacim</small></div>
        ${cubukAk(sayfaDiz)}
      </div>
      <div class="kutu">
        <div class="kutu-ust"><h3>En Yüksek Puanlı Akademik Eserler</h3><small>Detay için tıklayın</small></div>
        ${enPuanliAk.map(k => `<div class="mini-satir" data-kitap="${k.isbn}">
          <div style="min-width:0"><b>${esc(k.baslik)}</b><small>${esc(k.yazar)} ${k.yayinevi ? '· ' + esc(k.yayinevi) : ''}</small></div>
          <span class="mini-sag">★ ${Number(k.puan).toFixed(2)}</span>
        </div>`).join('')}
      </div>
    </div>

    <div class="ak-katalog-baslik" id="akKatalogBaslik">
      <h3>📚 Akademik Kitaplar Kataloğu <small style="color:var(--vurgu-acik);font-size:0.86rem">(${akFil.length} / ${akTum.length} kitap gösteriliyor)</small></h3>
      <div class="ak-katalog-araclar">
        <input id="akAraInput" type="search" placeholder="Akademik kitap, yazar, Türkçe/İngilizce özet ara…" value="${esc(durum.akAra)}">
        <select id="akKonuSec">
          <option value="">Tüm Klinik Alanlar</option>
          ${tumKlinikAlanlar.map(([al, n]) => `<option value="${esc(al)}" ${durum.akKonu === al ? 'selected' : ''}>${esc(al)} (${n})</option>`).join('')}
        </select>
        <select id="akDilSec">
          <option value="" ${durum.akDil === '' ? 'selected' : ''}>Tüm Diller (${akTum.length})</option>
          <option value="en" ${durum.akDil === 'en' ? 'selected' : ''}>Yabancı Dil / Çeviri Özetli (${enSay})</option>
          <option value="tr" ${durum.akDil === 'tr' ? 'selected' : ''}>Türkçe Baskı (${trSay})</option>
        </select>
        <select id="akSiralaSec">
          <option value="baslik-a" ${durum.akSirala === 'baslik-a' ? 'selected' : ''}>Kitap Adı (A → Z)</option>
          <option value="yazar-a" ${durum.akSirala === 'yazar-a' ? 'selected' : ''}>Yazar (A → Z)</option>
          <option value="yayin_yili-d" ${durum.akSirala === 'yayin_yili-d' ? 'selected' : ''}>Yayın Yılı (Yeni → Eski)</option>
          <option value="yayin_yili-a" ${durum.akSirala === 'yayin_yili-a' ? 'selected' : ''}>Yayın Yılı (Eski → Yeni)</option>
          <option value="sayfa-d" ${durum.akSirala === 'sayfa-d' ? 'selected' : ''}>Sayfa Sayısı (Çok → Az)</option>
          <option value="puan-d" ${durum.akSirala === 'puan-d' ? 'selected' : ''}>Okur Puanı (Yüksek → Düşük)</option>
        </select>
        ${(durum.akAra || durum.akDil || durum.akKonu) ? `<button id="akFiltreSifirla" class="buton-metin">Filtreyi Temizle</button>` : ''}
      </div>
    </div>

    <div id="akListeGrid" class="grid">
      ${akFil.length ? akFil.map(k => kartHtml(k, qAk)).join('') : '<div class="bos-sonuc">Arama kriterlerinize uygun akademik kitap bulunamadı.</div>'}
    </div>
  `;

  // Akademik katalog içindeki input olaylarını bağla
  const inp = $('#akAraInput');
  if (inp) {
    inp.addEventListener('input', e => {
      durum.akAra = e.target.value;
      const pos = e.target.selectionStart;
      akademikIstatistikCiz(ustBarHtml);
      const yeniInp = $('#akAraInput');
      if (yeniInp) { yeniInp.focus(); yeniInp.setSelectionRange(pos, pos); }
    });
  }
  const ks = $('#akKonuSec');
  if (ks) ks.addEventListener('change', e => { durum.akKonu = e.target.value; akademikIstatistikCiz(ustBarHtml); });
  const ds = $('#akDilSec');
  if (ds) ds.addEventListener('change', e => { durum.akDil = e.target.value; akademikIstatistikCiz(ustBarHtml); });
  const ss = $('#akSiralaSec');
  if (ss) ss.addEventListener('change', e => { durum.akSirala = e.target.value; akademikIstatistikCiz(ustBarHtml); });
  const sfBtn = $('#akFiltreSifirla');
  if (sfBtn) sfBtn.addEventListener('click', () => { durum.akAra = ''; durum.akDil = ''; durum.akKonu = ''; akademikIstatistikCiz(ustBarHtml); });
}

function istatistikCiz(liste, yilKume) {
  const akSayisi = K.filter(k => k.akademik).length;
  const ustBarHtml = `<div class="istat-alt-bar">
    <div class="istat-alt-sekmeler">
      <button class="istat-sek-btn ${durum.istatSekme === 'genel' ? 'aktif' : ''}" data-ist-sek="genel">
        📊 Genel Arşiv İstatistikleri <small>${liste.length}</small>
      </button>
      <button class="istat-sek-btn ${durum.istatSekme === 'akademik' ? 'aktif' : ''}" data-ist-sek="akademik">
        🎓 Akademik Kitaplar <small>${akSayisi}</small>
      </button>
    </div>
  </div>`;

  if (durum.istatSekme === 'akademik') {
    $('#istatAracSag').hidden = true;
    akademikIstatistikCiz(ustBarHtml);
    return;
  }

  $('#istatAracSag').hidden = false;
  if (!liste.length) {
    $('#sekIstatistik').innerHTML = ustBarHtml + '<div class="bos-sonuc">Seçili filtrelere uygun istatistik verisi bulunamadı.</div>';
    return;
  }
  const m = durum.metrik; // 'kitap' | 'saat' | 'sayfa'
  const degerVer = k => m === 'saat' ? ((k.sure_sn || 0) / 3600) : m === 'sayfa' ? (k.sayfa || 0) : 1;
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
  const toplamSn = liste.reduce((s, k) => s + (k.sure_sn || 0), 0);
  const toplamSayfa = liste.reduce((s, k) => s + (k.sayfa || 0), 0);
  const puanlilar = liste.filter(k => k.puan);
  const ortPuan = puanlilar.length ? (puanlilar.reduce((s, k) => s + Number(k.puan), 0) / puanlilar.length).toFixed(2) : '—';
  const payYuzde = Math.round((liste.length / K.length) * 100);

  // Yıllara göre karşılaştırma kartları (diğer filtreler sabitken 2025 vs 2026)
  const yillar = [...new Set(K.map(k => k.dinleme_yili).filter(Boolean))].sort((a, b) => b - a);
  const secYil = $('#fDinYil').value;
  const yilKartlari = yillar.map(y => {
    const yk = yilKume.filter(k => k.dinleme_yili === y);
    const ySn = yk.reduce((s, k) => s + (k.sure_sn || 0), 0);
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

  // Süre dağılımı (sadece süresi olan sesli kitaplar için) ve sayfa dağılımı
  const sureKat = k => {
    if (!k.sure_sn || k.sure_sn <= 0) return null;
    const sa = k.sure_sn / 3600;
    return sa < 2 ? '0 – 2 saat (Kısa)' : sa < 5 ? '2 – 5 saat' : sa < 8 ? '5 – 8 saat' : sa < 12 ? '8 – 12 saat' : '12+ saat (Uzun)';
  };
  const sureSira = ['0 – 2 saat (Kısa)', '2 – 5 saat', '5 – 8 saat', '8 – 12 saat', '12+ saat (Uzun)'];
  const sureMap = topla(sureKat);
  const sureDiz = sureSira.filter(x => sureMap.has(x)).map(x => [x, sureMap.get(x)]);

  const sayfaKat = k => {
    const sf = k.sayfa || 0;
    if (!sf) return null;
    return sf < 150 ? '1 – 149 sayfa' : sf < 300 ? '150 – 299 sayfa' : sf < 500 ? '300 – 499 sayfa' : '500+ sayfa';
  };
  const sayfaSira = ['1 – 149 sayfa', '150 – 299 sayfa', '300 – 499 sayfa', '500+ sayfa'];
  const sayfaMap = topla(sayfaKat);
  const sayfaDiz = sayfaSira.filter(x => sayfaMap.has(x)).map(x => [x, sayfaMap.get(x)]);

  // Aylık dağılım ve Yayın on yılı
  const ayMap = topla(k => (k.baslangic || '').slice(0, 7));
  const yyMap = topla(k => k.yayin_yili ? Math.floor(k.yayin_yili / 10) * 10 + '\'lar' : null);

  // En uzun 6 kitap ve En yüksek puanlı 6 kitap
  const enUzun = [...liste].filter(k => k.sure_sn > 0).sort((a, b) => b.sure_sn - a.sure_sn).slice(0, 6);
  const enPuanli = [...liste].filter(k => k.puan && (k.puan_sayisi || 0) >= 5).sort((a, b) => b.puan - a.puan || b.puan_sayisi - a.puan_sayisi).slice(0, 6);

  const filtreBilgi = aktifFilSonuc.length ? `<div class="istat-bilgi-cubuk">
    <span>Seçili filtrelere göre <b>${liste.length} kitap</b> (${payYuzde}%) üzerinden istatistikler gösteriliyor. Grafik çubuklarına tıklayarak filtreyi daraltabilirsiniz.</span>
    <button id="istatKitaplariGor">Bu ${liste.length} Kitabı Listele →</button>
  </div>` : `<div class="istat-bilgi-cubuk">
    <span>💡 İpucu: Sol panelden, üstteki kategori/yıl düğmelerinden veya <b>doğrudan grafik çubuklarına tıklayarak</b> istatistikleri istediğiniz kategori, yıl, yazar veya etikete göre filtreleyebilirsiniz.</span>
  </div>`;

  const sesliSayisi = liste.filter(k => k.sure_sn > 0).length || 1;

  $('#sekIstatistik').innerHTML = `
    ${ustBarHtml}
    ${filtreBilgi}
    <div class="yil-izgara">${yilKartlari}</div>
    <div class="sayilar">
      <div class="sayi-kart"><b>${liste.length}</b><span>Toplam Kitap</span><small>Arşivin %${payYuzde}'i (${liste.filter(k => k.akademik).length} akademik)</small></div>
      <div class="sayi-kart"><b>${Math.round(toplamSn / 3600).toLocaleString('tr-TR')} sa</b><span>Toplam Dinleme</span><small>≈ ${(toplamSn / 86400).toFixed(1)} tam gün</small></div>
      <div class="sayi-kart"><b>${toplamSayfa.toLocaleString('tr-TR')}</b><span>Toplam Sayfa</span><small>Ort. ${Math.round(toplamSayfa / liste.length)} sf/kitap</small></div>
      <div class="sayi-kart"><b>${new Set(liste.map(k => k.yazar).filter(Boolean)).size}</b><span>Farklı Yazar</span><small>${new Set(liste.map(k => k.yayinevi).filter(Boolean)).size} yayınevi</small></div>
      <div class="sayi-kart"><b>${new Set(liste.map(k => k.anlatici).filter(Boolean)).size}</b><span>Farklı Seslendiren</span><small>Ort. ${(toplamSn / sesliSayisi / 3600).toFixed(1)} sa/sesli kitap</small></div>
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
        <div class="kutu-ust"><h3>En Çok Okunan / Dinlenen Yazarlar</h3><small>${metrikEtiket} · Tıkla filtrele</small></div>
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
          <span class="mini-sag">★ ${Number(k.puan).toFixed(2)}</span>
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
  if (b.dataset.ozel === 'psk') {
    if ($('#fAlt').value === 'Psikoloji Kitapları') {
      $('#fKat').value = '';
      guncelleAlt();
      $('#fAlt').value = '';
    } else {
      $('#fKat').value = 'Kurgu Dışı';
      guncelleAlt();
      $('#fAlt').value = 'Psikoloji Kitapları';
      durum.etiketler.delete('Akademik');
    }
    if (durum.sekme === 'akademik') sekmeDegistir('kitaplar');
    else ciz();
    return;
  }
  if (b.dataset.ozel === 'ak') {
    if (durum.etiketler.has('Akademik')) {
      durum.etiketler.delete('Akademik');
    } else {
      $('#fKat').value = '';
      guncelleAlt();
      $('#fAlt').value = '';
      durum.etiketler.add('Akademik');
    }
    if (durum.sekme === 'akademik') sekmeDegistir('kitaplar');
    else ciz();
    return;
  }
  durum.etiketler.delete('Akademik');
  $('#fKat').value = b.dataset.kat;
  guncelleAlt();
  $('#fAlt').value = '';
  if (durum.sekme === 'akademik') sekmeDegistir('kitaplar');
  else ciz();
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
  const altSekBtn = e.target.closest('[data-ist-sek]');
  if (altSekBtn) {
    durum.istatSekme = altSekBtn.dataset.istSek;
    durum.sekme = durum.istatSekme === 'akademik' ? 'akademik' : 'istatistik';
    document.querySelectorAll('.sekmeler button').forEach(x => x.classList.toggle('aktif', x.dataset.sek === durum.sekme));
    ciz();
    return;
  }
  if (e.target.id === 'akTumunuKitapliktaGor') {
    $('#fKat').value = '';
    guncelleAlt();
    $('#fAlt').value = '';
    durum.etiketler.add('Akademik');
    sekmeDegistir('kitaplar');
    return;
  }
  if (e.target.id === 'istatKitaplariGor') { sekmeDegistir('kitaplar'); return; }

  const kartEl = e.target.closest('.kart');
  if (kartEl) { modalAc(kartEl.dataset.id); return; }

  const akCb = e.target.closest('[data-ak-tur]');
  if (akCb) {
    const { akTur, akDeger } = akCb.dataset;
    if (akTur === 'konu') durum.akKonu = durum.akKonu === akDeger ? '' : akDeger;
    else if (akTur === 'yazar' || akTur === 'yayinevi') durum.akAra = durum.akAra === akDeger ? '' : akDeger;
    ciz();
    const el = $('#akKatalogBaslik');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

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
  if (t) { durum.etiketler.add(t.dataset.modalE); modalKapat(); if (durum.sekme === 'akademik') sekmeDegistir('kitaplar'); else ciz(); }
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
