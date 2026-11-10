# Önbellekteki Kitapyurdu kayıtlarını (düzeltilmiş ayrıştırıcıyla) yeniden işler, ardından hepsi.json'u günceller.
import json, os, time
from concurrent.futures import ThreadPoolExecutor
from toplayici import ONB, indir, ky_ayrisitir, onb_oku, onb_yaz

ham = onb_oku('hepsi.json')

def yenile(k):
    ky = k.get('kitapyurdu') or {}
    if ky.get('url'):
        p = indir(ky['url'])
        if p:
            yeni = ky_ayrisitir(p, ky['url']); yeni['kapak'] = yeni['kapak'] or ky.get('kapak')
            onb_yaz(f"ky_{k['isbn']}.json", yeni); k['kitapyurdu'] = yeni
        time.sleep(0.3)
    return k

with ThreadPoolExecutor(4) as ex: ham = list(ex.map(yenile, ham))
onb_yaz('hepsi.json', ham)
print('tamam', sum(1 for k in ham if (k['kitapyurdu'] or {}).get('tanitim')), 'tanıtımlı')
