import requests
from bs4 import BeautifulSoup
import json


def scraper_annonce(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        )
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code != 200:

            print(
                "Erreur HTTP",
                response.status_code
            )

            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # ==============================
        # JSON-LD
        # ==============================

        script_json = soup.find(
            "script",
            type="application/ld+json"
        )

        if script_json is None:

            print(
                "JSON-LD absent"
            )

            return None

        data = json.loads(
            script_json.string
        )

        # ==============================
        # Equipements
        # ==============================

        equipements = []

        blocs = soup.find_all(
            "div",
            class_="adFeature"
        )

        for bloc in blocs:

            textes = [

                p.get_text(strip=True)

                for p in bloc.find_all("p")

            ]

            if textes:

                equipements.append(
                    textes
                )

        # ==============================
        # Dictionnaire final
        # ==============================

        annonce = {

            "titre":
                data.get("name"),

            "description":
                data.get("description"),

            "url":
                data.get("url"),

            "prix":
                data.get("offers", {})
                .get("price"),

            "devise":
                data.get("offers", {})
                .get("priceCurrency"),

            "ville":
                data.get("itemOffered", {})
                .get("address", {})
                .get("addressLocality"),

            "surface":
                data.get("itemOffered", {})
                .get("floorSize", {})
                .get("value"),

            "pieces":
                data.get("itemOffered", {})
                .get("numberOfRooms"),

            "chambres":
                data.get("itemOffered", {})
                .get("numberOfBedrooms"),

            "salles_de_bain":
                data.get("itemOffered", {})
                .get("numberOfBathroomsTotal"),

            "agence":
                data.get("seller", {})
                .get("name"),

            "images":
                data.get("image"),

            "equipements":
                equipements,

            # Rempli plus tard par mubawab_telephone.py (Selenium) :
            # le numéro n'est jamais présent dans ce HTML statique.
            "telephone":
                [],

        }

        return annonce

    except Exception as e:

        print(
            "Erreur scraping détail :",
            e
        )

        return None