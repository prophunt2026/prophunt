import requests
from bs4 import BeautifulSoup
import json
import html
import re
import time


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}



def construire_equipements_liste(data):

    features = data.get("features", {}) or {}
    services = data.get("services", {}) or {}
    equipements = []

    mapping_features = {
        "air_conditioning": "Climatisation",
        "elevator": "Ascenseur",
        "heating": "Chauffage",
        "garden": "Jardin",
        "concierge": "Concierge",
        "balconies": "Balcon",
        "terraces": "Terrasse",
    }

    for cle, label in mapping_features.items():

        valeur = features.get(cle)

        # Tecnocasa utilise "" ou "Non" pour dire "pas cet équipement"
        if valeur not in (None, "", "Non"):
            equipements.append(label)

    if features.get("car_places"):
        equipements.append(f"Garage ({features['car_places']} places)")

    # services{} contient des équipements plus détaillés (cuisine équipée,
    # vitrine, open-space...) organisés par sous-catégories "rooms"/"group"
    for section in ("rooms", "group"):

        section_data = services.get(section, {})
        items = section_data.values() if isinstance(section_data, dict) else section_data

        for item in items:

            label = item.get("nome-macro")

            if label:
                equipements.append(label)

    return equipements



def extraire_contact_agence(soup):

    tag = soup.find("estate-show-v2")

    if not tag or not tag.get(":estate"):
        return {}

    try:

        estate_data = json.loads(html.unescape(tag[":estate"]))

        agency = estate_data.get("agency", {}) or {}

        telephones = []

        if agency.get("phone"):
            telephones.append(agency["phone"])

        if agency.get("mobile") and agency.get("mobile") not in telephones:
            telephones.append(agency["mobile"])

        return {
            "telephone": telephones,
            "whatsapp": agency.get("whatsapp"),
            "email": agency.get("email"),
            "nom_agence": agency.get("name"),
            "adresse_agence": agency.get("address"),
        }

    except Exception as e:

        print("Erreur extraction contact :", e)

        return {}


# ==========================================================
# NOUVEAU : extraction des points d'intérêt à proximité
# ==========================================================
# Comme le contact, cette donnée est déjà en HTML statique (pas besoin de
# Selenium), dans le même attribut :estate, sous la clé "points_of_interest".
# Les catégories présentes varient selon l'annonce (school, pharmacy,
# hospital, market, shop, bar, restaurant, public_transport...), on prend
# donc tout ce qui est présent au lieu d'une liste figée.
CATEGORIES_PROXIMITE = {
    "school": "ecole",
    "pharmacy": "pharmacie",
    "hospital": "hopital",
    "market": "supermarche",
    "shop": "commerce",
    "bar": "bar",
    "restaurant": "restaurant",
    "public_transport": "transport_public",
}


def convertir_distance_en_metres(distance_texte):
    """'510 m' -> 510.0, '1,0 Km' -> 1000.0"""

    if not distance_texte:
        return None

    texte = distance_texte.strip().lower().replace(",", ".")

    match = re.match(r"([\d.]+)\s*(km|m)", texte)

    if not match:
        return None

    valeur, unite = match.groups()
    valeur = float(valeur)

    return valeur * 1000 if unite == "km" else valeur


def extraire_proximites(soup):

    tag = soup.find("estate-show-v2")

    if not tag or not tag.get(":estate"):
        return []

    try:

        estate_data = json.loads(html.unescape(tag[":estate"]))

        points_interet = estate_data.get("points_of_interest", {}) or {}

        proximites = []

        for cle_source, items in points_interet.items():

            categorie = CATEGORIES_PROXIMITE.get(cle_source, cle_source)

            for item in items or []:

                proximites.append({
                    "categorie": categorie,
                    "nom": item.get("name"),
                    "distance_m": convertir_distance_en_metres(item.get("distance")),
                })

        return proximites

    except Exception as e:

        print("Erreur extraction proximités :", e)

        return []


def extraire_images_completes(soup):
    """La liste 'images' du résumé (tecnocasa_links.json) ne contient que
    la photo de couverture. La galerie complète est dans le même attribut
    :estate que le contact/les proximités, sous media.images."""

    tag = soup.find("estate-show-v2")

    if not tag or not tag.get(":estate"):
        return []

    try:
        estate_data = json.loads(html.unescape(tag[":estate"]))

        images_media = estate_data.get("media", {}).get("images", []) or []

        urls = []

        for img in images_media:
            try:
                urls.append(img["url"]["detail"])
            except Exception:
                pass

        return urls

    except Exception as e:
        print("Erreur extraction galerie d'images :", e)
        return []


def scraper_annonce(data):

    url = data.get("detail_url")

    if not url:
        return None

    try:

        response = None

        for tentative in range(1, 4):

            try:
                response = requests.get(url, headers=headers, timeout=20)

                if response.status_code == 200:
                    break

                if response.status_code == 429:
                    print(f"Bloqué temporairement (429), pause longue... (tentative {tentative})")
                    time.sleep(9 * tentative)
                    continue

                print(f"Status {response.status_code} (tentative {tentative})")
                time.sleep(3 * tentative)

            except requests.exceptions.RequestException as e:
                print(f"Erreur réseau ({e}) - tentative {tentative}/3")
                time.sleep(3 * tentative)

        if response is None or response.status_code != 200:
            print("Echec définitif pour :", url)
            return None

        print("\nURL :", url)
        print("Status :", response.status_code)

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # =============================
        # TITRE
        # =============================

        titre = soup.find("h1")

        
        titre_text = (
            titre.get_text(strip=True)
            if titre and titre.get_text(strip=True)
            else data.get("title")
        )

        # =============================
        # DESCRIPTION
        # =============================

        description = ""

        desc = soup.find(
            "template",
            slot="estate-description"
        )

        if desc:
            description = desc.get_text(" ", strip=True)

        if not description:

            meta_desc = soup.find(
                "meta",
                property="og:description"
            )

            if meta_desc:
                description = meta_desc.get("content")

        # =============================
        # PRIX
        # =============================

        prix_text = data.get("price")
        prix = None

        if prix_text:

            nombres = re.findall(
                r"\d+",
                prix_text.replace(" ", "")
            )

            if nombres:
                prix = float(nombres[0])

        if prix is None:
            return None

        # =============================
        # IMAGES (galerie complète)
        # =============================

        images = extraire_images_completes(soup)

        if not images:
            # Repli : au moins la photo de couverture du résumé, au cas où
            # la galerie complète serait absente pour une annonce donnée.
            for img in data.get("images", []):
                try:
                    images.append(img["url"]["detail"])
                except Exception:
                    pass

        # =============================
        # SURFACE
        # =============================

        surface = None
        surface_text = data.get("surface")

        if surface_text:

            nombre = re.findall(r"\d+", surface_text)

            if nombre:
                surface = int(nombre[0])

        # =============================
        # VILLE
        # =============================

        ville = data.get("subtitle")

        # =============================
        # PIECES
        # =============================

        pieces = data.get("rooms")

        # =============================
        # AGENCE + CONTACT
        # =============================

        contact = extraire_contact_agence(soup)

        proximites = extraire_proximites(soup)

        agence = contact.get("nom_agence")

        if not agence and data.get("agency"):
            agence = data["agency"].get("id")

        # CORRECTION 2 (suite) : on appelle la nouvelle fonction au lieu
        # de chercher soup.find_all("div", class_="estate-feature")
        equipements = construire_equipements_liste(data)

        # =============================
        # RESULTAT FINAL
        # =============================

        annonce = {
            "titre": titre_text,
            "description": description,
            "url": url,
            "prix": prix,
            "devise": "TND",
            "ville": ville,
            "surface": surface,
            "pieces": pieces,
            "chambres": data.get("rooms"),
            "salles_de_bain": data.get("bathrooms"),
            "agence": agence,
            "images": images,
            "equipements": equipements,
            "telephone": contact.get("telephone", []),
            "whatsapp": contact.get("whatsapp"),
            "email": contact.get("email"),
            "adresse_agence": contact.get("adresse_agence"),
            "proximites": proximites,
        }

        return annonce

    except Exception as e:
        print("Erreur :", e)
        return None


# =====================================
# PROGRAMME PRINCIPAL
# =====================================

import os

SAUVEGARDE_TOUTES_LES = 25
FICHIER_SORTIE = "tecnocasa.json"

with open("tecnocasa_links.json", "r", encoding="utf-8") as f:
    annonces = json.load(f)

# Reprise : si tecnocasa.json existe déjà (run précédent interrompu), on
# repart de ce qui est déjà scrapé au lieu de tout refaire depuis zéro.
resultats = []
urls_deja_faites = set()

if os.path.exists(FICHIER_SORTIE):
    with open(FICHIER_SORTIE, encoding="utf-8") as f:
        resultats = json.load(f)
    urls_deja_faites = {r["url"] for r in resultats if r.get("url")}
    print(f"Reprise : {len(resultats)} annonces déjà présentes dans {FICHIER_SORTIE}")


def sauvegarder():
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=4)


a_faire = [a for a in annonces if a.get("detail_url") not in urls_deja_faites]

print(f"{len(a_faire)} annonces restant à scraper (sur {len(annonces)})")

for i, annonce in enumerate(a_faire, start=1):

    print("\n==========================")
    print(f"Annonce {i}/{len(a_faire)}")
    print("==========================")

    resultat = scraper_annonce(annonce)

    if resultat:
        resultats.append(resultat)
        print("OK ajoutée")
    else:
        print("Annonce ignorée")

    if i % SAUVEGARDE_TOUTES_LES == 0:
        sauvegarder()
        print(f"Sauvegarde intermédiaire ({len(resultats)} annonces au total)")

    time.sleep(1)

sauvegarder()

print("\n==========================")
print("SCRAPING TERMINE")
print("Annonces sauvegardées :", len(resultats))
print("Fichier créé :", FICHIER_SORTIE)