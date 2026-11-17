"""Test: Coop accepte-t-il les requêtes depuis GitHub (anti-robots DataDome)?
Affiche statuts HTTP et un exemple de produit. N'écrit rien d'important.
"""
import json
import sys
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
PAGE = "https://www.coop.ch/fr/actions/les-actions-du-moment/c/m_1011"
CAROUSEL = ("https://www.coop.ch/fr/carousels/lazy/json/0fe17fa8-224a-4712-9615-2f4af73902a0"
            "?useIsolatedCarousel=true&isWithButton=false&isQuantity=30&isSlider=productslider"
            "&isTitle=Hit+d%27assortiment&isData=SOLR%3aitemtype%3aAssortmentHitDummyProduct"
            "&fontColorInverted=false&backgroundColor=%23F5F3F0")

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})

r = s.get(PAGE, timeout=30)
print(f"[page] HTTP {r.status_code}, {len(r.content)} octets, cookies: {sorted(s.cookies.keys())}")
html = r.text
print("[page] mentionne datadome:", "datadome" in html.lower() or "captcha-delivery" in html.lower())
import re
ids = sorted(set(re.findall(r"carousels/lazy/json/([0-9a-f-]{36})", html)))
print(f"[page] identifiants de carrousel trouvés dans le HTML: {len(ids)}")

r2 = s.get(CAROUSEL, timeout=30, headers={"Referer": PAGE, "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"})
print(f"[carrousel] HTTP {r2.status_code}, type: {r2.headers.get('content-type')}, {len(r2.content)} octets")
if r2.ok and "json" in (r2.headers.get("content-type") or ""):
    data = r2.json()
    tuiles = []
    for a in data.get("contentJsons", {}).get("anchors", []):
        tuiles += a.get("json", {}).get("elements", [])
    print(f"[carrousel] {len(tuiles)} éléments")
    for t in tuiles[:2]:
        t = {k: v for k, v in t.items() if k not in ("image",)}
        print(json.dumps(t, ensure_ascii=False)[:1200])
else:
    print("[carrousel] début de la réponse:", r2.text[:300].replace("\n", " "))
    sys.exit(1)
