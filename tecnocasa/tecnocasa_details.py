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


def scraper_annonce(data):

    url = data.get("detail_url")

    if not url:
        return None

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        print("\nURL :", url)
        print("Status :", response.status_code)

        if response.status_code != 200:
            return None

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
        # IMAGE
        # =============================

        images = []

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
        }

        return annonce

    except Exception as e:
        print("Erreur :", e)
        return None


# =====================================
# PROGRAMME PRINCIPAL
# =====================================

with open("tecnocasa_links.json", "r", encoding="utf-8") as f:
    annonces = json.load(f)

resultats = []
total = len(annonces)

for i, annonce in enumerate(annonces, start=1):

    print("\n==========================")
    print(f"Annonce {i}/{total}")
    print("==========================")

    resultat = scraper_annonce(annonce)

    if resultat:
        resultats.append(resultat)
        print("OK ajoutée")
    else:
        print("Annonce ignorée")

    time.sleep(1)

with open("tecnocasa.json", "w", encoding="utf-8") as f:
    json.dump(resultats, f, ensure_ascii=False, indent=4)

print("\n==========================")
print("SCRAPING TERMINE")
print("Annonces sauvegardées :", len(resultats))
print("Fichier créé : tecnocasa.json")