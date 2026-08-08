import requests
from bs4 import BeautifulSoup
import html
import json
import time


# ==========================================
# CONFIGURATION
# ==========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

URLS_CATEGORIES = [
    "https://www.tecnocasa.tn/vendre+commercial.html",
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/mahdia/mahdia.html",
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/monastir.html",
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/sousse.html",
    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/cap-bon/hammamet.html",
    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/grand-tunis.html",
    "https://www.tecnocasa.tn/vendre/appartement/nord-est-ne/grand-tunis.html",
    "https://www.tecnocasa.tn/vendre/villa/nord-est-ne/grand-tunis.html",
    "https://www.tecnocasa.tn/vendre/terrain/nord-est-ne/grand-tunis.html",
    "https://www.tecnocasa.tn/vendre/appartement/nord-est-ne/cap-bon.html",
    "https://www.tecnocasa.tn/vendre/villa/nord-est-ne/cap-bon.html",
    "https://www.tecnocasa.tn/vendre/terrain/nord-est-ne/cap-bon.html",
    "https://www.tecnocasa.tn/vendre/appartement/nord-est-ne/cap-bon/nabeul.html",
    "https://www.tecnocasa.tn/vendre/appartement/centre-est-ce/mahdia.html",
    "https://www.tecnocasa.tn/vendre/villa/centre-est-ce/mahdia.html",
    "https://www.tecnocasa.tn/vendre/terrain/centre-est-ce/mahdia.html",
    "https://www.tecnocasa.tn/vendre/appartement/centre-est-ce/monastir.html",
    "https://www.tecnocasa.tn/vendre/villa/centre-est-ce/monastir.html",
    "https://www.tecnocasa.tn/vendre/terrain/centre-est-ce/monastir.html",
    "https://www.tecnocasa.tn/vendre/appartement/centre-est-ce/sousse.html",
    "https://www.tecnocasa.tn/vendre/villa/centre-est-ce/sousse.html",
    "https://www.tecnocasa.tn/vendre/terrain/centre-est-ce/sousse.html",
    "https://www.tecnocasa.tn/vendre/appartement/centre-est-ce/sfax.html",
    "https://www.tecnocasa.tn/vendre/villa/centre-est-ce/sfax.html",
    "https://www.tecnocasa.tn/vendre/terrain/centre-est-ce/sfax.html",
    "https://www.tecnocasa.tn/vendre/appartement/nord-ouest-no/bizerte.html",
    "https://www.tecnocasa.tn/vendre/villa/nord-ouest-no/bizerte.html",
    "https://www.tecnocasa.tn/vendre/terrain/nord-ouest-no/bizerte.html",
]

OBJECTIF_ANNONCES = 5
MAX_PAGES_PAR_CATEGORIE = 150


# ==========================================
# REQUÊTE HTTP AVEC RETRY
# ==========================================

def _requete_avec_retry(url: str, tentatives: int = 3, delai_base: int = 3):
    """Réessaie en cas d'erreur réseau ou de blocage temporaire (429/5xx)."""
    for tentative in range(1, tentatives + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)

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
# RÉCUPÉRATION DES ANNONCES D'UNE PAGE
# ==========================================

def _recuperer_annonces_page(url: str) -> list:
    """Retourne la liste des annonces brutes présentes sur une page de catégorie."""
    annonces = []

    response = _requete_avec_retry(url)
    if response is None:
        return []

    print("\nURL :", url)
    print("Status :", response.status_code)

    soup = BeautifulSoup(response.text, "html.parser")
    cartes = soup.find_all("estate-card")

    print("Nombre cartes :", len(cartes))

    for carte in cartes:
        data = carte.get(":estate")
        if not data:
            continue
        try:
            data = html.unescape(data)
            annonce = json.loads(data)
            annonces.append(annonce)
        except Exception as e:
            print("Erreur JSON :", e)

    return annonces


# ==========================================
# FONCTION PUBLIQUE
# ==========================================

def scrape_links(data=None) -> list:
   
    toutes_annonces = []

    for categorie in URLS_CATEGORIES:
        print("\n==============================")
        print("CATÉGORIE :", categorie)
        print("==============================")

        ids_page_precedente = None

        for page in range(1, MAX_PAGES_PAR_CATEGORIE + 1):
            url_page = categorie if page == 1 else f"{categorie}/pag-{page}"

            annonces = _recuperer_annonces_page(url_page)

            if not annonces:
                print("Aucune annonce trouvée -> fin de cette catégorie")
                break

            # Garde-fou : pagination silencieuse (même contenu répété)
            ids_page_actuelle = {a.get("id") for a in annonces}
            if ids_page_actuelle == ids_page_precedente:
                print("Page identique à la précédente -> fin de cette catégorie")
                break
            ids_page_precedente = ids_page_actuelle

            toutes_annonces.extend(annonces)

            print(f"Total cumulé : {len(toutes_annonces)} / objectif {OBJECTIF_ANNONCES}")

            if len(toutes_annonces) >= OBJECTIF_ANNONCES:
                print("Objectif de volume atteint, arrêt de la collecte.")
                break

            time.sleep(2)

        if len(toutes_annonces) >= OBJECTIF_ANNONCES:
            break

    # Déduplication par id
    annonces_uniques = {a.get("id"): a for a in toutes_annonces if a.get("id")}
    resultat = list(annonces_uniques.values())

    print("\n==============================")
    print("TOTAL ANNONCES UNIQUES :", len(resultat))
    print("==============================")

    return resultat
