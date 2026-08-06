import requests
from bs4 import BeautifulSoup
import json
import html
import re
import time


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}


# ==========================================
# HELPERS (logique inchangée)
# ==========================================

def _construire_equipements_liste(data: dict) -> list:
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
        if valeur not in (None, "", "Non"):
            equipements.append(label)

    if features.get("car_places"):
        equipements.append(f"Garage ({features['car_places']} places)")

    for section in ("rooms", "group"):
        section_data = services.get(section, {})
        items = section_data.values() if isinstance(section_data, dict) else section_data
        for item in items:
            label = item.get("nome-macro")
            if label:
                equipements.append(label)

    return equipements


def _extraire_contact_agence(soup) -> dict:
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


def _convertir_distance_en_metres(distance_texte) -> float | None:
    """'510 m' -> 510.0 · '1,0 Km' -> 1000.0"""
    if not distance_texte:
        return None
    texte = distance_texte.strip().lower().replace(",", ".")
    match = re.match(r"([\d.]+)\s*(km|m)", texte)
    if not match:
        return None
    valeur, unite = match.groups()
    return float(valeur) * 1000 if unite == "km" else float(valeur)


def _extraire_proximites(soup) -> list:
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
                    "distance_m": _convertir_distance_en_metres(item.get("distance")),
                })
        return proximites
    except Exception as e:
        print("Erreur extraction proximités :", e)
        return []


def _extraire_images_completes(soup) -> list:
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


def _scraper_annonce(data: dict) -> dict | None:
    """Scrape la page de détail d'une annonce et retourne un dict enrichi."""
    url = data.get("detail_url")
    if not url:
        return None

    try:
        response = None
        for tentative in range(1, 4):
            try:
                response = requests.get(url, headers=HEADERS, timeout=20)
                if response.status_code == 200:
                    break
                if response.status_code == 429:
                    print(f"Bloqué temporairement (429), pause... (tentative {tentative})")
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

        soup = BeautifulSoup(response.text, "html.parser")

        # Titre
        titre = soup.find("h1")
        titre_text = (
            titre.get_text(strip=True)
            if titre and titre.get_text(strip=True)
            else data.get("title")
        )

        # Description
        description = ""
        desc = soup.find("template", slot="estate-description")
        if desc:
            description = desc.get_text(" ", strip=True)
        if not description:
            meta_desc = soup.find("meta", property="og:description")
            if meta_desc:
                description = meta_desc.get("content")

        # Prix
        prix_text = data.get("price")
        prix = None
        if prix_text:
            nombres = re.findall(r"\d+", prix_text.replace(" ", ""))
            if nombres:
                prix = float(nombres[0])
        if prix is None:
            return None

        # Images
        images = _extraire_images_completes(soup)
        if not images:
            for img in data.get("images", []):
                try:
                    images.append(img["url"]["detail"])
                except Exception:
                    pass

        # Surface
        surface = None
        surface_text = data.get("surface")
        if surface_text:
            nombre = re.findall(r"\d+", surface_text)
            if nombre:
                surface = int(nombre[0])

        # Contact + proximités + équipements
        contact = _extraire_contact_agence(soup)
        proximites = _extraire_proximites(soup)
        equipements = _construire_equipements_liste(data)

        agence = contact.get("nom_agence")
        if not agence and data.get("agency"):
            agence = data["agency"].get("id")

        return {
            "titre": titre_text,
            "description": description,
            "url": url,
            "prix": prix,
            "devise": "TND",
            "ville": data.get("subtitle"),
            "surface": surface,
            "pieces": data.get("rooms"),
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

    except Exception as e:
        print("Erreur :", e)
        return None


# ==========================================
# FONCTION PUBLIQUE
# ==========================================

def scrape_details(links: list) -> list:
  
    resultats = []

    for i, annonce in enumerate(links, start=1):
        print(f"\n==========================")
        print(f"Annonce {i}/{len(links)}")
        print(f"==========================")

        resultat = _scraper_annonce(annonce)

        if resultat:
            resultats.append(resultat)
            print("OK ajoutée")
        else:
            print("Annonce ignorée")

        time.sleep(1)

    print(f"\n==========================")
    print(f"DÉTAILS TERMINÉS : {len(resultats)} annonces")
    print(f"==========================")

    return resultats
