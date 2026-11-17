"""Récupère les actions Coop via Playwright et génère coop_import.json
au même format que migros_import.json.
"""
import json
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

URL_ACTIONS = "https://www.coop.ch/fr/actions/les-actions-du-moment/c/m_1011"


def categorie_coop(cat1):
    """Traduit l'attribut data-udo-cat1 de Coop vers les catégories de l'app."""
    c = (cat1 or "").lower()
    regles = [
        (("fruechte", "gemuese"), "Fruits et légumes"),
        (("fleisch", "fisch"), "Viande et poisson"),
        (("milch", "kaese", "eier"), "Produits laitiers"),
        (("brot", "backwaren"), "Boulangerie"),
        (("getraenke", "wein", "bier"), "Boissons et vins"),
        (("tiefkuehl",), "Surgelés"),
        (("drogerie", "kosmetik", "haushalt", "baby"), "Hygiène et maison"),
        (("tier",), "Animaux"),
    ]
    for mots, cat in regles:
        if any(m in c for m in mots):
            return cat
    return "Épicerie"


def parser_aria_label(label):
    """Extrait nom, quantité, prix promo et ancien prix depuis aria-label.
    Ex: 'Escalopes de chevreuil importées 2 pièces 200g 20% Promotion 9.00 CHF au lieu de 11.30 CHF'
    """
    # Recherche du bloc prix : "... X% Promotion Y.YY CHF au lieu de Z.ZZ CHF"
    m = re.search(
        r"(?:(\d+%)\s+)?Promotion\s+(\d+\.\d{2})\s*CHF(?:\s+au lieu de\s+(\d+\.\d{2})\s*CHF)?",
        label,
    )
    if not m:
        return None

    rabais = m.group(1) or ""
    price = float(m.group(2))
    old = float(m.group(3)) if m.group(3) else None

    # Tout ce qui précède le rabais/Promotion constitue le nom + la quantité
    avant_promo = label[: m.start()].strip()

    # Tente d'isoler la quantité à la fin (ex: '200g', '6x50cl', '1.5kg', '2 pièces')
    m_qty = re.search(
        r"(\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?)?\s*(?:g|kg|ml|cl|dl|l|pièces?|pce|rouleaux?))$",
        avant_promo,
        re.IGNORECASE,
    )
    if m_qty:
        qty = m_qty.group(1).strip()
        nom = avant_promo[: m_qty.start()].strip()
    else:
        qty = rabais
        nom = avant_promo

    return {"name": nom, "qty": qty, "price": price, "old": old}


def main():
    with sync_playwright() as p:
        # Lancement d'un navigateur Chromium furtif
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            locale="fr-CH",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        print("Chargement de la page des actions Coop...")
        page.goto(URL_ACTIONS, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)  # Laisse le temps aux carrousels lazy-load de charger

        # Défilement progressif jusqu'en bas pour déclencher le chargement de tous les rayons
        for _ in range(8):
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(1000)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    tuiles = soup.select("a.productTile[data-productid]")
    print(f"{len(tuiles)} cartes produits trouvées dans le HTML.")

    out = []
    vus = set()

    for a in tuiles:
        pid = a.get("data-productid")
        if pid in vus:
            continue
        vus.add(pid)

        label = a.get("aria-label", "")
        infos = parser_aria_label(label)
        if not infos or not infos["name"]:
            continue

        out.append({
            "store": "coop",
            "cat": categorie_coop(a.get("data-udo-cat1")),
            "name": infos["name"],
            "qty": infos["qty"],
            "price": infos["price"],
            "old": infos["old"],
            "valid": "",  # Coop affiche la validité globale de la semaine (mardi au lundi)
        })

    with open("coop_import.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"{len(out)} produits écrits dans coop_import.json")


if __name__ == "__main__":
    main()
