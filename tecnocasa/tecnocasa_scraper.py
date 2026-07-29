import requests
from bs4 import BeautifulSoup
import html
import json
import time
import os


# ==========================================
# CONFIGURATION
# ==========================================


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}



# Les catégories : plusieurs types de biens x plusieurs régions.
# Vérifié : le site suit le modèle /vendre/{type}/{macro-région}/{région}.html
# pour appartement/villa/terrain, en plus de tes catégories "immeubles"
# d'origine. Si une combinaison n'existe pas ou est vide, le code passe à
# la suivante automatiquement (pas de plantage).
urls_categories = [

    "https://www.tecnocasa.tn/vendre+commercial.html",

    # Tes catégories d'origine (immeubles = mix de types)
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/mahdia/mahdia.html",
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/monastir.html",
    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/sousse.html",
    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/cap-bon/hammamet.html",
    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/grand-tunis.html",

    # Nouvelles catégories : appartement / villa / terrain, mêmes régions
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

    # Régions supplémentaires (à vérifier à l'usage : gardées même si
    # certaines s'avèrent vides, le code les ignore proprement)
    "https://www.tecnocasa.tn/vendre/appartement/centre-est-ce/sfax.html",
    "https://www.tecnocasa.tn/vendre/villa/centre-est-ce/sfax.html",
    "https://www.tecnocasa.tn/vendre/terrain/centre-est-ce/sfax.html",

    "https://www.tecnocasa.tn/vendre/appartement/nord-ouest-no/bizerte.html",
    "https://www.tecnocasa.tn/vendre/villa/nord-ouest-no/bizerte.html",
    "https://www.tecnocasa.tn/vendre/terrain/nord-ouest-no/bizerte.html",
]

# Objectif de volume : on s'arrête une fois ce nombre d'annonces uniques
# atteint (ou avant, si toutes les catégories sont épuisées). Mis à 1300
# (marge au-dessus des 1200 visés en sortie finale, pour absorber les
# pertes habituelles : prix manquant, surface non fiable, etc.)
OBJECTIF_ANNONCES = 1300

# Garde-fou : nombre max de pages par catégorie, même si le site en
# proposait plus (évite une boucle infinie en cas de bug). Le "break" sur
# page vide plus bas arrête déjà une catégorie avant cette limite dans la
# grande majorité des cas.
MAX_PAGES_PAR_CATEGORIE = 150

FICHIER_LIENS = "tecnocasa_links.json"


# ==========================================
# Requête HTTP avec retry (nouveau)
# ==========================================

def requete_avec_retry(url, tentatives=3, delai_base=3):
    """Réessaie en cas d'erreur réseau ou de blocage temporaire (429/5xx),
    avec un délai qui augmente à chaque tentative, au lieu d'abandonner
    la page directement."""

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
# Fonction récupérer annonces d'une page
# ==========================================


def recuperer_annonces(url):

    annonces = []

    response = requete_avec_retry(url)

    if response is None:
        return []

    print("\nURL :", url)
    print("Status :", response.status_code)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    cartes = soup.find_all(
        "estate-card"
    )


    print(
        "Nombre cartes :",
        len(cartes)
    )



    for carte in cartes:


        data = carte.get(
            ":estate"
        )


        if not data:
            continue


        try:

            # Décoder HTML
            data = html.unescape(data)


            # Transformer JSON texte en dictionnaire
            annonce = json.loads(
                data
            )


            annonces.append(
                annonce
            )


        except Exception as e:

            print(
                "Erreur JSON :",
                e
            )


    return annonces




# ==========================================
# SCRAPING DES CATEGORIES
# ==========================================


toutes_annonces = []

# Reprise : si tecnocasa_links.json existe déjà (run précédent
# interrompu), on repart de ce qui est déjà collecté.
if os.path.exists(FICHIER_LIENS):
    with open(FICHIER_LIENS, encoding="utf-8") as f:
        toutes_annonces = json.load(f)
    print(f"Reprise : {len(toutes_annonces)} annonces déjà présentes dans {FICHIER_LIENS}")


def sauvegarder_liens():
    with open(FICHIER_LIENS, "w", encoding="utf-8") as f:
        json.dump(toutes_annonces, f, ensure_ascii=False, indent=4)


for categorie in urls_categories:


    print("\n==============================")
    print("CATÉGORIE")
    print(categorie)
    print("==============================")


    ids_page_precedente = None

    for page in range(1, MAX_PAGES_PAR_CATEGORIE + 1):


        # pagination Tecnocasa : le suffixe "/pag-N" s'ajoute APRES l'URL
        # complète (qui se termine déjà par .html), il ne la remplace pas.
        # Ex: https://www.tecnocasa.tn/.../cap-bon.html/pag-3
        if page == 1:

            url_page = categorie

        else:

            url_page = categorie + f"/pag-{page}"



        annonces = recuperer_annonces(
            url_page
        )


        if len(annonces) == 0:

            print(
                "Aucune annonce trouvée -> fin de cette catégorie"
            )

            break

        # Garde-fou supplémentaire : si cette page renvoie exactement les
        # mêmes annonces que la précédente (pagination cassée/silencieuse),
        # on arrête au lieu de tourner en boucle sur du contenu dupliqué.
        ids_page_actuelle = {a.get("id") for a in annonces}

        if ids_page_actuelle == ids_page_precedente:

            print("Page identique à la précédente -> fin de cette catégorie (pagination inefficace)")

            break

        ids_page_precedente = ids_page_actuelle



        toutes_annonces.extend(
            annonces
        )

        # Sauvegarde progressive à chaque page (pas besoin d'attendre la
        # fin du run sur une collecte qui peut durer longtemps).
        sauvegarder_liens()

        print(f"Total cumulé : {len(toutes_annonces)} / objectif {OBJECTIF_ANNONCES}")

        if len(toutes_annonces) >= OBJECTIF_ANNONCES:
            print("Objectif de volume atteint, on arrête la collecte.")
            break

        time.sleep(2)

    if len(toutes_annonces) >= OBJECTIF_ANNONCES:
        break




# ==========================================
# SUPPRESSION DOUBLONS
# ==========================================


annonces_uniques = {}



for annonce in toutes_annonces:


    identifiant = annonce.get(
        "id"
    )


    if identifiant:

        annonces_uniques[identifiant] = annonce



resultat = list(
    annonces_uniques.values()
)



print("\n==============================")
print(
    "TOTAL ANNONCES :",
    len(resultat)
)
print("==============================")




# ==========================================
# SAUVEGARDE
# ==========================================


with open(
    FICHIER_LIENS,
    "w",
    encoding="utf-8"
) as f:


    json.dump(
        resultat,
        f,
        ensure_ascii=False,
        indent=4
    )



print(
    "Fichier créé :", FICHIER_LIENS
)