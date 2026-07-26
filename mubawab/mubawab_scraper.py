import requests
from bs4 import BeautifulSoup
from mubawab_details import scraper_annonce
from mubawab_telephone import creer_driver, scraper_telephone_mubawab
import json
import time

# ==========================================
# Configuration
# ==========================================

base_url = "https://www.mubawab.tn/fr/sc/appartements-a-vendre"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

# Nombre de pages à scraper
nombre_pages = 10

# ==========================================
# Fonction récupération des liens
# ==========================================

def recuperer_liens_page(url):

    liens = []

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        print("\n=================================")
        print("URL :", url)
        print("Status :", response.status_code)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        annonces = soup.find_all("div", class_="contentBox")

        print("Blocs annonces trouvés :", len(annonces))

        for annonce in annonces:

            titre = annonce.find("h2", class_="listingTit")

            if titre:

                lien = titre.find("a")

                if lien and lien.get("href"):

                    url_annonce = lien["href"]

                    # garder uniquement les vraies annonces
                    if "/a/" in url_annonce:

                        liens.append(url_annonce)

        print("Liens récupérés :", len(liens))

    except Exception as e:

        print("Erreur :", e)

    return liens


# ==========================================
# Récupération de tous les liens
# ==========================================

tous_les_liens = []

for page in range(1, nombre_pages + 1):

    if page == 1:
        url_page = base_url
    else:
        url_page = f"{base_url}:p:{page}"

    liens = recuperer_liens_page(url_page)

    tous_les_liens.extend(liens)

    time.sleep(2)

# Suppression des doublons

tous_les_liens = list(dict.fromkeys(tous_les_liens))

print("\n=================================")
print("Nombre total de liens uniques :", len(tous_les_liens))
print("=================================")

# ==========================================
# Scraping des détails (requests/BeautifulSoup)
# ==========================================

annonces_finales = []

for index, lien in enumerate(tous_les_liens, start=1):

    print("\n---------------------------------")
    print(f"Annonce {index}/{len(tous_les_liens)}")
    print(lien)

    try:

        annonce = scraper_annonce(lien)

        if annonce:

            # ignorer les annonces sans prix
            if annonce["prix"] is None:
                print("Prix absent -> ignorée")
                continue

            annonce.setdefault("telephone", [])

            annonces_finales.append(annonce)

            print("OK ajoutée")

        else:

            print("Annonce ignorée")

    except Exception as e:

        print("Erreur :", e)

    time.sleep(2)

# ==========================================
# NOUVEAU : second passage Selenium pour les téléphones
# ==========================================
# On réutilise un seul navigateur pour toutes les annonces au lieu d'en
# ouvrir un par annonce (beaucoup plus lent sinon).

print("\n=================================")
print("RECUPERATION DES TELEPHONES (Selenium)")
print("=================================")

driver = creer_driver(headless=True)

try:

    for index, annonce in enumerate(annonces_finales, start=1):

        print(f"\nTéléphone {index}/{len(annonces_finales)} - {annonce['url']}")

        telephones = scraper_telephone_mubawab(annonce["url"], driver)

        annonce["telephone"] = telephones

        print("Trouvé :", telephones if telephones else "aucun")

        time.sleep(1)

finally:
    driver.quit()

# ==========================================
# Sauvegarde JSON
# ==========================================

with open(
    "mubawab.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        annonces_finales,
        f,
        ensure_ascii=False,
        indent=4
    )

sans_telephone = sum(1 for a in annonces_finales if not a.get("telephone"))

print("\n=================================")
print("SCRAPING TERMINE")
print("Nombre d'annonces sauvegardées :", len(annonces_finales))
print("Annonces sans téléphone récupéré :", sans_telephone)
print("Fichier créé : mubawab.json")