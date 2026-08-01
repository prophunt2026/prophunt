"""
parsers.py - Fonctions de parsing du DOM HTML et blocs JSON-LD.
"""

import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from config import ETAT_MAP, EQUIPEMENT_KEYWORDS
from config import PAYS_VOULUS, DEVISES_VOULUES, TYPES_VOULUS, MOTS_CLES_EXCLUS
from models import empty_record


def parse_number(text):
    """Extrait un nombre entier ou décimal d'une chaîne de caractères."""
    if not text:
        return None
    match = re.search(r"[\d\s\u202f]+(?:[.,]\d+)?", text)
    if not match:
        return None
    cleaned = match.group(0).replace("\u202f", "").replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
        return int(value) if value.is_integer() else value
    except ValueError:
        return None


def parse_summary_block(soup):
    summary = soup.find("div", class_="summary")
    data = {}
    if not summary:
        return data
    for li in summary.find_all("li"):
        span = li.find("span")
        if not span:
            continue
        label = li.get_text(" ", strip=True).replace(span.get_text(strip=True), "").strip()
        data[label] = span.get_text(strip=True)
    return data


def get_breadcrumb_tabs(soup):
    """
    Retourne les textes des onglets du fil d'Ariane :
    [0] catégorie de transaction ("Vente" / "Location" / "Location saisonnière")
    [1] type de bien ("Appartement", "Maison", "Terrain", ...)
    [2] titre complet de l'annonce (peu fiable, on ne s'en sert pas)
    Structure réelle observée : <nav aria-label="breadcrumb"><ul>
      <li class="module-breadcrumb-tab"><a>Location</a></li>
      <li class="module-breadcrumb-tab"><a>Maison</a></li>
      <li class="module-breadcrumb-tab"><h2><a>Location villa ...</a></h2></li>
    </ul></nav>
    (NB : le 3e onglet ne commence pas toujours par "Vente"/"Location" suivi
    du type — s'appuyer dessus par regex est fragile, d'où l'usage des 2
    premiers onglets qui sont des libellés propres et stables.)
    """
    breadcrumb = soup.find("nav", attrs={"aria-label": "breadcrumb"})
    if not breadcrumb:
        return []
    tabs = breadcrumb.find_all("li", class_="module-breadcrumb-tab")
    return [tab.get_text(strip=True) for tab in tabs]


def get_type_bien(soup):
    """Type de bien = 2e onglet du fil d'Ariane."""
    tabs = get_breadcrumb_tabs(soup)
    if len(tabs) >= 2:
        return tabs[1]
    return None


def get_transaction_type(soup):
    """Type de transaction = 1er onglet du fil d'Ariane ('Vente' ou 'Location*')."""
    tabs = get_breadcrumb_tabs(soup)
    if tabs:
        first = tabs[0].lower()
        if "location" in first:
            return "location"
        if "vente" in first:
            return "vente"
    return None


def get_equipements(soup):
    result = {}
    prestations_div = soup.find("h3", string=re.compile("Prestations"))
    if not prestations_div:
        return result
    container = prestations_div.find_parent("div")
    ul = container.find("ul") if container else None
    if not ul:
        return result
    items = [li.get_text(strip=True).lower() for li in ul.find_all("li")]
    for field, keywords in EQUIPEMENT_KEYWORDS.items():
        result[field] = any(any(kw in item for kw in keywords) for item in items)
    return result


def get_proximites(soup):
    prox_h3 = soup.find("h3", string=re.compile("Proximités"))
    if not prox_h3:
        return []
    container = prox_h3.find_parent("div")
    ul = container.find("ul") if container else None
    if not ul:
        return []
    return [
        {"type": None, "nom": li.get_text(strip=True), "distance_m": None}
        for li in ul.find_all("li")
    ]


def get_surfaces_extra(soup):
    surf_h3 = soup.find("h3", string=re.compile("^Surfaces$"))
    result = {}
    if not surf_h3:
        return result
    container = surf_h3.find_parent("div")
    ul = container.find("ul") if container else None
    if not ul:
        return result
    for li in ul.find_all("li"):
        label = li.get_text(" ", strip=True)
        span = li.find("span")
        if "terrain" in label.lower() and span:
            result["superficie_terrain"] = parse_number(span.get_text(strip=True))
    return result


def get_contact_info(soup):
    contact_div = soup.find("div", class_=lambda c: c and "module-223304" in c)
    result = {"nom_vendeur": None, "telephone": [], "email": None}
    if not contact_div:
        return result
    name_tag = contact_div.find("h3")
    if name_tag:
        result["nom_vendeur"] = " ".join(name_tag.get_text(" ", strip=True).split())
    result["telephone"] = [
        a.get_text(strip=True)
        for a in contact_div.find_all("a", href=lambda h: h and h.startswith("tel:"))
    ]
    email_tag = contact_div.find("a", href=lambda h: h and h.startswith("mailto:"))
    if email_tag:
        result["email"] = email_tag.get_text(strip=True)
    return result


def get_json_ld(soup):
    script_tag = soup.find("script", {"type": "application/ld+json"})
    if not script_tag or not script_tag.string:
        return None
    try:
        return json.loads(script_tag.string)
    except json.JSONDecodeError:
        return None


def build_record(html, url, listing_extra=None):
    listing_extra = listing_extra or {}
    record = empty_record()
    record["listing"]["url_source"] = url
    record["listing"]["url_canonique"] = url
    record["listing"]["date_scraping"] = datetime.now(timezone.utc).isoformat()

    soup = BeautifulSoup(html, "lxml")
    json_ld = get_json_ld(soup)
    record["donnees_brutes"]["json_ld"] = json_ld

    # Détecté depuis le fil d'Ariane HTML (indépendant du JSON-LD, donc fiable
    # même si le bloc JSON-LD est absent ou incomplet)
    transaction_type = get_transaction_type(soup) or "vente"
    record["transaction"]["type"] = transaction_type

    property_data, agency_data = None, None
    if json_ld:
        graph = json_ld.get("@graph", [])
        property_data = next(
            (x for x in graph if x.get("@type") in ("Apartment", "House", "SingleFamilyResidence")),
            None,
        )
        agency_data = next((x for x in graph if x.get("@type") == "RealEstateAgent"), None)

    if property_data:
        record["listing"]["id_source"] = property_data.get("identifier")
        record["listing"]["id_universel"] = f"HIT_{property_data.get('identifier')}"
        record["listing"]["date_publication"] = property_data.get("datePosted")
        record["listing"]["date_maj"] = property_data.get("dateModified")
        offers = property_data.get("offers", {}) or {}
        record["listing"]["statut"] = (
            "actif" if offers.get("availability", "").endswith("InStock") else "inconnu"
        )
        prix_json_ld = parse_number(offers.get("price"))
        if transaction_type == "location":
            record["transaction"]["loyer_mensuel"] = prix_json_ld
        else:
            record["transaction"]["prix"] = prix_json_ld
        record["transaction"]["devise"] = offers.get("priceCurrency", "TND")
        record["transaction"]["disponibilite_date"] = offers.get("validFrom")

        address = property_data.get("address", {}) or {}
        record["localisation"]["ville"] = address.get("addressLocality")
        record["localisation"]["code_postal"] = address.get("postalCode")
        record["localisation"]["adresse"] = address.get("streetAddress")

        geo = property_data.get("geo", {}) or {}
        record["localisation"]["coordonnees"]["latitude"] = geo.get("latitude")
        record["localisation"]["coordonnees"]["longitude"] = geo.get("longitude")

        record["description"]["titre"] = (property_data.get("name") or "").strip()
        record["description"]["texte"] = property_data.get("description")

        record["bien"]["nombre_pieces"] = property_data.get("numberOfRooms")
        floor_size = property_data.get("floorSize", {}) or {}
        record["bien"]["superficie_habitable"] = floor_size.get("value")

        record["medias"]["photos"] = [
            {"url": img, "url_thumb": None, "legende": None, "ordre": i, "type": None}
            for i, img in enumerate(property_data.get("image", []))
        ]
        record["medias"]["nombre_photos"] = len(record["medias"]["photos"])

    if agency_data:
        record["contact"]["nom_agence"] = agency_data.get("name")
        record["contact"]["site_web"] = agency_data.get("url")
        record["contact"]["logo_agence"] = agency_data.get("logo")

    type_bien = get_type_bien(soup)
    if type_bien:
        record["bien"]["type"] = type_bien.lower()

    summary = parse_summary_block(soup)
    if "Surface" in summary:
        record["bien"]["superficie_habitable"] = parse_number(summary["Surface"])
    if "Surface totale" in summary:
        record["bien"]["superficie_totale"] = parse_number(summary["Surface totale"])
    if "Pièces" in summary:
        record["bien"]["nombre_pieces"] = parse_number(summary["Pièces"])
    if "Étage" in summary:
        record["bien"]["etage"] = summary["Étage"]
    if "Vue" in summary:
        record["bien"]["vue"] = summary["Vue"]
    if "État" in summary:
        record["bien"]["etat_general"] = ETAT_MAP.get(summary["État"].lower())
    if "Exposition" in summary:
        record["bien"]["orientation"] = summary["Exposition"]
    if "Type de chauffage" in summary:
        record["equipements"]["chauffage"] = summary["Type de chauffage"]
    if "Type d'eau chaude" in summary:
        record["equipements"]["eau_chaude"] = summary["Type d'eau chaude"]

    record["bien"].update(get_surfaces_extra(soup))
    record["equipements"].update(get_equipements(soup))
    record["localisation"]["proximites"] = get_proximites(soup)

    contact_info = get_contact_info(soup)
    record["contact"]["nom_vendeur"] = contact_info["nom_vendeur"]
    record["contact"]["telephone"] = contact_info["telephone"]
    record["contact"]["email"] = contact_info["email"]

    if record["bien"]["nombre_pieces"] is None:
        record["bien"]["nombre_pieces"] = listing_extra.get("nombre_pieces_liste")
    if record["bien"]["nombre_chambres"] is None:
        record["bien"]["nombre_chambres"] = listing_extra.get("nombre_chambres_liste")
    if record["bien"]["nombre_salles_bain"] is None:
        record["bien"]["nombre_salles_bain"] = listing_extra.get("nombre_salles_bain_liste")
    if record["bien"]["superficie_totale"] is None:
        record["bien"]["superficie_totale"] = listing_extra.get("superficie_liste")
    if transaction_type == "location" and record["transaction"]["loyer_mensuel"] is None:
        record["transaction"]["loyer_mensuel"] = listing_extra.get("loyer_liste")

    record["metadonnees_scraping"]["statut_scraping"] = (
        "succes" if property_data else "echec_partiel"
    )
    return record

def is_valid_record(record):
    """
    Vérifie si un record respecte tous nos critères :
    - Type voulu (appartement, villa, etc.)
    - Situé en Tunisie
    - En Dinars Tunisiens (TND)
    - Pas de mots-clés commerciaux/hôteliers dans le titre ou la description.
    """
    # 1. Validation du type
    bien_type = (record.get("bien", {}).get("type") or "").lower()
    if bien_type not in TYPES_VOULUS:
        return False, f"Type invalide ({bien_type})"

    # 2. Validation du pays
    pays = (record.get("localisation", {}).get("pays") or "").lower()
    if pays and pays not in PAYS_VOULUS:
        return False, f"Hors Tunisie ({record['localisation']['pays']})"

    # 3. Validation de la devise
    devise = record.get("transaction", {}).get("devise")
    if devise and devise not in DEVISES_VOULUES:
        return False, f"Devise hors TND ({devise})"

    # 4. Détection des hôtels/locaux commerciaux dans le titre et texte
    titre = (record.get("description", {}).get("titre") or "").lower()
    texte = (record.get("description", {}).get("texte") or "").lower()
    contenu_complet = f"{titre} {texte}"

    for mot in MOTS_CLES_EXCLUS:
        if mot in contenu_complet:
            return False, f"Détecté comme bien commercial/hôtel (mot-clé: '{mot}')"

    return True, "Valide"