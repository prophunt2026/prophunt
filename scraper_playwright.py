"""
Scraper Home In Tunisia -> schema_standard_immobilier_tunisie.json
Extraction dynamique du listing via Playwright (scroll & parsing DOM)
et parsing HTML/JSON-LD des fiches fétchées via Playwright / requests.
"""

import json
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.homeintunisia.com"
LISTING_URL = BASE_URL + "/fr/acheter"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}

TYPES_VOULUS = {"appartement", "maison", "villa","studio","s3","s4","s2","s1","s0"}

ETAT_MAP = {
    "excellent état": "bon",
    "bon état": "bon",
    "neuf": "neuf",
    "à rénover": "a_renover",
    "ancien": "ancien",
    "livré": "livre",
    "sur plan": "sur_plan",
}

EQUIPEMENT_KEYWORDS = {
    "climatisation": ["climatis"],
    "ascenseur": ["ascenseur"],
    "garage": ["garage"],
    "cave": ["cave"],
    "terrasse": ["terrasse"],
    "balcon": ["balcon"],
    "jardin": ["jardin"],
    "piscine": ["piscine"],
    "cuisine_equipee": ["cuisine équipée", "cuisine equipee"],
    "cuisine_americaine": ["cuisine américaine"],
    "double_vitrage": ["double vitrage"],
    "volets_roulants": ["volet"],
    "porte_blindee": ["porte blindée"],
    "interphone": ["interphone"],
    "videophone": ["vidéophone", "videophone"],
    "alarme": ["alarme"],
    "concierge": ["concierge"],
    "gardiennage": ["gardien"],
    "cheminee": ["cheminée"],
    "dressing": ["dressing"],
    "salle_de_sport": ["salle de sport"],
}


def empty_record():
    """Squelette vide conforme au schéma standard."""
    return {
        "listing": {
            "id_source": None, "id_universel": None, "url_source": None,
            "url_canonique": None, "date_scraping": None, "date_publication": None,
            "date_maj": None, "statut": "inconnu", "langue": "fr",
        },
        "transaction": {
            "type": "vente", "prix": None, "devise": "TND", "prix_negociable": None,
            "prix_m2": None, "loyer_mensuel": None, "charges_mensuelles": None,
            "caution": None, "frais_agence": None, "disponibilite": None,
            "disponibilite_date": None,
        },
        "bien": {
            "type": None, "sous_type": None, "usage": "residentiel",
            "superficie_totale": None, "superficie_habitable": None,
            "superficie_terrain": None, "nombre_pieces": None, "nombre_chambres": None,
            "nombre_salles_bain": None, "nombre_salles_eau": None,
            "nombre_etages_total": None, "etage": None, "dernier_etage": None,
            "annee_construction": None, "etat_general": None, "standing": None,
            "meuble": None, "orientation": None, "vue": None,
        },
        "localisation": {
            "pays": "Tunisie", "pays_code": "TN", "gouvernorat": None,
            "delegation": None, "ville": None, "localite": None, "quartier": None,
            "adresse": None, "code_postal": None, "proximites": [],
            "coordonnees": {"latitude": None, "longitude": None}, "zone": None,
        },
        "equipements": {k: None for k in [
            "climatisation", "chauffage", "ascenseur", "garage", "places_parking",
            "parking_exterieur", "cave", "terrasse", "balcon", "jardin",
            "superficie_jardin", "piscine", "cuisine_equipee", "cuisine_americaine",
            "double_vitrage", "volets_roulants", "porte_blindee", "interphone",
            "videophone", "alarme", "concierge", "gardiennage", "eau_chaude",
            "antenne_tv", "internet", "adsl", "fibre_optique", "cheminee",
            "dressing", "salle_de_sport", "espace_enfants",
        ]} | {"autres": []},
        "description": {
            "titre": None, "texte": None, "texte_ar": None,
            "points_forts": [], "mentions_legales": None,
        },
        "medias": {
            "photos": [], "videos": [], "plans": [],
            "visite_virtuelle": None, "nombre_photos": None,
        },
        "contact": {
            "type_vendeur": "agence", "nom_vendeur": None, "nom_agence": None,
            "telephone": [], "whatsapp": None, "email": None, "site_web": None,
            "logo_agence": None, "photo_agence": None, "url_profil": None,
            "annonces_vendeur": None, "membre_depuis": None, "verifie": None,
        },
        "metadonnees_scraping": {
            "source": "home_in_tunisia", "selecteur_html": {}, "methode": "playwright",
            "statut_scraping": "echec", "erreurs": [], "temps_scraping_ms": None,
            "user_agent": USER_AGENT, "proxy_utilise": None, "cache": None,
        },
        "scoring_ia": {
            "prix_estime_marche": None, "decote_pourcentage": None,
            "score_opportunite": None, "confiance_estimation": None,
            "tendance_quartier": None, "rentabilite_locative": None,
            "delai_vente_estime": None, "alertes": [],
        },
        "donnees_brutes": {"json_ld": None, "html_snippet": None},
    }


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
    """Extrait les paires clé-valeur du bloc résumé de la fiche."""
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


def get_type_bien(soup):
    """Détermine le type de bien depuis s le fil d'Ariane."""

    breadcrumb = soup.find("nav", attrs={"aria-label": "breadcrumb"})
    if breadcrumb:
        h2 = breadcrumb.find("h2")
        if h2:
            match = re.search(r"Vente (\w+)", h2.get_text(strip=True))
            if match:
                return match.group(1)
    return None


def get_equipements(soup):
    """Analyse la rubrique Prestations pour identifier les équipements présents."""
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
    """Récupère les éléments de proximité."""
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
    """Extrait la surface du terrain si spécifiée."""
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
    """Extrait le nom, téléphone et mail de l'agent immobilier."""
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
    """Récupère le bloc JSON-LD de la page."""
    script_tag = soup.find("script", {"type": "application/ld+json"})
    if not script_tag or not script_tag.string:
        return None
    try:
        return json.loads(script_tag.string)
    except json.JSONDecodeError:
        return None


def build_record(html, url, listing_extra=None):
    """Construit la structure de données finale à partir du HTML de la fiche."""
    listing_extra = listing_extra or {}
    record = empty_record()
    record["listing"]["url_source"] = url
    record["listing"]["url_canonique"] = url
    record["listing"]["date_scraping"] = datetime.now(timezone.utc).isoformat()

    soup = BeautifulSoup(html, "lxml")

    json_ld = get_json_ld(soup)
    record["donnees_brutes"]["json_ld"] = json_ld

    property_data, agency_data = None, None
    if json_ld:
        graph = json_ld.get("@graph", [])
        property_data = next(
            (x for x in graph if x.get("@type") in ("Apartment", "House", "SingleFamilyResidence")),
            None,
        )
        agency_data = next((x for x in graph if x.get("@type") == "RealEstateAgent"), None)

    # --- Section Listing ---
    if property_data:
        record["listing"]["id_source"] = property_data.get("identifier")
        record["listing"]["id_universel"] = f"HIT_{property_data.get('identifier')}"
        record["listing"]["date_publication"] = property_data.get("datePosted")
        record["listing"]["date_maj"] = property_data.get("dateModified")
        offers = property_data.get("offers", {}) or {}
        record["listing"]["statut"] = (
            "actif" if offers.get("availability", "").endswith("InStock") else "inconnu"
        )
        record["transaction"]["prix"] = parse_number(offers.get("price"))
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

    # --- Type de bien ---
    type_bien = get_type_bien(soup)
    if type_bien:
        record["bien"]["type"] = type_bien.lower()

    # --- Résumé HTML ---
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

    # --- Fallback avec les infos capturées sur la carte du listing ---
    if record["bien"]["nombre_pieces"] is None:
        record["bien"]["nombre_pieces"] = listing_extra.get("nombre_pieces_liste")
    if record["bien"]["nombre_chambres"] is None:
        record["bien"]["nombre_chambres"] = listing_extra.get("nombre_chambres_liste")
    if record["bien"]["nombre_salles_bain"] is None:
        record["bien"]["nombre_salles_bain"] = listing_extra.get("nombre_salles_bain_liste")
    if record["bien"]["superficie_totale"] is None:
        record["bien"]["superficie_totale"] = listing_extra.get("superficie_liste")

    record["metadonnees_scraping"]["statut_scraping"] = (
        "succes" if property_data else "echec_partiel"
    )
    return record


# ---------------------------------------------------------------------------
# EXTRACTION AVEC PLAYWRIGHT (Remplace le hack basés sur les IDs)
# ---------------------------------------------------------------------------

def fetch_listing_items_with_playwright(page, max_scrolls=10):
    """
    Ouvre la page de listing, fait défiler vers le bas (scroll) pour forcer
    le chargement JS de toutes les cartes d'annonces, puis extrait les liens réels
    et le contenu HTML des cartes chargées.
    """
    print(f"Navigation vers : {LISTING_URL}")
    page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("ul.listing", timeout=10000)

    previous_count = 0
    for scroll_idx in range(1, max_scrolls + 1):
        # Récupère le nombre d'éléments actuellement présents dans le DOM
        current_count = page.locator("ul.listing > li.property").count()
        print(f"Scroll {scroll_idx}/{max_scrolls} - Biens détectés : {current_count}")

        # Défilement vers le bas
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)  # Pause pour laisser le JS charger les éléments

        # Arrêt si le scrolling n'apporte plus de nouveaux biens
        if current_count == previous_count and scroll_idx > 2:
            print("Plus de nouveaux biens chargés via scroll.")
            break
        previous_count = current_count

    # Extraction du HTML complet rendu après tous les scrolls
    html_content = page.content()
    soup = BeautifulSoup(html_content, "lxml")

    results = []
    ul = soup.find("ul", class_="listing")
    if not ul:
        return results

    for li in ul.find_all("li", class_="property"):
        prop_id = li.get("data-property-id")

        # Recherche du vrai lien <a> dans la carte
        link_tag = li.find("a", href=True)
        if link_tag:
            href = link_tag["href"]
            url = BASE_URL + href if href.startswith("/") else href
        elif prop_id:
            # Sécurité si la balise <a> n'est pas encore rendue
            url = f"{BASE_URL}/fr/propriété/{prop_id}"
        else:
            continue

        card_infos = {}
        article = li.find("article")
        if article:
            for sub_li in article.find_all("li"):
                span = sub_li.find("span")
                if span and span.get("class"):
                    field = span["class"][0]
                    value = sub_li.get_text(strip=True)
                    if value:
                        card_infos[field] = value

        type_tag = li.find("h3")
        results.append({
            "url": url,
            "id": prop_id,
            "type_liste": type_tag.get_text(strip=True).split(",")[0] if type_tag else None,
            "nombre_pieces_liste": parse_number(card_infos.get("rooms")),
            "nombre_chambres_liste": parse_number(card_infos.get("bedrooms")),
            "nombre_salles_bain_liste": parse_number(card_infos.get("bathrooms")),
            "superficie_liste": parse_number(card_infos.get("area")),
        })

    return results


def scrape_all(max_properties=15, delay=1.0, headless=True):
    """Fonction principale d'orchestration."""
    all_items = []

    with sync_playwright() as p:
        print("Lancement du navigateur Chromium (Playwright)...")
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            all_items = fetch_listing_items_with_playwright(page, max_scrolls=8)
            print(f"\nTotal des annonces capturées dans le DOM : {len(all_items)}")
        except PlaywrightTimeoutError:
            print("Erreur : Temps d'attente dépassé lors du chargement de la page listing.")
        finally:
            browser.close()

    if not all_items:
        print("Aucune annonce trouvée.")
        return []

    if max_properties:
        all_items = all_items[:max_properties]

    records = []
    skipped_type = 0

    # Scraping individuel des fiches de détail (via requests pour la rapidité)
    for i, item in enumerate(all_items, 1):
        try:
            resp = requests.get(item["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            record = build_record(resp.text, item["url"], listing_extra=item)

            # Filtrage par type de bien
            bien_type = record["bien"]["type"]
            if bien_type not in TYPES_VOULUS:
                skipped_type += 1
                print(f"[{i}/{len(all_items)}] {item['url']} -> ignoré (type={bien_type})")
                continue

            records.append(record)
            print(f"[{i}/{len(all_items)}] {item['url']} -> OK ({bien_type})")
        except requests.RequestException as e:
            print(f"Erreur lors du fetch de la fiche {item['url']}: {e}")

        time.sleep(delay)

    print(f"\n{len(records)} biens retenus, {skipped_type} ignorés (type non voulu)")
    return records


if __name__ == "__main__":
    # max_properties=15 pour vos tests ; augmentez ou passez à None pour tout scraper
    records = scrape_all(max_properties=15, delay=1.0, headless=True)

    with open("properties_schema.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"{len(records)} biens enregistrés dans 'properties_schema.json'.")