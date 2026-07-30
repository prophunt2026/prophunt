"""
Scraper pour tayara.tn — catégorie Immobilier, via l'API interne du site.

DÉCOUVERTE CLÉ (analyse du trafic réseau, capturée en DEBUG_NETWORK) :
Tayara charge ses résultats via un endpoint JSON interne (Next.js), pas en
scrollant du HTML :

    https://www.tayara.tn/_next/data/<BUILD_ID>/en/listing/c/immobilier.json
        ?category=immobilier&page=N

C'est beaucoup plus rapide et fiable qu'un navigateur simulé (Playwright) :
une simple requête HTTP renvoie des annonces déjà structurées — titre, prix,
DESCRIPTION COMPLÈTE, photos, date de publication, gouvernorat/délégation,
et vendeur (nom + agence ou particulier).

ENRICHISSEMENT FICHE DÉTAIL :
Après la collecte initiale (listing API), chaque annonce est enrichie en
visitant sa fiche HTML /item/ID/ qui contient :
    - Toutes les photos (l'API listing ne renvoie qu'une image)
    - Le numéro de téléphone du vendeur
    - Les paramètres structurés (superficie, chambres, SDB, type transaction)
    - Les données complètes du vendeur (nom, email, isShop, url boutique)

Le <BUILD_ID> change à chaque déploiement du site (identifiant Next.js) :
on le récupère dynamiquement depuis le HTML de la page catégorie avant de
paginer, pour ne pas dépendre d'une valeur codée en dur qui expirerait.
"""

import re
import time
from datetime import datetime, timezone

import requests

from common.schema import new_listing
from common.utils import RateLimiter, deduplicate, export_to_csv, export_to_json, get_logger, safe_get

CATEGORY_PAGE_URL = "https://www.tayara.tn/listing/c/immobilier/"
API_URL_TEMPLATE = "https://www.tayara.tn/_next/data/{build_id}/en/listing/c/immobilier.json"
ITEM_PAGE_URL_TEMPLATE = "https://www.tayara.tn/item/{listing_id}/"
SOURCE_NAME = "tayara"

logger = get_logger(SOURCE_NAME)

# Mapping observé subCategory (id Tayara) -> type de bien normalisé.
SUBCATEGORY_MAP = {
    "60be84bd50ab95b45b08a09c": "appartement",
    "60be84bd50ab95b45b08a09d": "villa",
    "60be84bd50ab95b45b08a09e": "appartement",  # locations saisonnières / meublées
    "60be84be50ab95b45b08a0a0": "local_commercial",
    "60be84be50ab95b45b08a0a1": "terrain",
    "60be84be50ab95b45b08a09f": "local_commercial",  # bureaux
}

# Mapping adParams label -> champ schema
ADPARAM_LABEL_MAP = {
    "superficie": "superficie_totale",
    "superficie (m²)": "superficie_totale",
    "surface": "superficie_totale",
    "chambres": "nombre_chambres",
    "salles de bains": "nombre_salles_bain",
    "salle de bain": "nombre_salles_bain",
    "salles de bain": "nombre_salles_bain",
}

TRANSACTION_TYPE_MAP = {
    "à vendre": "vente",
    "a vendre": "vente",
    "vente": "vente",
    "à louer": "location",
    "a louer": "location",
    "location": "location",
}

SURFACE_PATTERNS = [
    r"[Ss]uperficie[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*m",
    r"[Ss]urface[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*m",
]
CHAMBRES_PATTERN = re.compile(r"(\d+)\s*chambres?\s*(?:à coucher)?", re.IGNORECASE)
SDB_PATTERN = re.compile(r"(\d+)\s*salles?\s*(?:de\s*)?bain", re.IGNORECASE)
SDB_SINGULAR_PATTERN = re.compile(r"\bsalle\s+de\s+bain\b", re.IGNORECASE)


def _guess_salles_bain(text: str) -> int | None:
    if not text:
        return None
    m = SDB_PATTERN.search(text)
    if m:
        return int(m.group(1))
    if SDB_SINGULAR_PATTERN.search(text):
        return 1
    return None


def _guess_float(text: str, patterns: list[str]) -> float | None:
    if not text:
        return None
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def _parse_adparam_float(value: str) -> float | None:
    """Convertit une chaîne comme '80' ou '120.5' en float."""
    if not value:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _parse_adparam_int(value: str) -> int | None:
    """Convertit une chaîne comme '3' en int."""
    f = _parse_adparam_float(value)
    return int(f) if f is not None else None


def get_build_id(session: requests.Session) -> str | None:
    """Récupère l'identifiant de build Next.js actuel depuis le HTML de la
    page catégorie (change à chaque déploiement du site)."""
    resp = safe_get(CATEGORY_PAGE_URL, session=session)
    if resp is None:
        return None
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    return match.group(1) if match else None


def fetch_detail(listing_id: str, session: requests.Session) -> dict | None:
    """Récupère la fiche détail d'une annonce via sa page HTML /item/ID/.

    Retourne un dict avec :
        - images       : liste de toutes les URLs photos
        - phone        : numéro de téléphone du vendeur (ou None)
        - ad_params    : dict normalisé {superficie_totale, nombre_chambres,
                         nombre_salles_bain, type_transaction}
        - vendor_name  : nom complet du vendeur
        - vendor_email : email du vendeur (souvent vide)
        - vendor_is_shop : bool
        - vendor_url   : URL boutique (si agence)
        - vendor_phone : phonenumber depuis adUserData (alternative à phone)

    Retourne None si la fiche est introuvable ou si la page redirige
    (annonce expirée).
    """
    url = ITEM_PAGE_URL_TEMPLATE.format(listing_id=listing_id)
    resp = safe_get(url, session=session)
    if resp is None:
        return None

    # Détection de redirection silencieuse (annonce expirée -> page listing)
    if resp.url and "/item/" not in resp.url:
        logger.debug(f"Annonce {listing_id} expirée (redirigée vers {resp.url})")
        return None

    # Extraction du __NEXT_DATA__ embarqué dans le HTML
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        logger.warning(f"__NEXT_DATA__ introuvable pour {listing_id}")
        return None

    import json
    try:
        next_data = json.loads(match.group(1))
    except (ValueError, KeyError):
        logger.warning(f"JSON invalide dans __NEXT_DATA__ pour {listing_id}")
        return None

    page_props = next_data.get("props", {}).get("pageProps", {})
    ad = page_props.get("adDetails") or {}
    user = page_props.get("adUserData") or {}

    if not ad:
        return None

    # --- Photos ---
    images = ad.get("images") or []

    # --- Téléphone ---
    phone = ad.get("phone") or user.get("phonenumber") or None

    # --- adParams -> champs structurés ---
    ad_params: dict = {}
    for param in (ad.get("adParams") or []):
        label_raw = (param.get("label") or "").strip().lower()
        value_raw = str(param.get("value") or "").strip()
        normalized_key = ADPARAM_LABEL_MAP.get(label_raw)

        if normalized_key == "superficie_totale":
            ad_params["superficie_totale"] = _parse_adparam_float(value_raw)
        elif normalized_key == "nombre_chambres":
            ad_params["nombre_chambres"] = _parse_adparam_int(value_raw)
        elif normalized_key == "nombre_salles_bain":
            ad_params["nombre_salles_bain"] = _parse_adparam_int(value_raw)
        elif label_raw in ("type de transaction", "transaction"):
            ad_params["type_transaction"] = TRANSACTION_TYPE_MAP.get(
                value_raw.lower(), None
            )

    # --- Données vendeur ---
    vendor_name = user.get("fullname") or ad.get("publisher", {}).get("name") or None
    vendor_email = user.get("email") or None
    vendor_is_shop = bool(user.get("isShop") or ad.get("publisher", {}).get("isShop"))
    vendor_url = user.get("url") or None
    vendor_avatar = user.get("avatar") or ad.get("publisher", {}).get("avatar") or None

    return {
        "images": images,
        "phone": phone,
        "ad_params": ad_params,
        "vendor_name": vendor_name,
        "vendor_email": vendor_email,
        "vendor_is_shop": vendor_is_shop,
        "vendor_url": vendor_url,
        "vendor_avatar": vendor_avatar,
    }


def parse_api_page(data: dict) -> list[dict]:
    """ÉTAPES 2+3+4 : transforme la réponse JSON de l'API Tayara en annonces
    respectant le schéma commun (common/schema.py).

    Note : à ce stade, photos et téléphone sont incomplets (API listing ne
    renvoie qu'une image par annonce et pas de téléphone). Ces champs seront
    complétés par enrich_with_details().
    """
    hits = data.get("pageProps", {}).get("searchedListingsAction", {}).get("newHits", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    records = []

    for hit in hits:
        metadata = hit.get("metadata", {}) or {}
        publisher = metadata.get("publisher", {}) or {}
        location = hit.get("location", {}) or {}
        description = hit.get("description") or ""
        title = hit.get("title") or ""
        sub_category = metadata.get("subCategory")

        listing = new_listing()
        listing["listing"].update({
            "id_source": hit.get("id"),
            "url_source": f"https://www.tayara.tn/item/{hit.get('id')}/",
            "date_scraping": now_iso,
            "date_publication": metadata.get("publishedOn"),
            "statut": "actif",
            "langue": "ar" if re.search(r"[\u0600-\u06FF]", title) else "fr",
        })
        listing["transaction"].update({
            "prix": hit.get("price"),
        })
        listing["bien"].update({
            "type": SUBCATEGORY_MAP.get(sub_category),
            # Valeurs extraites de la description texte — seront remplacées
            # par les valeurs structurées (adParams) lors de l'enrichissement
            "superficie_totale": _guess_float(description, SURFACE_PATTERNS),
            "nombre_chambres": int(m.group(1)) if (m := CHAMBRES_PATTERN.search(description)) else None,
            "nombre_salles_bain": _guess_salles_bain(description),
        })
        listing["localisation"].update({
            "gouvernorat": location.get("governorate"),
            "delegation": location.get("delegation"),
        })
        listing["description"].update({
            "titre": title or None,
            "texte": description or None,
        })
        # Photos partielles depuis l'API listing (1 seule image en général)
        images = hit.get("images", []) or []
        listing["medias"].update({
            "photos": [
                {"url": u, "url_thumb": None, "legende": None, "ordre": i, "type": None}
                for i, u in enumerate(images)
            ],
            "nombre_photos": len(images),
        })
        listing["contact"].update({
            "type_vendeur": "agence" if publisher.get("isShop") else "particulier",
            "nom_vendeur": publisher.get("name") or None,
        })
        listing["metadonnees_scraping"].update({
            "source": SOURCE_NAME,
            "methode": "api+html",
            "statut_scraping": "succes",
        })
        records.append(listing)

    return records


def enrich_with_details(
    records: list[dict],
    session: requests.Session,
    limiter: RateLimiter,
    max_detail_failures: int = 50,
) -> list[dict]:
    """PASSE 2 : visite la fiche HTML de chaque annonce pour récupérer :
    - Toutes les photos (l'API listing n'en retourne qu'une)
    - Le numéro de téléphone
    - Les paramètres structurés (superficie, chambres, SDB, type transaction)
    - Les données complètes du vendeur

    Les données de l'API listing sont conservées si la fiche détail est
    introuvable (annonce expirée entre les deux passes).
    """
    total = len(records)
    failures = 0

    for i, record in enumerate(records):
        listing_id = record["listing"].get("id_source")
        if not listing_id:
            continue

        limiter.wait()
        logger.info(f"Enrichissement {i + 1}/{total} : {listing_id}")

        detail = fetch_detail(listing_id, session)

        if detail is None:
            # Annonce expirée ou introuvable entre la passe 1 et la passe 2
            record["listing"]["statut"] = "expiré"
            failures += 1
            logger.warning(f"Détail introuvable pour {listing_id} ({failures}/{max_detail_failures})")
            if failures >= max_detail_failures:
                logger.error("Trop d'échecs de fiches détail — arrêt de l'enrichissement.")
                break
            continue

        # --- Mise à jour des photos ---
        images = detail["images"]
        if images:
            record["medias"]["photos"] = [
                {"url": u, "url_thumb": None, "legende": None, "ordre": idx, "type": None}
                for idx, u in enumerate(images)
            ]
            record["medias"]["nombre_photos"] = len(images)

        # --- Mise à jour du téléphone ---
        phone = detail["phone"]
        if phone:
            # Normalise en liste (schéma contact.telephone est une liste)
            record["contact"]["telephone"] = [phone]

        # --- Mise à jour des champs structurés depuis adParams ---
        ap = detail["ad_params"]
        if ap.get("superficie_totale") is not None:
            record["bien"]["superficie_totale"] = ap["superficie_totale"]
        if ap.get("nombre_chambres") is not None:
            record["bien"]["nombre_chambres"] = ap["nombre_chambres"]
        if ap.get("nombre_salles_bain") is not None:
            record["bien"]["nombre_salles_bain"] = ap["nombre_salles_bain"]
        if ap.get("type_transaction") is not None:
            record["transaction"]["type"] = ap["type_transaction"]

        # --- Mise à jour du vendeur ---
        if detail["vendor_name"]:
            record["contact"]["nom_vendeur"] = detail["vendor_name"]
        if detail["vendor_email"]:
            record["contact"]["email"] = detail["vendor_email"]
        if detail["vendor_url"]:
            record["contact"]["site_web"] = detail["vendor_url"]
        if detail["vendor_avatar"]:
            record["contact"]["photo_agence"] = detail["vendor_avatar"]
        # Affiner le type vendeur si on a l'info précise
        is_shop = detail["vendor_is_shop"]
        record["contact"]["type_vendeur"] = "agence" if is_shop else "particulier"

    logger.info(f"Enrichissement terminé : {total - failures}/{total} annonces enrichies")
    return records


def scrape_api(
    target: int = 1000,
    max_pages: int = 200,
    enrich_details: bool = True,
) -> list[dict]:
    """Pagine l'API interne de Tayara puis enrichit chaque annonce avec les
    données de la fiche détail (photos complètes + téléphone).

    Paramètres :
        target          : nombre maximum d'annonces à collecter
        max_pages       : garde-fou contre une boucle infinie
        enrich_details  : si False, skip la passe d'enrichissement (plus rapide
                          mais photos/téléphone incomplets)
    """
    session = requests.Session()
    # Rate limiter listing : rapide (API JSON)
    listing_limiter = RateLimiter(min_delay=1.0, max_delay=2.0)
    # Rate limiter détail : un peu plus lent (pages HTML complètes)
    detail_limiter = RateLimiter(min_delay=1.5, max_delay=3.0)

    build_id = get_build_id(session)
    if not build_id:
        logger.error(
            "Impossible de récupérer le buildId Next.js — le site a peut-être "
            "changé de structure. Vérifier CATEGORY_PAGE_URL manuellement."
        )
        return []
    logger.info(f"buildId Tayara détecté : {build_id}")

    api_url = API_URL_TEMPLATE.format(build_id=build_id)
    all_records = []

    # --- PASSE 1 : collecte rapide via l'API listing ---
    logger.info("Passe 1 : collecte via l'API listing...")
    for page in range(1, max_pages + 1):
        listing_limiter.wait()
        start = time.time()
        resp = safe_get(f"{api_url}?category=immobilier&page={page}", session=session)
        elapsed_ms = int((time.time() - start) * 1000)

        if resp is None:
            logger.error(f"Page {page} ignorée (échec de la requête)")
            continue

        try:
            data = resp.json()
        except ValueError:
            logger.error(f"Page {page} : réponse non-JSON (buildId probablement expiré), arrêt.")
            break

        records = parse_api_page(data)
        for r in records:
            r["metadonnees_scraping"]["temps_scraping_ms"] = elapsed_ms
        all_records.extend(records)
        logger.info(f"Page {page} : +{len(records)} annonces -> {len(all_records)} au total")

        if not records:
            logger.info("Page vide — fin du catalogue atteinte.")
            break
        if len(all_records) >= target:
            logger.info(f"Objectif de {target} annonces atteint.")
            break

    all_records = deduplicate(all_records, key="listing.url_source")
    # Respecte la limite target après déduplication
    if len(all_records) > target:
        all_records = all_records[:target]
    logger.info(f"Passe 1 terminée : {len(all_records)} annonces uniques collectées.")

    # --- PASSE 2 : enrichissement fiche détail ---
    if enrich_details and all_records:
        logger.info("Passe 2 : enrichissement via les fiches détail (photos + téléphone)...")
        all_records = enrich_with_details(all_records, session, detail_limiter)

    return all_records


if __name__ == "__main__":
    data = scrape_api(target=1000)
    export_to_json(data, "data/tayara/tayara.json")
    export_to_csv(data, "data/tayara/tayara.csv")
