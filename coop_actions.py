import json
import re
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    import requests as cffi_requests

URL_COOP = "https://www.coop.ch/fr/actions/les-actions-du-moment/c/m_1011"

def map_category(cat_raw, name=""):
    t = f"{cat_raw} {name}".lower()
    if any(k in t for k in ['fruit', 'légume', 'salade', 'pomme', 'banane', 'tomate', 'carotte', 'courge', 'orange', 'mandarine', 'fraise', 'raisin']):
        return 'Fruits et légumes'
    if any(k in t for k in ['viande', 'poisson', 'poulet', 'bœuf', 'boeuf', 'porc', 'veau', 'agneau', 'saumon', 'crevette', 'jambon', 'saucisse', 'charcuterie']):
        return 'Viande et poisson'
    if any(k in t for k in ['laitier', 'fromage', 'lait', 'yogourt', 'yaourt', 'beurre', 'crème', 'fondue', 'raclette', 'gruyère', 'oeuf', 'œuf']):
        return 'Produits laitiers'
    if any(k in t for k in ['pain', 'boulangerie', 'tresse', 'croissant', 'brioche', 'toast']):
        return 'Boulangerie'
    if any(k in t for k in ['boisson', 'vin', 'bière', 'eau', 'jus', 'thé', 'café', 'coca', 'soda', 'prosecco']):
        return 'Boissons et vins'
    if any(k in t for k in ['surgelé', 'glace', 'pizza', 'frites']):
        return 'Surgelés'
    if any(k in t for k in ['hygiène', 'ménage', 'maison', 'lessive', 'savon', 'shampoing', 'dentifrice', 'papier', 'vaisselle']):
        return 'Hygiène et maison'
    if any(k in t for k in ['animal', 'animaux', 'chien', 'chat']):
        return 'Animaux'
    if any(k in t for k in ['bazar', 'loisir', 'maison & habitat', 'vêtement', 'jouet', 'fleur', 'plante', 'cuisine']):
        return 'Bazar et loisirs'
    return 'Épicerie'

def extract_json_recursive(obj, out_list, seen):
    if isinstance(obj, dict):
        title = obj.get('title') or obj.get('name') or obj.get('productName')
        price_obj = obj.get('price') or obj.get('salesPrice') or obj.get('prices')
        if isinstance(title, str) and price_obj is not None:
            price = None
            old_price = None
            if isinstance(price_obj, (int, float)):
                price = float(price_obj)
            elif isinstance(price_obj, dict):
                val = price_obj.get('value') or price_obj.get('current') or price_obj.get('amount')
                old = price_obj.get('was') or price_obj.get('old') or price_obj.get('regular') or price_obj.get('originalPrice')
                if isinstance(val, (int, float)):
                    price = float(val)
                if isinstance(old, (int, float)) and float(old) > (price or 0):
                    old_price = float(old)

            if price and price > 0:
                qty = str(obj.get('quantity') or obj.get('content') or obj.get('packageSize') or '')
                cat_raw = str(obj.get('category') or obj.get('mainCategory') or '')
                valid = str(obj.get('validTo') or obj.get('promotionPeriod') or '')
                key = (title.strip(), price)
                if key not in seen:
                    seen.add(key)
                    out_list.append({
                        "store": "coop",
                        "cat": map_category(cat_raw, title),
                        "name": title.strip(),
                        "qty": qty.strip(),
                        "price": price,
                        "old": old_price,
                        "valid": valid.strip()
                    })
        for v in obj.values():
            extract_json_recursive(v, out_list, seen)
    elif isinstance(obj, list):
        for item in obj:
            extract_json_recursive(item, out_list, seen)

def main():
    results = []
    seen = set()

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-CH,fr;q=0.9",
        "Referer": "https://www.coop.ch/fr/"
    }

    for page_num in range(0, 5):
        url = f"{URL_COOP}?q=%3Arelevance&page={page_num}&pageSize=60"
        print(f"Requête Coop via VPN (page {page_num})...", flush=True)
        try:
            resp = cffi_requests.get(url, headers=headers, impersonate="chrome124", timeout=15)
            print(f"  Statut HTTP : {resp.status_code} | Taille : {len(resp.text)} octets", flush=True)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            print(f"  Titre HTML : {title_tag.text.strip() if title_tag else 'Aucun'}", flush=True)

            for sc in soup.find_all("script"):
                txt = sc.string or ""
                if "product" in txt.lower() and ("price" in txt.lower() or "salesprice" in txt.lower()):
                    try:
                        extract_json_recursive(json.loads(txt), results, seen)
                    except Exception:
                        pass

            cards = soup.select('[data-udo-cat1], [class*="productTile"], article')
            for c in cards:
                cat_attr = c.get("data-udo-cat1", "")
                lines = [l.strip() for l in c.get_text("\n").split("\n") if l.strip()]
                price = None
                old_price = None
                qty = ""
                name = ""
                for l in lines:
                    m = re.match(r'^(?:CHF\s*)?(\d+\.\d{2})$', l)
                    if m:
                        v = float(m.group(1))
                        if price is None:
                            price = v
                        elif v > price:
                            old_price = v
                    elif re.search(r'\b(\d+\s*(?:g|kg|ml|cl|l|pièce|pièces))\b', l, re.I) and len(l) < 30:
                        qty = l
                    elif not name and len(l) > 3 and '%' not in l:
                        name = l
                if name and price:
                    key = (name, price)
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "store": "coop",
                            "cat": map_category(cat_attr, name),
                            "name": name,
                            "qty": qty,
                            "price": price,
                            "old": old_price,
                            "valid": ""
                        })

            if len(results) == 0 and page_num == 0:
                break
        except Exception as e:
            print(f"  Erreur page {page_num} : {e}", flush=True)
            break

    with open("coop_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total Coop sauvegardé : {len(results)} produits dans coop_import.json", flush=True)

if __name__ == "__main__":
    main()
