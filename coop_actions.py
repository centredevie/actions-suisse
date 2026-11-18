import json
import re
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

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

def extract_from_json_payload(data, out_list, seen):
    if isinstance(data, dict):
        title = data.get('title') or data.get('name') or data.get('productName')
        price_obj = data.get('price') or data.get('salesPrice') or data.get('prices')
        if title and isinstance(title, str) and price_obj is not None:
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
                qty = str(data.get('quantity') or data.get('content') or data.get('packageSize') or '')
                cat_raw = str(data.get('category') or data.get('mainCategory') or '')
                valid = str(data.get('validTo') or data.get('promotionPeriod') or '')
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
        for v in data.values():
            extract_from_json_payload(v, out_list, seen)
    elif isinstance(data, list):
        for item in data:
            extract_from_json_payload(item, out_list, seen)

def main():
    results = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            locale="fr-CH",
            timezone_id="Europe/Zurich",
            viewport={"width": 1366, "height": 900}
        )
        page = context.new_page()
        if stealth_sync:
            stealth_sync(page)

        def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "application/json" in ct and response.status == 200:
                    if any(k in response.url for k in ["product", "search", "m_1011", "offer", "action"]):
                        extract_from_json_payload(response.json(), results, seen)
            except Exception:
                pass

        page.on("response", handle_response)

        print("Chargement des actions Coop via VPN...", flush=True)
        try:
            page.goto(URL_COOP, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(4000)
            print(f"Titre de la page reçue : {page.title()}", flush=True)
        except Exception as e:
            print(f"Erreur réseau Coop : {e}", flush=True)
            browser.close()
            with open("coop_import.json", "w", encoding="utf-8") as f:
                json.dump([], f)
            return

        try:
            btn = page.locator("#onetrust-accept-btn-handler, button:has-text('Accepter')").first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1500)
        except Exception:
            pass

        for step in range(1, 12):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step / 11});")
            page.wait_for_timeout(450)

        dom_items = page.evaluate("""() => {
            const cards = Array.from(document.querySelectorAll('[data-udo-cat1], [class*="productTile"], article'));
            return cards.map(c => ({
                cat: c.getAttribute('data-udo-cat1') || '',
                text: c.innerText || ''
            }));
        }""")

        print(f"JSON interceptés : {len(results)} | Cartes DOM trouvées : {len(dom_items)}", flush=True)

        for d in dom_items:
            lines = [l.strip() for l in d['text'].split('\n') if l.strip()]
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
                        "cat": map_category(d['cat'], name),
                        "name": name,
                        "qty": qty,
                        "price": price,
                        "old": old_price,
                        "valid": ""
                    })

        browser.close()

    with open("coop_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"{len(results)} produits écrits dans coop_import.json", flush=True)

if __name__ == "__main__":
    main()
