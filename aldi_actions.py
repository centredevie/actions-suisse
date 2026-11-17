import json
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

def get_target_mondays():
    today = datetime.now()
    # Lundi de cette semaine et lundi de la semaine prochaine
    monday_this = today - timedelta(days=today.weekday())
    monday_next = monday_this + timedelta(days=7)
    return [monday_this.strftime("%Y-%m-%d"), monday_next.strftime("%Y-%m-%d")]

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
    if any(k in t for k in ['vin', 'bière', 'eau', 'jus', 'sirop', 'thé', 'café', 'coca', 'soda', 'prosecco', 'champagne', 'amarone', 'merlot', 'pinot', 'chardonnay', 'boisson']):
        return 'Boissons et vins'
    if any(k in t for k in ['surgelé', 'glace', 'pizza', 'frites', 'bâtonnets']):
        return 'Surgelés'
    if any(k in t for k in ['lessive', 'savon', 'shampoing', 'gel douche', 'dentifrice', 'papier', 'mouchoir', 'nettoyant', 'vaisselle', 'crème mains', 'déodorant']):
        return 'Hygiène et maison'
    if any(k in t for k in ['chien', 'chat', 'croquette', 'litière']):
        return 'Animaux'
    if any(k in t for k in ['caquelon', 'poêle', 'casserole', 'lampe', 'vêtement', 'pantalon', 'veste', 'chaussure', 'chaussette', 'jouet', 'outil', 'plante', 'fleur', 'bougie', 'déco', 'grès']):
        return 'Bazar et loisirs'
    return 'Épicerie'

def parse_card_lines(lines, default_valid):
    # Nettoyer les lignes vides et boutons parasites
    clean = [l.strip() for l in lines if l.strip() and l.strip().lower() not in ['ajouter à la liste', 'en savoir plus', 'nouveau']]
    if not clean:
        return None

    price = None
    old_price = None
    qty = ""
    valid = default_valid
    name_parts = []

    for line in clean:
        # Extraction date de validité
        if line.lower().startswith('à partir du') or re.search(r'\d{2}\.\d{2}', line):
            valid = line
            continue

        # Extraction du prix principal (ex: "CHF 14.99" ou "14.99")
        m_price = re.search(r'(?:CHF\s*)?(\d+\.\d{2})', line)
        if m_price and ('chf' in line.lower() or re.match(r'^\d+\.\d{2}$', line)):
            val = float(m_price.group(1))
            if price is None:
                price = val
            elif val > price and old_price is None:
                old_price = val
            continue

        # Extraction de l'ancien prix barré ou réduction (ex: "-25%" ou "au lieu de 19.99")
        m_old = re.search(r'(?:au lieu de|statt)\s*(?:CHF\s*)?(\d+\.\d{2})', line, re.I)
        if m_old:
            old_price = float(m_old.group(1))
            continue

        if re.match(r'^-\d+\s*%$', line):
            continue

        # Extraction de la quantité (ex: "75 cl", "1 pièce", "500 g", "1 kg")
        if re.search(r'\b(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pièce|pièces|pces|x)\b)', line, re.I) and len(line) < 35:
            qty = line
            continue

        name_parts.append(line)

    if price is None or not name_parts:
        return None

    name = " - ".join(name_parts[:2])
    return {
        "store": "aldi",
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

        for date_str in get_target_mondays():
            url = f"https://www.aldi-suisse.ch/fr/actions/{date_str}"
            print(f"Chargement Aldi : {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2000)

                # Défilement progressif pour charger les 194 produits (lazy loading)
                for _ in range(15):
                    page.mouse.wheel(0, 1500)
                    page.wait_for_timeout(400)

                # Extraction des blocs liens contenant CHF
                cards_text = page.evaluate("""() => {
                    const anchors = Array.from(document.querySelectorAll('main a'));
                    return anchors
                        .filter(a => a.innerText && a.innerText.includes('CHF') && a.querySelector('img'))
                        .map(a => a.innerText);
                }""")

                print(f"  -> {len(cards_text)} cartes brutes détectées pour {date_str}")
                dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
                default_valid = f"dès le {dt_obj.strftime('%d.%m')}"

                for raw in cards_text:
                    item = parse_card_lines(raw.split('\n'), default_valid)
                    if item:
                        key = (item['name'], item['price'])
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
            except Exception as e:
                print(f"Erreur sur {url} : {e}")

        browser.close()

    with open("aldi_import.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total Aldi sauvegardé : {len(results)} offres dans aldi_import.json")

if __name__ == "__main__":
    main()
