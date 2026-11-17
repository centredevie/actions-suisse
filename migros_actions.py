"""Récupère les actions Migros et écrit deux fichiers:
- migros_brut.json : réponse brute de l'API (pour vérifier les champs)
- migros_import.json : à coller dans « Ajouter ou importer des actions » de l'app
À lancer chez vous: python3 migros_actions.py
"""
import json
import requests

import sys


def verifie(r, etape):
    """Affiche le statut et un extrait de la réponse, puis s'arrête si erreur."""
    print(f"[{etape}] HTTP {r.status_code}, {len(r.content)} octets")
    if not r.ok:
        print("Début de la réponse:", r.text[:500].replace("\n", " "))
        sys.exit(1)


session = requests.Session()
verifie(session.get("https://www.migros.ch/fr", timeout=30,
                    headers={"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}),
        "page d'accueil")

headers = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "migros-language": "fr",
    "origin": "https://www.migros.ch",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# Jeton invité: l'API répond 401 sans le header "leshopch".
# On essaie GET puis POST sur l'endpoint invité, et on cherche le jeton
# dans les headers de la réponse, puis dans le corps JSON.
# Seuls les NOMS des champs sont affichés, jamais la valeur du jeton.
url_guest = "https://www.migros.ch/authentication/public/v1/api/guest?authorizationNeeded=false"
token = None
for methode in ("GET", "POST"):
    g = session.request(methode, url_guest, headers=headers, timeout=30)
    print(f"[jeton invité {methode}] HTTP {g.status_code}, headers: {sorted(g.headers.keys())}")
    token = g.headers.get("leshopch")
    if not token:
        try:
            corps = g.json()
            print("   clés du corps JSON:", list(corps.keys()) if isinstance(corps, dict) else type(corps))
            if isinstance(corps, dict):
                token = corps.get("leshopch") or corps.get("token") or corps.get("accessToken")
        except ValueError:
            pass
    if token:
        break
if not token:
    print("Aucun jeton trouvé: voir les noms de headers ci-dessus.")
    sys.exit(1)
headers["leshopch"] = token
print("Jeton invité obtenu.")

url_search = "https://www.migros.ch/product-display/public/web/v3/products/promotion/search"
payload_search = {
    "storeType": "OFFLINE", "period": "CURRENT", "filters": {},
    "sortFields": ["categoryLevel"], "sortOrder": "asc",
    "from": 0, "until": 300, "region": "national", "warehouse": "1",
}
res = session.post(url_search, json=payload_search, headers=headers, timeout=30)
verifie(res, "recherche des actions")
res = res.json()
print("Clés de la réponse:", list(res.keys()))
ids = [i["id"] for i in res.get("items", [])]
print(f"{len(ids)} actions trouvées")

url_cards = "https://www.migros.ch/product-display/public/v4/product-cards"
cards = []
for i in range(0, len(ids), 50):
    payload = {
        "offerFilter": {"storeType": "OFFLINE", "region": "national",
                        "ongoingOfferDate": res["startDate"] + "T00:00:00"},
        "productFilter": {"uids": ids[i:i + 50]},
    }
    r = session.post(url_cards, json=payload, headers=headers, timeout=30)
    verifie(r, f"détails {i}-{i + 50}")
    cards.extend(r.json())

with open("migros_brut.json", "w", encoding="utf-8") as f:
    json.dump(cards, f, ensure_ascii=False, indent=1)

if cards:
    premier = {k: v for k, v in cards[0].items() if k not in ("breadcrumb",)}
    texte = json.dumps(premier, ensure_ascii=False)
    print("=== PREMIER PRODUIT (sans breadcrumb) ===")
    print(texte[:3000])
    print("=== FIN ===")


def categorie(c):
    """Catégorie de l'app, déduite du 1er niveau du breadcrumb Migros."""
    bc = c.get("breadcrumb") or []
    haut = (bc[0].get("name", "") if bc else "").lower()
    regles = [
        (("fruits", "légumes"), "Fruits et légumes"),
        (("viande", "poisson", "charcuterie"), "Viande et poisson"),
        (("lait", "œuf", "oeuf", "fromage", "yogourt"), "Produits laitiers"),
        (("pain", "boulangerie", "pâtisserie"), "Boulangerie"),
        (("boisson", "vin", "bière", "eau", "spiritueux"), "Boissons et vins"),
        (("surgelé", "glace"), "Surgelés"),
        (("ménage", "hygiène", "beauté", "soins", "bébé", "nettoyage", "lessive"), "Hygiène et maison"),
        (("animaux", "chien", "chat"), "Animaux"),
        (("bricolage", "jardin", "loisirs", "jouet", "électronique", "mode", "sport", "maison"), "Bazar et loisirs"),
    ]
    for mots, cat in regles:
        if any(m in haut for m in mots):
            return cat
    return "Épicerie"


def pick(d, *paths):
    """Premier champ trouvé parmi plusieurs chemins possibles (a.b.c)."""
    for p in paths:
        v = d
        for k in p.split("."):
            v = v.get(k) if isinstance(v, dict) else None
        if v not in (None, ""):
            return v
    return None


out = []
for c in cards:
    price = pick(c, "offer.price.value", "offer.price", "price.value", "price")
    old = pick(c, "offer.price.base", "offer.basePrice", "price.base", "basePrice", "offer.originalPrice")
    name = pick(c, "name", "title")
    if not name or not isinstance(price, (int, float)):
        continue
    out.append({
        "store": "migros",
        "cat": categorie(c),
        "name": name,
        "qty": pick(c, "versionInfo", "packageSize", "quantity", "unit") or "",
        "price": price,
        "old": old if isinstance(old, (int, float)) else None,
        "valid": res.get("startDate", "") + " → " + res.get("endDate", ""),
    })

with open("migros_import.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"{len(out)} produits écrits dans migros_import.json (sur {len(cards)} reçus)")
