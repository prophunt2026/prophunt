"""
Scraper pour tayara.tn — catégorie Immobilier, via l'API interne du site.

DÉCOUVERTE CLÉ (analyse du trafic réseau) :
Tayara charge ses résultats via un endpoint JSON interne (Next.js) :

    https://www.tayara.tn/_next/data/<BUILD_ID>/en/listing/c/immobilier.json
        ?category=immobilier&page=N

Pipeline (convention PropHunter) :
    scrape_links(data=None)   → list[dict]   (annonces brutes depuis l'API listing)
    scrape_details(data)      → list[dict]   (enrichissement fiche HTML par annonce)
    normaliser(data)          → list[dict]   (format standard PropHunter)
"""

import re
import time
from datetime import datetime, timezone

import requests

from app.scrapers.common.schema import new_listing
from app.scrapers.common.utils import RateLimiter, deduplicate, get_logger, safe_get

CATEGORY_PAGE_URL   = "https://www.tayara.tn/listing/c/immobilier/"
API_URL_TEMPLATE    = "https://www.tayara.tn/_next/data/{build_id}/en/listing/c/immobilier.json"
ITEM_PAGE_URL_TEMPLATE = "https://www.tayara.tn/item/{listing_id}/"
SOURCE_NAME         = "tayara"

TARGET_ANNONCES = 10
MAX_PAGES       = 2

logger = get_logger(SOURCE_NAME)

# ─── Tables de correspondance ────────────────────────────────────────────────

SUBCATEGORY_MAP = {
    "60be84bd50ab95b45b08a09c": "appartement",
    "60be84bd50ab95b45b08a09d": "villa",
    "60be84bd50ab95b45b08a09e": "appartement",
    "60be84be50ab95b45b08a0a0": "local_commercial",
    "60be84be50ab95b45b08a0a1": "terrain",
    "60be84be50ab95b45b08a09f": "local_commercial",
}

ADPARAM_LABEL_MAP = {
    "superficie":             "superficie_totale",
    "superficie (m²)":        "superficie_totale",
    "surface":                "superficie_totale",
    "chambres":               "nombre_chambres",
    "salles de bains":        "nombre_salles_bain",
    "salle de bain":          "nombre_salles_bain",
    "salles de bain":         "nombre_salles_bain",
}

TRANSACTION_TYPE_MAP = {
    "à vendre":  "vente",
    "a vendre":  "vente",
    "vente":     "vente",
    "à louer":   "location",
    "a louer":   "location",
    "location":  "location",
}

SURFACE_PATTERNS = [
    r"[Ss]uperficie[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*m",
    r"[Ss]urface[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*m",
]
CHAMBRES_PATTERN     = re.compile(r"(\d+)\s*chambres?\s*(?:à coucher)?", re.IGNORECASE)
SDB_PATTERN          = re.compile(r"(\d+)\s*salles?\s*(?:de\s*)?bain", re.IGNORECASE)
SDB_SINGULAR_PATTERN = re.compile(r"\bsalle\s+de\s+bain\b", re.IGNORECASE)


# ─── Helpers internes ────────────────────────────────────────────────────────

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
    if not value:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _parse_adparam_int(value: str) -> int | None:
    f = _parse_adparam_float(value)
    return int(f) if f is not None else None


def _get_build_id(session: requests.Session) -> str | None:
    """Récupère le buildId Next.js dynamiquement depuis le HTML de la page catégorie."""
    resp = safe_get(CATEGORY_PAGE_URL, session=session)
    if resp is None:
        return None
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    return match.group(1) if match else None


def _fetch_detail(listing_id: str, session: requests.Session) -> dict | None:
    """Visite la fiche HTML /item/ID/ pour récupérer photos complètes, téléphone, adParams."""
    url  = ITEM_PAGE_URL_TEMPLATE.format(listing_id=listing_id)
    resp = safe_get(url, session=session)
    if resp is None:
        return None

    if resp.url and "/item/" not in resp.url:
        logger.debug(f"Annonce {listing_id} expirée (redirigée vers {resp.url})")
        return None

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        resp.text, re.DOTALL,
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
    ad   = page_props.get("adDetails") or {}
    user = page_props.get("adUserData") or {}

    if not ad:
        return None

    images = ad.get("images") or []
    phone  = ad.get("phone") or user.get("phonenumber") or None

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
            ad_params["type_transaction"] = TRANSACTION_TYPE_MAP.get(value_raw.lower())

    vendor_name    = user.get("fullname") or ad.get("publisher", {}).get("name") or None
    vendor_email   = user.get("email") or None
    vendor_is_shop = bool(user.get("isShop") or ad.get("publisher", {}).get("isShop"))
    vendor_url     = user.get("url") or None
    vendor_avatar  = user.get("avatar") or ad.get("publisher", {}).get("avatar") or None

    return {
        "images":        images,
        "phone":         phone,
        "ad_params":     ad_params,
        "vendor_name":   vendor_name,
        "vendor_email":  vendor_email,
        "vendor_is_shop": vendor_is_shop,
        "vendor_url":    vendor_url,
        "vendor_avatar": vendor_avatar,
    }


def _parse_api_page(data: dict) -> list[dict]:
    """Transforme une page JSON de l'API Tayara en liste d'annonces brutes."""
    hits = (
        data.get("pageProps", {})
            .get("searchedListingsAction", {})
            .get("newHits", [])
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    records = []

    for hit in hits:
        metadata  = hit.get("metadata", {}) or {}
        publisher = metadata.get("publisher", {}) or {}
        location  = hit.get("location", {}) or {}
        description = hit.get("description") or ""
        title       = hit.get("title") or ""
        sub_category = metadata.get("subCategory")

        # On stocke la donnée brute dans le format intermédiaire
        # (pas encore le schéma standard — normaliser() fera ça)
        record = {
            "_id_source":       hit.get("id"),
            "_url":             f"https://www.tayara.tn/item/{hit.get('id')}/",
            "_date_scraping":   now_iso,
            "_date_publication": metadata.get("publishedOn"),
            "_prix":            hit.get("price"),
            "_type_bien":       SUBCATEGORY_MAP.get(sub_category),
            "_superficie":      _guess_float(description, SURFACE_PATTERNS),
            "_chambres":        int(m.group(1)) if (m := CHAMBRES_PATTERN.search(description)) else None,
            "_salles_bain":     _guess_salles_bain(description),
            "_gouvernorat":     location.get("governorate"),
            "_delegation":      location.get("delegation"),
            "_titre":           title or None,
            "_description":     description or None,
            "_images":          hit.get("images", []) or [],
            "_type_vendeur":    "agence" if publisher.get("isShop") else "particulier",
            "_nom_vendeur":     publisher.get("name") or None,
            "_transaction":     None,   # complété lors de scrape_details
            "_telephone":       [],
            "_email":           None,
            "_site_web":        None,
            "_photo_agence":    None,
        }
        records.append(record)

    return records


# ═══════════════════════════════════════════════════════════════════════════════
# FONCTIONS PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_links(data=None) -> list[dict]:
    """
    ÉTAPE 1 — Collecte toutes les annonces via l'API JSON interne de Tayara.

    Args:
        data: ignoré (convention pipeline — premier maillon reçoit None)

    Returns:
        list[dict]: annonces brutes (format intermédiaire _champs)
    """
    session        = requests.Session()
    listing_limiter = RateLimiter(min_delay=1.0, max_delay=2.0)

    build_id = _get_build_id(session)
    if not build_id:
        logger.error("Impossible de récupérer le buildId Next.js de Tayara.")
        return []

    logger.info(f"[Tayara] buildId détecté : {build_id}")
    api_url    = API_URL_TEMPLATE.format(build_id=build_id)
    all_records = []

    for page in range(1, MAX_PAGES + 1):
        listing_limiter.wait()
        start = time.time()
        resp  = safe_get(f"{api_url}?category=immobilier&page={page}", session=session)
        elapsed_ms = int((time.time() - start) * 1000)

        if resp is None:
            logger.error(f"[Tayara] Page {page} ignorée (échec requête)")
            continue

        try:
            data_page = resp.json()
        except ValueError:
            logger.error(f"[Tayara] Page {page} : réponse non-JSON (buildId expiré?), arrêt.")
            break

        records = _parse_api_page(data_page)
        for r in records:
            r["_temps_scraping_ms"] = elapsed_ms
        all_records.extend(records)
        logger.info(f"[Tayara] Page {page} : +{len(records)} → {len(all_records)} total")

        if not records:
            logger.info("[Tayara] Page vide — fin du catalogue.")
            break
        if len(all_records) >= TARGET_ANNONCES:
            logger.info(f"[Tayara] Objectif {TARGET_ANNONCES} atteint.")
            break

    # Déduplication par URL
    seen  = set()
    unique = []
    for r in all_records:
        url = r.get("_url")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    if len(unique) > TARGET_ANNONCES:
        unique = unique[:TARGET_ANNONCES]

    logger.info(f"[Tayara] scrape_links terminé : {len(unique)} annonces uniques")
    return unique


def scrape_details(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 2 — Enrichit chaque annonce en visitant sa fiche HTML /item/ID/.

    Ajoute : toutes les photos, téléphone, adParams structurés, données vendeur.

    Args:
        data: liste d'annonces brutes (sortie de scrape_links)

    Returns:
        list[dict]: annonces enrichies
    """
    session        = requests.Session()
    detail_limiter = RateLimiter(min_delay=1.5, max_delay=3.0)
    total          = len(data)
    failures       = 0
    MAX_FAILURES   = 50

    for i, record in enumerate(data):
        listing_id = record.get("_id_source")
        if not listing_id:
            continue

        detail_limiter.wait()
        logger.info(f"[Tayara] Enrichissement {i + 1}/{total} : {listing_id}")

        detail = _fetch_detail(listing_id, session)

        if detail is None:
            record["_statut"] = "expiré"
            failures += 1
            logger.warning(f"[Tayara] Détail introuvable pour {listing_id} ({failures}/{MAX_FAILURES})")
            if failures >= MAX_FAILURES:
                logger.error("[Tayara] Trop d'échecs détail — arrêt enrichissement.")
                break
            continue

        # Photos complètes
        if detail["images"]:
            record["_images"] = detail["images"]

        # Téléphone
        if detail["phone"]:
            record["_telephone"] = [detail["phone"]]

        # Champs structurés depuis adParams
        ap = detail["ad_params"]
        if ap.get("superficie_totale") is not None:
            record["_superficie"] = ap["superficie_totale"]
        if ap.get("nombre_chambres") is not None:
            record["_chambres"] = ap["nombre_chambres"]
        if ap.get("nombre_salles_bain") is not None:
            record["_salles_bain"] = ap["nombre_salles_bain"]
        if ap.get("type_transaction") is not None:
            record["_transaction"] = ap["type_transaction"]

        # Vendeur
        if detail["vendor_name"]:
            record["_nom_vendeur"] = detail["vendor_name"]
        if detail["vendor_email"]:
            record["_email"] = detail["vendor_email"]
        if detail["vendor_url"]:
            record["_site_web"] = detail["vendor_url"]
        if detail["vendor_avatar"]:
            record["_photo_agence"] = detail["vendor_avatar"]
        record["_type_vendeur"] = "agence" if detail["vendor_is_shop"] else "particulier"

    logger.info(f"[Tayara] scrape_details terminé : {total - failures}/{total} enrichies")
    return data


def normaliser(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 3 — Convertit les annonces enrichies au format standard PropHunter.

    Args:
        data: liste d'annonces enrichies (sortie de scrape_details)

    Returns:
        list[dict]: annonces au format standard PropHunter
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    results = []

    for r in data:
        id_source = r.get("_id_source")
        images    = r.get("_images", [])

        listing = new_listing()
        listing["listing"].update({
            "id_source":        id_source,
            "id_universel":     f"tayara_{id_source}" if id_source else None,
            "url_source":       r.get("_url"),
            "url_canonique":    r.get("_url"),
            "date_scraping":    now_iso,
            "date_publication": r.get("_date_publication"),
            "statut":           r.get("_statut", "actif"),
            "langue":           "ar" if re.search(r"[\u0600-\u06FF]", r.get("_titre") or "") else "fr",
        })
        listing["transaction"].update({
            "type":  r.get("_transaction"),
            "prix":  r.get("_prix"),
        })
        listing["bien"].update({
            "type":              r.get("_type_bien"),
            "superficie_totale": r.get("_superficie"),
            "nombre_chambres":   r.get("_chambres"),
            "nombre_salles_bain": r.get("_salles_bain"),
        })
        listing["localisation"].update({
            "gouvernorat": r.get("_gouvernorat"),
            "delegation":  r.get("_delegation"),
        })
        listing["description"].update({
            "titre": r.get("_titre"),
            "texte": r.get("_description"),
        })
        listing["medias"].update({
            "photos": [
                {"url": u, "url_thumb": None, "legende": None, "ordre": i, "type": None}
                for i, u in enumerate(images)
            ],
            "nombre_photos": len(images),
        })
        listing["contact"].update({
            "type_vendeur": r.get("_type_vendeur"),
            "nom_vendeur":  r.get("_nom_vendeur"),
            "telephone":    r.get("_telephone", []),
            "email":        r.get("_email"),
            "site_web":     r.get("_site_web"),
            "photo_agence": r.get("_photo_agence"),
        })
        listing["metadonnees_scraping"].update({
            "source":            SOURCE_NAME,
            "methode":           "api+html",
            "statut_scraping":   "succes",
            "temps_scraping_ms": r.get("_temps_scraping_ms"),
        })

        results.append(listing)

    exclues = len(data) - len(results)
    logger.info(f"[Tayara] normaliser terminé : {len(results)} annonces ({exclues} exclues)")
    return results
