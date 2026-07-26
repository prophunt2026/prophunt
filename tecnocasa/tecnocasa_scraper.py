import requests
from bs4 import BeautifulSoup
import html
import json
import time


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



# Les catégories trouvées
urls_categories = [

    "https://www.tecnocasa.tn/vendre+commercial.html",

    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/mahdia/mahdia.html",

    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/monastir.html",

    "https://www.tecnocasa.tn/vendre/immeubles/centre-est-ce/sousse.html",

    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/cap-bon/hammamet.html",

    "https://www.tecnocasa.tn/vendre/immeubles/nord-est-ne/grand-tunis.html"

]



# Nombre de pages
nombre_pages = 10



# ==========================================
# Fonction récupérer annonces d'une page
# ==========================================


def recuperer_annonces(url):

    annonces = []


    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )


        print("\nURL :", url)
        print("Status :", response.status_code)


        if response.status_code != 200:
            return []


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



    except Exception as e:

        print(
            "Erreur page :",
            e
        )


    return annonces




# ==========================================
# SCRAPING DES CATEGORIES
# ==========================================


toutes_annonces = []



for categorie in urls_categories:


    print("\n==============================")
    print("CATÉGORIE")
    print(categorie)
    print("==============================")


    for page in range(1, nombre_pages + 1):


        # pagination Tecnocasa
        if page == 1:

            url_page = categorie

        else:

            url_page = categorie + f"?page={page}"



        annonces = recuperer_annonces(
            url_page
        )


        if len(annonces) == 0:

            print(
                "Aucune annonce trouvée"
            )

            break



        toutes_annonces.extend(
            annonces
        )


        time.sleep(2)




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
    "tecnocasa_links.json",
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
    "Fichier créé : tecnocasa_links.json"
)