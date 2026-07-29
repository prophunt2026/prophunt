import requests
from bs4 import BeautifulSoup
from mubawab_details import scraper_annonce
from mubawab_telephone import creer_driver, scraper_telephone_mubawab
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
import json
import time
import os

# ==========================================
# Configuration
# ==========================================

# Plusieurs catégories pour couvrir plus de types de biens.
# "appartements-a-vendre" à elle seule contient ~4976 annonces sur le site
# (vérifié dans page_mubawab.html), donc largement de quoi dépasser 1000.
categories = [
    "https://www.mubawab.tn/fr/sc/appartements-a-vendre",
    "https://www.mubawab.tn/fr/sc/villas-et-maisons-de-luxe-a-vendre",
    "https://www.mubawab.tn/fr/sc/maisons-a-vendre",
    "https://www.mubawab.tn/fr/sc/terrains-a-vendre",
]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

# Objectif de volume : on s'arrête une fois ce nombre d'annonces uniques
# atteint (ou avant, si toutes les catégories sont épuisées).
OBJECTIF_ANNONCES = 2800

# Garde-fou : on ne dépasse jamais ce nombre de pages par catégorie, même
# si le site en propose plus (évite une boucle infinie en cas de bug).
MAX_PAGES_PAR_CATEGORIE = 150

# Sauvegarde intermédiaire tous les N annonces (pour ne rien perdre si
# le script plante en cours de route sur un run long).
SAUVEGARDE_TOUTES_LES = 25

FICHIER_LIENS = "mubawab_liens.json"
FICHIER_SORTIE = "mubawab.json"


# ==========================================
# Requête HTTP avec retry (nouveau)
# ==========================================

def requete_avec_retry(url, tentatives=3, delai_base=3):
    """Réessaie en cas d'erreur réseau ou de blocage temporaire (429/5xx),
    avec un délai qui augmente à chaque tentative, au lieu d'abandonner
    l'annonce/la page directement."""

    for tentative in range(1, tentatives + 1):

        try:
            response = requests.get(url, headers=headers, timeout=20)

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                print(f"Bloqué temporairement (429), pause longue... (tentative {tentative})")
                time.sleep(delai_base * tentative * 3)
                continue

            print(f"Status {response.status_code} pour {url} (tentative {tentative})")
            time.sleep(delai_base * tentative)

        except requests.exceptions.RequestException as e:
            print(f"Erreur réseau ({e}) - tentative {tentative}/{tentatives}")
            time.sleep(delai_base * tentative)

    print("Echec définitif après", tentatives, "tentatives :", url)
    return None


# ==========================================
# Fonction récupération des liens
# ==========================================

def recuperer_liens_page(url):

    liens = []

    response = requete_avec_retry(url)

    if response is None:
        return []

    print("\n=================================")
    print("URL :", url)
    print("Status :", response.status_code)

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

    return liens


# ==========================================
# Récupération de tous les liens (plusieurs catégories, pagination dynamique)
# ==========================================

tous_les_liens = []

for base_url in categories:

    print("\n#################################")
    print("CATEGORIE :", base_url)
    print("#################################")

    for page in range(1, MAX_PAGES_PAR_CATEGORIE + 1):

        if page == 1:
            url_page = base_url
        else:
            url_page = f"{base_url}:p:{page}"

        liens = recuperer_liens_page(url_page)

        # Pagination dynamique : si une page ne renvoie plus rien, on
        # arrête cette catégorie (pas la peine de continuer à taper dans
        # des pages vides) au lieu d'un nombre de pages fixe.
        if len(liens) == 0:
            print("Page vide -> fin de cette catégorie")
            break

        tous_les_liens.extend(liens)

        # Dédoublonnage au fil de l'eau + vérif objectif
        tous_les_liens = list(dict.fromkeys(tous_les_liens))

        print(f"Total liens uniques cumulés : {len(tous_les_liens)} / objectif {OBJECTIF_ANNONCES}")

        if len(tous_les_liens) >= OBJECTIF_ANNONCES:
            print("Objectif de volume atteint pour les liens, on arrête la collecte de liens.")
            break

        time.sleep(2)

    if len(tous_les_liens) >= OBJECTIF_ANNONCES:
        break

print("\n=================================")
print("Nombre total de liens uniques :", len(tous_les_liens))
print("=================================")

with open(FICHIER_LIENS, "w", encoding="utf-8") as f:
    json.dump(tous_les_liens, f, ensure_ascii=False, indent=2)

# ==========================================
# Scraping des détails (requests/BeautifulSoup)
# ==========================================

# Reprise : si mubawab.json existe déjà (run précédent interrompu), on
# repart de ce qui est déjà scrapé au lieu de tout refaire depuis zéro.
annonces_finales = []
urls_deja_faites = set()

if os.path.exists(FICHIER_SORTIE):
    with open(FICHIER_SORTIE, encoding="utf-8") as f:
        annonces_finales = json.load(f)
    urls_deja_faites = {a["url"] for a in annonces_finales if a.get("url")}
    print(f"Reprise : {len(annonces_finales)} annonces déjà présentes dans {FICHIER_SORTIE}")


def sauvegarder():
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(annonces_finales, f, ensure_ascii=False, indent=4)


liens_a_faire = [lien for lien in tous_les_liens if lien not in urls_deja_faites]

print(f"{len(liens_a_faire)} annonces restant à scraper (sur {len(tous_les_liens)})")

for index, lien in enumerate(liens_a_faire, start=1):

    print("\n---------------------------------")
    print(f"Annonce {index}/{len(liens_a_faire)}")
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

    # Sauvegarde progressive : on n'attend pas la toute fin du run pour
    # écrire sur le disque, sinon un plantage à l'annonce 800/1000 fait
    # tout perdre.
    if index % SAUVEGARDE_TOUTES_LES == 0:
        sauvegarder()
        print(f"Sauvegarde intermédiaire ({len(annonces_finales)} annonces au total)")

    time.sleep(2)

sauvegarder()

# ==========================================
# Second passage Selenium pour les téléphones
# ==========================================
# On réutilise un seul navigateur pour toutes les annonces au lieu d'en
# ouvrir un par annonce (beaucoup plus lent sinon).
# On ne refait pas le téléphone des annonces qui en ont déjà un (reprise).

print("\n=================================")
print("RECUPERATION DES TELEPHONES (Selenium)")
print("=================================")

a_faire_telephone = [a for a in annonces_finales if not a.get("telephone")]

print(f"{len(a_faire_telephone)} annonces sans téléphone à traiter (sur {len(annonces_finales)})")

# Redémarrage préventif périodique (évite l'accumulation de mémoire sur un
# run très long) + redémarrage automatique si Chrome plante en cours de route.
REDEMARRAGE_DRIVER_TOUTES_LES = 200

driver = creer_driver(headless=True)

try:

    for index, annonce in enumerate(a_faire_telephone, start=1):

        print(f"\nTéléphone {index}/{len(a_faire_telephone)} - {annonce['url']}")

        try:
            telephones = scraper_telephone_mubawab(annonce["url"], driver)

        except (InvalidSessionIdException, WebDriverException) as e:
            # Chrome a planté / la session est morte : on redémarre un
            # navigateur frais et on réessaie cette annonce une fois,
            # au lieu de rester bloqué avec une session morte pour tout
            # le reste du run.
            print(f"Session Chrome perdue ({e.__class__.__name__}), redémarrage du navigateur...")

            try:
                driver.quit()
            except Exception:
                pass

            driver = creer_driver(headless=True)

            try:
                telephones = scraper_telephone_mubawab(annonce["url"], driver)
            except Exception as e2:
                print("Echec même après redémarrage :", e2)
                telephones = []

        annonce["telephone"] = telephones

        print("Trouvé :", telephones if telephones else "aucun")

        if index % SAUVEGARDE_TOUTES_LES == 0:
            sauvegarder()
            print("Sauvegarde intermédiaire (téléphones)")

        # Redémarrage préventif : Chrome accumule de la mémoire sur des
        # milliers de pages chargées d'affilée, mieux vaut repartir sur
        # un navigateur frais régulièrement plutôt que d'attendre le crash.
        if index % REDEMARRAGE_DRIVER_TOUTES_LES == 0:
            print(f"Redémarrage préventif du navigateur (après {index} annonces)")
            driver.quit()
            driver = creer_driver(headless=True)

        time.sleep(1)

finally:
    try:
        driver.quit()
    except Exception:
        pass

# ==========================================
# Sauvegarde finale
# ==========================================

sauvegarder()

sans_telephone = sum(1 for a in annonces_finales if not a.get("telephone"))

print("\n=================================")
print("SCRAPING TERMINE")
print("Nombre d'annonces sauvegardées :", len(annonces_finales))
print("Annonces sans téléphone récupéré :", sans_telephone)
print("Fichier créé :", FICHIER_SORTIE)