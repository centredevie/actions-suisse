import json
import re
from playwright.sync_api import sync_playwright

URL_DENNER = "https://www.denner.ch/fr/actions/"

def map_category(text):
    t = text.lower()
    if any(k in t for k in ['pomme', 'poire', 'banane', 'orange', 'mandarine', 'clémentine', 'citron', 'raisin', 'fraise', 'kiwi', 'mangue', 'avocat', 'salade', 'tomate', 'carotte', 'oignon', 'ail', 'pomme de terre', 'courgette', 'poivron', 'brocoli', 'champignon', 'légume', 'fruit']):
        return 'Fruits et légumes'
    if any(k in t for k in ['poulet', 'bœuf', 'boeuf', 'porc', 'veau', 'agneau', 'dinde', 'canard', 'viande', 'steak', 'filet', 'entrecôte', 'saucisse', 'cervelas', 'jambon', 'lard', 'salami', 'charcuterie', 'poisson', 'saumon', 'crevette', 'thon', 'truite', 'cabillaud']):
        return 'Viande et poisson'
    if any(k in t for k in ['lait', 'fromage', 'gruyère', 'emmental', 'raclette', 'fondue', 'mozzarella', 'parmesan', 'yogourt', 'yaourt', 'crème', 'beurre', 'séré', 'oeuf', 'œuf']):
        return 'Produits laitiers'
    if any(k in t for k in ['pain', 'tresse', 'croissant', 'baguette', 'toast', 'brioche', 'petit pain', 'boulangerie']):
        return 'Boulangerie'
    if any(k in t for k in ['vin', 'bière', 'eau', 'jus', 'sirop', 'thé', 'café', 'coca', 'soda', 'prosecco', 'champagne', 'merlot', 'pinot', 'chardonnay', 'rioja', 'ribera', 'bordeaux', 'rosé', 'boisson', 'whisky', 'gin', 'vodka']):
        return 'Boissons et vins'
    if any(k in t for k in ['surgelé', 'glace', 'pizza', 'frites', 'bâtonnets']):
        return 'Surgelés'
    if any(k in t for k in ['lessive', 'savon', 'shampoing', 'gel douche', 'dentifrice', 'papier', 'mouchoir', 'nettoyant', 'vaisselle', 'crème mains', 'déodorant', 'persil', 'ariel', 'lenor', 'pampers']):
        return 'Hygiène et maison'
    if any(k in t for k in ['chien', 'chat', 'croquette', 'litière', 'felix', 'whiskas', 'purina']):
        return 'Animaux'
    if any(k in t for k in ['poêle', 'casserole', 'lampe', 'vêtement', 'pantalon', 'veste', 'chaussure', 'chaussette', 'jouet', 'outil', 'plante', 'fleur', 'bougie', 'déco']):
        return 'Bazar et loisirs'
    return 'Épicerie'

def extract_denner_json(obj, out_list, seen):
    """Parcourt récursivement les réponses JSON / __NEXT_DATA__ de Denner."""
    if isinstance(obj, dict):
        title = obj.get('title') or obj.get('name') or obj.get('productName') or obj.get('headline')
        # Recherche de prix sous différentes clés utilisées par Denner
        raw_price = obj.get('price') or obj.get('salesPrice') or obj.get('actionPrice') or obj.get('specialPrice')
        raw_old = obj.get('oldPrice') or obj.get('insteadOfPrice') or obj.get('regularPrice') or obj.get('comparisonPrice')

        price = None
        old_price = None

        if isinstance(raw_price, (int, float)):
            price = float(raw_price)
        elif isinstance(raw_price, str):
            m = re.search(r'(\d+\.\d{2})', raw_price)
            if m:
                price = float(m.group(1))
        elif isinstance(raw_price, dict):
            v = raw_price.get('value') or raw_price.get('amount') or raw_price.get('current')
            o = raw_price.get('old') or raw_price.get('insteadOf') or raw_price.get('regular')
            if isinstance(v, (int, float)):
                price = float(v)
            if isinstance(o, (int, float)):
                old_price = float(o)

        if isinstance(raw_old, (int, float)) and raw_old > (price or 0):
            old_price = float(raw_old)
        elif isinstance(raw_old, str):
            m = re.search(r'(\d+\.\d{2})', raw_old)
            if m and float(m.group(1)) > (price or 0):
                old_price = float(m.group(1))

        if isinstance(title, str) and len(title.strip()) > 2 and price and 0.1 < price < 1000:
            qty = str(obj.get('packaging') or obj.get('quantity') or obj.get('unit') or obj.get('subline') or '')
            cat_raw = str(obj.get('category') or obj.get('categoryName') or '')
            valid = str(obj.get('validity') or obj.get('validTo') or '')
            key = (title.strip(), price)
            if key not in seen:
                seen.add(key)
                out_list.append({
                    "store": "denner",
                    "cat": map_category(f"{cat_raw} {title}"),
                    "name": title.strip(),
                    "qty": qty.strip(),
                    "price": price,
                    "old": old_price,
                    "valid": valid.strip()
                })

        for v in obj.values():
            extract_denner_json(v, out_list, seen)
    elif isinstance(obj, list):
        for item in obj:
            extract_denner_json(item, out_list, seen)

def main():
    results = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            locale="fr-CH",
            timezone_id="Europe/Zurich"
        )
        page = context.new_page()

        # 1. Intercepter toutes les réponses JSON chargées par la page Denner
        def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "application/json" in ct and response.status == 200:
                    extract_denner_json(response.json(), results, seen)
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Chargement Denner : {URL_DENNER}", flush=True)
        page.goto(URL_DENNER, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        print(f"Titre page Denner : {page.title()}", flush=True)

        # Accepter cookies si présent
        try:
            btn = page.locator("#onetrust-accept-btn-handler, button:has-text('Accepter')").first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Défiler pour déclencher le lazy-loading
        for step in range(1, 10):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step / 9});")
            page.wait_for_timeout(500)

        # 2. Extraire le JSON embarqué (__NEXT_DATA__ / scripts JSON)
        scripts = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('script[type="application/json"]'))
                .map(s => s.textContent || '');
        }""")
        for raw in scripts:
            try:
                extract_denner_json(json.loads(raw), results, seen)
            except Exception:
                pass

        print(f"Offres Denner via JSON/API : {len(results)}", flush=True)

        # 3. Extraction universelle depuis les liens/cartes contenant une image et un prix
        dom_cards = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/fr/actions/"], article, [class*="product"], [class*="offer"]'));
            return links
                .filter(el => el.querySelector('img') && /\\d+\\.\\d{2}/.test(el.innerText))
                .map(el => el.innerText || '');
        }""")

        print(f"Cartes DOM Denner détectées : {len(dom_cards)}", flush=True)

        for text in dom_cards:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            price = None
            old_price = None
            qty = ""
            name_parts = []
            for l in lines:
                if re.match(r'^-?\d+\s*%$', l) or l.lower() in {'action', 'hit', 'nouveau', 'en vente dès maintenant'}:
                    continue
                nums = re.findall(r'(\d+\.\d{2})', l)
                if nums and len(l) < 25:
                    for n in nums:
                        v = float(n)
                        if price is None:
                            price = v
                        elif v > price and old_price is None:
                            old_price = v
                        elif v < price and old_price is None:
                            old_price = price
                            price = v
                    continue
                if re.search(r'\b(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pces|pièces|x|×)\b)', l, re.I) and len(l) < 35 and not qty:
                    qty = l
                    continue
                if len(l) > 2:
                    name_parts.append(l)

            if price and name_parts:
                name = " - ".join(name_parts[:2])
                key = (name, price)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "store": "denner",
                        "cat": map_category(name),
                        "name": name,
                        "qty": qty,
                        "price": price,
                        "old": old_price,
                        "valid": ""
                    })

        browser.close()

    with open("denner_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total Denner sauvegardé : {len(results)} offres dans denner_import.json", flush=True)

if __name__ == "__main__":
    main()
