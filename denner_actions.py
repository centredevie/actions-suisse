import json
import re
from playwright.sync_api import sync_playwright

URL_DENNER = "https://www.denner.ch/fr/actions/"

def map_category(text):
    t = text.lower()
    if any(k in t for k in ['pomme', 'poire', 'banane', 'orange', 'mandarine', 'clémentine', 'citron', 'raisin', 'fraise', 'kiwi', 'mangue', 'avocat', 'salade', 'tomate', 'carotte', 'oignon', 'ail', 'pomme de terre', 'courgette', 'courge', 'grenade', 'pak-choi', 'poivron', 'brocoli', 'champignon', 'légume', 'fruit']):
        return 'Fruits et légumes'
    if any(k in t for k in ['poulet', 'bœuf', 'boeuf', 'porc', 'veau', 'agneau', 'dinde', 'canard', 'viande', 'steak', 'filet', 'entrecôte', 'romsteck', 'quasi', 'côtelette', 'saucisse', 'cervelas', 'jambon', 'lard', 'salami', 'burger', 'poisson', 'saumon', 'crevette', 'thon', 'truite', 'cabillaud']):
        return 'Viande et poisson'
    if any(k in t for k in ['lait', 'fromage', 'gruyère', 'emmental', 'leerdammer', 'raclette', 'fondue', 'mozzarella', 'parmesan', 'yogourt', 'yaourt', 'crème', 'beurre', 'séré', 'oeuf', 'œuf']):
        return 'Produits laitiers'
    if any(k in t for k in ['pain', 'tresse', 'croissant', 'baguette', 'toast', 'brioche', 'petit pain', 'boulangerie']):
        return 'Boulangerie'
    if any(k in t for k in ['vin', 'bière', 'eau', 'jus', 'sirop', 'thé', 'café', 'coca', 'soda', 'prosecco', 'champagne', 'merlot', 'pinot', 'primitivo', 'igt', 'doc', 'aoc', 'boisson']):
        return 'Boissons et vins'
    if any(k in t for k in ['surgelé', 'glace', 'pizza', 'frites', 'momo', 'momos']):
        return 'Surgelés'
    if any(k in t for k in ['lessive', 'persil', 'savon', 'shampoing', 'gel douche', 'dentifrice', 'papier', 'mouchoir', 'nettoyant', 'vaisselle', 'déodorant']):
        return 'Hygiène et maison'
    if any(k in t for k in ['chien', 'chat', 'croquette', 'litière']):
        return 'Animaux'
    if any(k in t for k in ['poêle', 'casserole', 'lampe', 'vêtement', 'jouet', 'outil', 'plante', 'fleur', 'rose', 'bougie', 'déco']):
        return 'Bazar et loisirs'
    return 'Épicerie'

def parse_denner_card(lines):
    ignore = {'ajouter à la liste', 'liste de courses', 'en savoir plus', 'nouveau', 'action', 'hit', 'spécial'}
    clean = [l.strip() for l in lines if l.strip() and l.strip().lower() not in ignore]
    if not clean:
        return None

    price = None
    old_price = None
    qty = ""
    valid = ""
    name_parts = []

    for line in clean:
        # Date de validité (ex: "12.11–18.11" ou "jusqu’au 18.11" ou "Valable du 12.11 au 18.11")
        if re.search(r'(?:jusqu|valable|\d{2}\.\d{2}\s*[–-]\s*\d{2}\.\d{2})', line, re.I):
            valid = line
            continue

        # Ignorer le badge pourcentage seul (ex: "-48%" ou "50%")
        if re.match(r'^-?\d+\s*%$', line):
            continue

        # Ancien prix explicitement marqué (ex: "au lieu de 12.90" ou "statt 12.90")
        m_old = re.search(r'(?:au lieu de|statt)\s*(?:CHF\s*)?(\d+\.\d{2})', line, re.I)
        if m_old:
            old_price = float(m_old.group(1))
            continue

        # Prix (ex: "1.95", "CHF 7.80", "12.95*")
        m_price = re.match(r'^(?:CHF\s*)?(\d+\.\d{2})\*?$', line, re.I)
        if m_price:
            val = float(m_price.group(1))
            if price is None:
                price = val
            elif val > price and old_price is None:
                old_price = val
            elif val < price and old_price is None:
                old_price = price
                price = val
            continue

        # Quantité / conditionnement (ex: "6 × 1,5 l", "1 kg", "3 × 90 g", "env. 600 g, les 100 g")
        if re.search(r'\b(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pièce|pièces|bouteilles|tranches|lessives|x|×)\b)', line, re.I) and len(line) < 55 and not qty:
            qty = line
            continue

        name_parts.append(line)

    if price is None or not name_parts:
        return None

    name = " · ".join(name_parts[:2])
    return {
        "store": "denner",
        "cat": map_category(name),
        "name": name,
        "qty": qty,
        "price": price,
        "old": old_price,
        "valid": valid
    }

def main():
    results = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="fr-CH"
        )
        page = context.new_page()
        print(f"Chargement Denner : {URL_DENNER}")
        page.goto(URL_DENNER, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2000)

        # Fermer cookies si affiché
        try:
            btn = page.locator("button:has-text('Accepter'), button:has-text('Tout accepter'), #onetrust-accept-btn-handler").first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Cliquer sur éventuels boutons "Afficher plus" et défiler toute la page
        for _ in range(18):
            try:
                more_btn = page.locator("button:has-text('Afficher plus'), button:has-text('Charger plus'), button:has-text('Voir plus')").first
                if more_btn.is_visible(timeout=400):
                    more_btn.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(400)

        # Extraire les cartes produits Denner
        cards_text = page.evaluate("""() => {
            const selectors = [
                'article',
                '[class*="product-card"]',
                '[class*="offer-card"]',
                '[class*="ProductCard"]',
                'main a'
            ];
            let els = [];
            for (const sel of selectors) {
                const found = Array.from(document.querySelectorAll(sel))
                    .filter(el => el.querySelector('img') && /\\d+\\.\\d{2}/.test(el.innerText));
                if (found.length > 5) {
                    els = found;
                    break;
                }
            }
            return els.map(el => el.innerText);
        }""")

        print(f"Cartes brutes Denner détectées : {len(cards_text)}")

        for raw in cards_text:
            item = parse_denner_card(raw.split('\n'))
            if item:
                key = (item['name'], item['price'])
                if key not in seen:
                    seen.add(key)
                    results.append(item)

        browser.close()

    with open("denner_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total Denner sauvegardé : {len(results)} offres dans denner_import.json")

if __name__ == "__main__":
    main()
