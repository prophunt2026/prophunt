import requests
import json
import time
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}


# ==========================================
# HELPERS
# ==========================================

def _scraper_annonce(url: str) -> dict | None:
    """Scrape la page de détail d'une annonce et retourne un dict enrichi."""
    try:
        response = None
        for tentative in range(1, 4):
            try:
                response = requests.get(url, headers=HEADERS, timeout=20)
                if response.status_code == 200:
                    break
                if response.status_code == 429:
                    print(f"Bloqué (429), pause... (tentative {tentative})")
                    time.sleep(9 * tentative)
                    continue
                print(f"Status {response.status_code} (tentative {tentative})")
                time.sleep(3 * tentative)
            except requests.exceptions.RequestException as e:
                print(f"Erreur réseau ({e}) - tentative {tentative}/3")
                time.sleep(3 * tentative)

        if response is None or response.status_code != 200:
            print(f"Echec définitif : {url}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # JSON-LD
        script_json = soup.find("script", type="application/ld+json")
        if script_json is None:
            print("JSON-LD absent")
            return None

        data = json.loads(script_json.string)

        # Caractéristiques générales
        caracteristiques = {}
        for bloc in soup.find_all("div", class_="adMainFeature"):
            label  = bloc.find("p", class_="adMainFeatureContentLabel")
            valeur = bloc.find("p", class_="adMainFeatureContentValue")
            if label and valeur:
                caracteristiques[label.get_text(strip=True)] = valeur.get_text(strip=True)

        # Équipements
        equipements = []
        for bloc in soup.find_all("div", class_="adFeature"):
            textes = [p.get_text(strip=True) for p in bloc.find_all("p")]
            if textes:
                equipements.append(textes)

        annonce = {
            "titre":       data.get("name"),
            "description": data.get("description"),
            "url":         data.get("url") or url,
            "prix":        data.get("offers", {}).get("price"),
            "devise":      data.get("offers", {}).get("priceCurrency", "TND"),
            "ville":       data.get("itemOffered", {}).get("address", {}).get("addressLocality"),
            "surface":     data.get("itemOffered", {}).get("floorSize", {}).get("value"),
            "pieces":      data.get("itemOffered", {}).get("numberOfRooms"),
            "chambres":    data.get("itemOffered", {}).get("numberOfBedrooms"),
            "salles_de_bain": data.get("itemOffered", {}).get("numberOfBathroomsTotal"),
            "agence":      data.get("seller", {}).get("name"),
            "images":      data.get("image") or [],
            "equipements": equipements,
            "caracteristiques": caracteristiques,
            "telephone":   [],  # rempli par scrape_telephones()
        }

        # Ignorer les annonces sans prix
        if annonce["prix"] is None:
            print("Prix absent → ignorée")
            return None

        return annonce

    except Exception as e:
        print(f"Erreur scraping détail {url} : {e}")
        return None


# ==========================================
# FONCTION PUBLIQUE
# ==========================================

def scrape_details(links: list) -> list:
    """
    Reçoit la liste d'URLs (sortie de scrape_links), scrape chaque page
    de détail et retourne une liste d'annonces enrichies (sans téléphone).

    Args:
        links: liste d'URLs Mubawab (str)

    Returns:
        list: liste de dicts enrichis
    """
    resultats = []

    for i, url in enumerate(links, start=1):
        print(f"\n--- Annonce {i}/{len(links)} : {url}")
        annonce = _scraper_annonce(url)
        if annonce:
            resultats.append(annonce)
            print("OK ajoutée")
        else:
            print("Ignorée")
        time.sleep(2)

    print(f"\n=================================")
    print(f"DÉTAILS TERMINÉS : {len(resultats)} annonces")
    print(f"=================================")

    return resultats
