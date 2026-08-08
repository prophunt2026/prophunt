import requests
import time
from bs4 import BeautifulSoup

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

CATEGORIES = [
    "https://www.mubawab.tn/fr/sc/appartements-a-vendre",
    "https://www.mubawab.tn/fr/sc/villas-et-maisons-de-luxe-a-vendre",
    "https://www.mubawab.tn/fr/sc/maisons-a-vendre",
    "https://www.mubawab.tn/fr/sc/terrains-a-vendre",
]

OBJECTIF_ANNONCES       = 2800
MAX_PAGES_PAR_CATEGORIE = 150


# ==========================================
# HELPERS
# ==========================================

def _requete_avec_retry(url: str, tentatives: int = 3, delai_base: int = 3):
    for tentative in range(1, tentatives + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            if response.status_code == 200:
                return response
            if response.status_code == 429:
                print(f"Bloqué temporairement (429), pause... (tentative {tentative})")
                time.sleep(delai_base * tentative * 3)
                continue
            print(f"Status {response.status_code} pour {url} (tentative {tentative})")
            time.sleep(delai_base * tentative)
        except requests.exceptions.RequestException as e:
            print(f"Erreur réseau ({e}) - tentative {tentative}/{tentatives}")
            time.sleep(delai_base * tentative)
    print("Echec définitif après", tentatives, "tentatives :", url)
    return None


def _recuperer_liens_page(url: str) -> list:
    liens = []
    response = _requete_avec_retry(url)
    if response is None:
        return []

    print(f"\nURL : {url} | Status : {response.status_code}")
    soup = BeautifulSoup(response.text, "html.parser")
    annonces = soup.find_all("div", class_="contentBox")
    print(f"Blocs trouvés : {len(annonces)}")

    for annonce in annonces:
        titre = annonce.find("h2", class_="listingTit")
        if titre:
            lien = titre.find("a")
            if lien and lien.get("href") and "/a/" in lien["href"]:
                liens.append(lien["href"])

    print(f"Liens récupérés : {len(liens)}")
    return liens


# ==========================================
# FONCTION PUBLIQUE
# ==========================================

def scrape_links(data=None) -> list:
    """
    Parcourt toutes les catégories Mubawab et retourne la liste d'URLs
    d'annonces dédupliquées (sans écrire de fichier).

    Args:
        data: ignoré (convention pipeline — premier maillon reçoit None)

    Returns:
        list: liste d'URLs uniques (str)
    """
    tous_les_liens: list = []

    for base_url in CATEGORIES:
        print(f"\n#################################")
        print(f"CATÉGORIE : {base_url}")
        print(f"#################################")

        for page in range(1, MAX_PAGES_PAR_CATEGORIE + 1):
            url_page = base_url if page == 1 else f"{base_url}:p:{page}"
            liens = _recuperer_liens_page(url_page)

            if not liens:
                print("Page vide → fin de cette catégorie")
                break

            tous_les_liens.extend(liens)
            tous_les_liens = list(dict.fromkeys(tous_les_liens))  # dédup au fil de l'eau

            print(f"Total liens uniques : {len(tous_les_liens)} / objectif {OBJECTIF_ANNONCES}")

            if len(tous_les_liens) >= OBJECTIF_ANNONCES:
                print("Objectif atteint, arrêt de la collecte.")
                break

            time.sleep(2)

        if len(tous_les_liens) >= OBJECTIF_ANNONCES:
            break

    print(f"\n=================================")
    print(f"TOTAL LIENS UNIQUES : {len(tous_les_liens)}")
    print(f"=================================")

    return tous_les_liens
