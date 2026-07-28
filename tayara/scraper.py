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

Comme la description complète est incluse dès la page de liste, on peut en
extraire la superficie (et chambres/salles de bain) directement par
expression régulière, sans avoir besoin de visiter chaque fiche détail.

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
SOURCE_NAME = "tayara"

logger = get_logger(SOURCE_NAME)

# Mapping observé subCategory (id Tayara) -> type de bien normalisé.
# À COMPLÉTER si de nouvelles valeurs de subCategory apparaissent dans les
# données (vérifiable en loggant metadata["subCategory"] pour les types
# non reconnus -> voir la fonction parse_api_page ci-dessous).
SUBCATEGORY_MAP = {
    "60be84bd50ab95b45b08a09c": "appartement",
    "60be84bd50ab95b45b08a09d": "villa",
    "60be84bd50ab95b45b08a09e": "appartement",  # locations saisonnières / meublées
    "60be84be50ab95b45b08a0a0": "local_commercial",
    "60be84be50ab95b45b08a0a1": "terrain",
    "60be84be50ab95b45b08a09f": "local_commercial",  # bureaux
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


def get_build_id(session: requests.Session) -> str | None:
    """Récupère l'identifiant de build Next.js actuel depuis le HTML de la
    page catégorie (change à chaque déploiement du site)."""
    resp = safe_get(CATEGORY_PAGE_URL, session=session)
    if resp is None:
        return None
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    return match.group(1) if match else None


def parse_api_page(data: dict) -> list[dict]:
    """ÉTAPES 2+3+4 : transforme la réponse JSON de l'API Tayara en annonces
    respectant le schéma commun (common/schema.py)."""
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
            "methode": "api",
            "statut_scraping": "succes",
        })
        records.append(listing)

    return records


def scrape_api(target: int = 1000, max_pages: int = 200) -> list[dict]:
    """Pagine l'API interne de Tayara jusqu'à atteindre 'target' annonces
    (ou la fin du catalogue). ~24-30 annonces par page selon la catégorie."""
    session = requests.Session()
    limiter = RateLimiter(min_delay=1.0, max_delay=2.0)  # ÉTAPE 5 : pause entre requêtes

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

    for page in range(1, max_pages + 1):
        limiter.wait()  # ÉTAPE 5 : limite de fréquence
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

        records = parse_api_page(data)  # ÉTAPE 4 : extraction
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

    return deduplicate(all_records, key="listing.url_source")


if __name__ == "__main__":
    data = scrape_api(target=1000)
    export_to_json(data, "data/tayara/tayara.json")
    export_to_csv(data, "data/tayara/tayara.csv")