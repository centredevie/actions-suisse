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

    # Recombiner les prix coupés sur 2 lignes (ex: "2." suivi de "99" ou "2" suivi de ".99")
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

        # Extraction de prix flexible dans la ligne (ex: "2.99", "CHF 2.99", "2.99*", "au lieu de 4.50")
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

def discover_promo_urls(page):
    """Détecte uniquement les vraies URLs de rayons d'actions (/c/fr-CH/store/.../a10...)."""
    print(f"Recherche des liens d'actions sur {HOME_LIDL}...")
    page.goto(HOME_LIDL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)

    try:
        btn = page.locator("button:has-text('Accepter'), #onetrust-accept-btn-handler").first
        if btn.is_visible(timeout=2000):
            btn.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    hrefs = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        return links
            .map(a => a.getAttribute('href') || '')
            .filter(href => href.includes('/c/fr-CH/store/') && /\/a\d+/.test(href));
    }""")

    urls = [FALLBACK_LIDL]
    for h in hrefs:
        full = urljoin(HOME_LIDL, h)
        if full not in urls and 'lidl-plus' not in full:
            urls.append(full)

    return urls[:4]

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

        target_urls = discover_promo_urls(page)
        print(f"Pages d'actions Lidl ciblées : {target_urls}")

        for url in target_urls:
            print(f"Scraping Lidl : {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)

                for _ in range(15):
                    try:
                        more_btn = page.locator("button:has-text('Afficher plus'), button:has-text('Charger plus')").first
                        if more_btn.is_visible(timeout=400):
                            more_btn.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(450)

                # Extraction des cartes produits + attributs data-*
                cards_data = page.evaluate("""() => {
                    const selectors = [
                        '.product-grid-box',
                        '[data-testid*="product"]',
                        'li.s-grid__item',
                        'article'
                    ];
                    let els = [];
                    for (const sel of selectors) {
                        const found = Array.from(document.querySelectorAll(sel));
                        if (found.length > 3) {
                            els = found;
                            break;
                        }
                    }
                    if (!els.length) {
                        els = Array.from(document.querySelectorAll('main a')).filter(a => a.querySelector('img') && /\\d+\\.\\d{2}/.test(a.innerText));
                    }
                    return els.map(el => ({
                        text: el.innerText || '',
                        title: el.getAttribute('data-name') || el.getAttribute('title') || '',
                        price: el.getAttribute('data-price') || ''
                    }));
                }""")

                print(f"  -> {len(cards_data)} cartes brutes sur {url}")
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
                print(f"Erreur sur {url} : {e}")

        browser.close()

    with open("lidl_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total Lidl sauvegardé : {len(results)} offres dans lidl_import.json")

if __name__ == "__main__":
    main()
