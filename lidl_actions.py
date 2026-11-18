import json
import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

HOME_LIDL = "https://www.lidl.ch/fr"
FALLBACK_LIDL = "https://www.lidl.ch/c/fr-CH/store/promotions-de-la-semaine/a10106737"

def map_category(text):
    t = text.lower()
    if any(k in t for k in ['pomme', 'poire', 'banane', 'orange', 'mandarine', 'clémentine', 'citron', 'raisin', 'fraise', 'kiwi', 'mangue', 'avocat', 'salade', 'tomate', 'carotte', 'oignon', 'ail', 'pomme de terre', 'courgette', 'poivron', 'brocoli', 'champignon', 'légume', 'fruit', 'bio ']):
        return 'Fruits et légumes'
    if any(k in t for k in ['poulet', 'bœuf', 'boeuf', 'porc', 'veau', 'agneau', 'dinde', 'canard', 'viande', 'steak', 'filet', 'entrecôte', 'saucisse', 'cervelas', 'jambon', 'lard', 'salami', 'charcuterie', 'poisson', 'saumon', 'crevette', 'thon', 'truite', 'cabillaud']):
        return 'Viande et poisson'
    if any(k in t for k in ['lait', 'fromage', 'gruyère', 'emmental', 'raclette', 'fondue', 'mozzarella', 'parmesan', 'yogourt', 'yaourt', 'crème', 'beurre', 'séré', 'oeuf', 'œuf']):
        return 'Produits laitiers'
    if any(k in t for k in ['pain', 'tresse', 'croissant', 'baguette', 'toast', 'brioche', 'petit pain', 'boulangerie']):
        return 'Boulangerie'
    if any(k in t for k in ['vin', 'bière', 'eau', 'jus', 'sirop', 'thé', 'café', 'coca', 'soda', 'prosecco', 'champagne', 'merlot', 'pinot', 'chardonnay', 'boisson']):
        return 'Boissons et vins'
    if any(k in t for k in ['surgelé', 'glace', 'pizza', 'frites', 'bâtonnets']):
        return 'Surgelés'
    if any(k in t for k in ['lessive', 'savon', 'shampoing', 'gel douche', 'dentifrice', 'papier', 'mouchoir', 'nettoyant', 'vaisselle', 'crème mains', 'déodorant']):
        return 'Hygiène et maison'
    if any(k in t for k in ['chien', 'chat', 'croquette', 'litière']):
        return 'Animaux'
    if any(k in t for k in ['poêle', 'casserole', 'lampe', 'vêtement', 'pantalon', 'veste', 'chaussure', 'chaussette', 'jouet', 'outil', 'plante', 'fleur', 'bougie', 'déco', 'parkside', 'silvercrest', 'esmara', 'livergy', 'crivit', 'lupilu']):
        return 'Bazar et loisirs'
    return 'Épicerie'

def parse_lidl_card(lines):
    ignore = {'ajouter au panier', 'en savoir plus', 'nouveau', 'super prix', 'action', 'exclusivité lidl plus', 'lidl plus', 'en magasin'}
    clean = [l.strip() for l in lines if l.strip() and l.strip().lower() not in ignore]
    if not clean:
        return None

    merged_lines = []
    i = 0
    while i < len(clean):
        if i + 1 < len(clean) and re.match(r'^\d+\.$', clean[i]) and re.match(r'^\d{2}\*?$', clean[i+1]):
            merged_lines.append(clean[i] + clean[i+1])
            i += 2
        else:
            merged_lines.append(clean[i])
            i += 1

    price = None
    old_price = None
    qty = ""
    valid = ""
    name_parts = []

    for line in merged_lines:
        if re.search(r'(?:dès le|valable|\d{2}\.\d{2}\.?\s*[–-])', line, re.I):
            valid = line
            continue
        if re.match(r'^-?\d+\s*%(?:\s*de rabais)?$', line, re.I):
            continue
        if re.search(r'(?:1\s*kg|100\s*g|1\s*l|100\s*ml)\s*=', line, re.I):
            if not qty:
                qty = line
            continue

        nums = re.findall(r'(\d+\.\d{2})', line)
        if nums and len(line) < 25:
            for n in nums:
                val = float(n)
                if price is None:
                    price = val
                elif val > price and old_price is None:
                    old_price = val
                elif val < price and old_price is None:
                    old_price = price
                    price = val
            continue

        if re.search(r'\b(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pièce|pièces|pces|x|×)\b)', line, re.I) and len(line) < 40 and not qty:
            qty = line
            continue

        if len(line) > 2:
            name_parts.append(line)

    if price is None or not name_parts:
        return None

    name = " - ".join(name_parts[:2])
    return {
        "store": "lidl",
        "cat": map_category(name),
        "name": name,
        "qty": qty,
        "price": price,
        "old": old_price,
        "valid": valid
    }

def extract_embedded_json(obj, out_list, seen):
    """Extrait les produits si Lidl les stocke dans un script JSON de la page."""
    if isinstance(obj, dict):
        title = obj.get('title') or obj.get('fullTitle') or obj.get('name')
        price_data = obj.get('price')
        if isinstance(title, str) and isinstance(price_data, dict):
            p = price_data.get('price') or price_data.get('amount')
            old = price_data.get('oldPrice') or price_data.get('strokePrice')
            if isinstance(p, (int, float)) and p > 0:
                key = (title.strip(), float(p))
                if key not in seen:
                    seen.add(key)
                    out_list.append({
                        "store": "lidl",
                        "cat": map_category(title),
                        "name": title.strip(),
                        "qty": str(price_data.get('packaging') or obj.get('packaging') or ''),
                        "price": float(p),
                        "old": float(old) if isinstance(old, (int, float)) and old > p else None,
                        "valid": ""
                    })
        for v in obj.values():
            extract_embedded_json(v, out_list, seen)
    elif isinstance(obj, list):
        for item in obj:
            extract_embedded_json(item, out_list, seen)

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
        page.set_default_timeout(15000)

        print("1/3 Découverte des pages d'actions Lidl...", flush=True)
        target_urls = [FALLBACK_LIDL]
        try:
            page.goto(HOME_LIDL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            hrefs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.getAttribute('href') || '')
                    .filter(h => h.includes('/c/fr-CH/store/') && /\\/a\\d+/.test(h));
            }""")
            for h in hrefs:
                full = urljoin(HOME_LIDL, h)
                if full not in target_urls and 'lidl-plus' not in full:
                    target_urls.append(full)
        except Exception as e:
            print(f"Note accueil Lidl : {e}", flush=True)

        target_urls = target_urls[:3]
        print(f"Pages ciblées ({len(target_urls)}) : {target_urls}", flush=True)

        for url in target_urls:
            print(f"2/3 Lecture de {url}...", flush=True)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2500)

                # Défilement rapide et borné (6 étapes max, aucun clic bloquant)
                for step in range(1, 7):
                    page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step / 6});")
                    page.wait_for_timeout(400)

                # 1) Extraction depuis les JSON intégrés dans la page
                scripts_json = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('script[type="application/json"]'))
                        .map(s => s.textContent || '');
                }""")
                for raw_j in scripts_json:
                    try:
                        extract_embedded_json(json.loads(raw_j), results, seen)
                    except Exception:
                        pass

                # 2) Extraction depuis le DOM visible
                cards_data = page.evaluate("""() => {
                    const selectors = ['.product-grid-box', '[data-testid*="product"]', 'li.s-grid__item', 'article'];
                    let els = [];
                    for (const sel of selectors) {
                        const found = Array.from(document.querySelectorAll(sel));
                        if (found.length > 2) { els = found; break; }
                    }
                    if (!els.length) {
                        els = Array.from(document.querySelectorAll('main a')).filter(a => /\\d+\\.\\d{2}/.test(a.innerText));
                    }
                    return els.map(el => ({
                        text: el.innerText || '',
                        title: el.getAttribute('data-name') || el.getAttribute('title') || '',
                        price: el.getAttribute('data-price') || ''
                    }));
                }""")

                print(f"   -> {len(cards_data)} cartes DOM vues | Total cumulé : {len(results)}", flush=True)
                for card in cards_data:
                    raw_lines = card['text'].split('\n')
                    if card['title'] and card['price']:
                        raw_lines = [card['title'], card['price']] + raw_lines
                    item = parse_lidl_card(raw_lines)
                    if item:
                        key = (item['name'], item['price'])
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
            except Exception as e:
                print(f"Erreur sur {url} : {e}", flush=True)

        browser.close()

    with open("lidl_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"3/3 Terminé : {len(results)} offres écrites dans lidl_import.json", flush=True)

if __name__ == "__main__":
    main()
