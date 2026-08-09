"""
Scraper pour tunisie-annonce.com — rubrique Immobilier.

Pipeline (convention PropHunter) :
    scrape_links(data=None)  → list[dict]   (annonces brutes depuis les pages listing)
    scrape_details(data)     → list[dict]   (enrichissement fiche détail par annonce)
    normaliser(data)         → list[dict]   (format standard PropHunter)

Structure observée :
- Liste : http://www.tunisie-annonce.com/AnnoncesImmobilier.asp
  Pagination via rech_page_num, filtre transaction via rech_cod_typ
  (10101=Location, 10102=Vente, 10104=Terrain)
- Fiche détail : /Details_Annonces_Immobilier.asp?cod_ann=XXXX
  Contient surface, localisation complète, contact, photos
"""

import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.scrapers.common.schema import new_listing
from app.scrapers.common.utils import RateLimiter, deduplicate, get_logger, safe_get

BASE_URL    = "http://www.tunisie-annonce.com/AnnoncesImmobilier.asp"
SOURCE_NAME = "tunisie_annonce"

# ~30 annonces/page — mettre 40 en production
MAX_PAGES = 1   # ← TEST : 1 page suffit pour avoir ~30 annonces avant le [:10]

# rech_cod_typ → type de transaction normalisé
TRANSACTION_MAP = {
    "10101": "location",
    "10102": "vente",
    "10104": "vente",   # terrains
}

TYPE_KEYWORDS = {
    "app.":    "appartement",
    "maison":  "villa",
    "villa":   "villa",
    "terrain": "terrain",
    "bureau":  "local_commercial",
    "duplex":  "duplex",
    "surface": "local_commercial",
}

logger = get_logger(SOURCE_NAME)


# ─── Helpers internes ────────────────────────────────────────────────────────

def _parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _extract_id(url: str) -> str | None:
    match = re.search(r"cod_ann=(\d+)", url)
    return match.group(1) if match else None


def _guess_type(text: str) -> str | None:
    low = text.lower()
    for kw, normalized in TYPE_KEYWORDS.items():
        if kw in low:
            return normalized
    return None


def _parse_listing_page(html: str, transaction_code: str | None = None) -> list[dict]:
    """Parse une page de liste et retourne des annonces au format intermédiaire _champs."""
    soup    = BeautifulSoup(html, "lxml")
    records = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for link in soup.select("a[href*='Details_Annonces_Immobilier.asp']"):
        href  = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or not href:
            continue

        row      = link.find_parent("tr")
        row_text = row.get_text(" ", strip=True) if row else link.parent.get_text(" ", strip=True)

        price_match = re.search(
            r"(?<![a-zA-Zàâéèêëïîôùûü])(\d{1,3}(?:\s\d{3})+|\d{4,})(?!\d)", row_text
        )
        price = _parse_price(price_match.group(1)) if price_match else None

        date_match = re.search(r"\d{2}/\d{2}/\d{4}", row_text)
        date_maj   = date_match.group(0) if date_match else None

        localite_link = row.find("a", href=re.compile(r"rech_cod_loc")) if row else None
        localite      = localite_link.get_text(strip=True) if localite_link else None

        full_url = (
            href if href.startswith("http")
            else "http://www.tunisie-annonce.com/" + href.lstrip("/")
        )

        records.append({
            "_id_source":         _extract_id(full_url),
            "_url":               full_url,
            "_date_scraping":     now_iso,
            "_date_maj":          date_maj,
            "_date_publication":  None,
            "_transaction":       TRANSACTION_MAP.get(transaction_code),
            "_prix":              price,
            "_type_bien":         _guess_type(row_text),
            "_localite":          localite,
            "_gouvernorat":       None,
            "_delegation":        None,
            "_ville":             None,
            "_adresse":           None,
            "_superficie":        None,
            "_type_vendeur":      None,
            "_nom_vendeur":       None,
            "_telephone":         [],
            "_description":       None,
            "_photos":            [],
            "_titre":             title,
        })

    return records


def _parse_detail_page(html: str) -> dict:
    """Parse la fiche détail et retourne un dict avec les champs enrichis."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # Surface
    surface = None
    surf_match = re.search(r"Surface\s+([\d\s,.]+?)\s*m", text)
    if surf_match:
        try:
            surface = float(
                surf_match.group(1).strip().replace(" ", "").replace(",", ".")
            )
        except ValueError:
            pass

    # Localisation : "Tunisie > Gouvernorat > Délégation > Ville"
    gouvernorat = delegation = ville = None
    loc_match = re.search(
        r"Localisation\s+Tunisie\s*>\s*([^>]+?)\s*>\s*([^>]+?)\s*>\s*"
        r"([^A-Z][^\s>]+(?:\s+[^\s>]+)*?)\s+(?:Adresse|Surface|Prix|Texte)",
        text,
    )
    if loc_match:
        gouvernorat = loc_match.group(1).strip()
        delegation  = loc_match.group(2).strip()
        ville       = loc_match.group(3).strip()
    else:
        loc2 = re.search(
            r"Localisation\s+Tunisie\s*>\s*([^>]+?)\s*>\s*"
            r"([^A-Z][^\s>]+(?:\s+[^\s>]+)*?)\s+(?:Adresse|Surface|Prix|Texte)",
            text,
        )
        if loc2:
            gouvernorat = loc2.group(1).strip()
            delegation  = loc2.group(2).strip()

    # Adresse
    adresse = None
    adresse_match = re.search(r"Adresse\s+(.+?)\s+(?:Surface|Prix|Texte)", text)
    if adresse_match:
        adresse = adresse_match.group(1).strip()

    # Dates
    date_pub_match = re.search(r"Ins[ée]r[ée]e?\s+le\s+(\d{2}/\d{2}/\d{4})", text)
    date_publication = date_pub_match.group(1) if date_pub_match else None

    date_maj_match = re.search(r"Modifi[ée]e?\s+le\s+(\d{2}/\d{2}/\d{4})", text)
    date_maj = date_maj_match.group(1) if date_maj_match else None

    # Contact
    type_vendeur = nom_vendeur = adresse_agence = None
    phones: list[str] = []

    contact_match = re.search(
        r"Contact\s*:\s*(Particulier|Professionnel)(.*?)(?:Mail\s*:|$)",
        text, re.DOTALL,
    )
    if contact_match:
        kind = contact_match.group(1).strip()
        bloc = contact_match.group(2).strip()

        if kind == "Particulier":
            type_vendeur = "particulier"
        else:
            type_vendeur = "agence"
            nom_match = re.match(r"^(.+?)\s+(?:\d|Tél\s*:|Mob\s*:)", bloc)
            if nom_match:
                nom_vendeur = nom_match.group(1).strip()
            addr_match = re.search(r"^.+?\s+(\d.+?)\s+(?:Tél\s*:|Mob\s*:)", bloc)
            if addr_match:
                adresse_agence = addr_match.group(1).strip()

        raw_phones = re.findall(r"(?:Tél|Mob)\s*:\s*([\d\s\+]{6,20})", bloc)
        for p in raw_phones:
            cleaned = re.sub(r"\s+", "", p.strip())
            if cleaned and cleaned not in phones:
                phones.append(cleaned)

    # Texte descriptif
    texte = None
    texte_match = re.search(
        r"Texte\s+(.+?)\s+Ins[ée]r[ée]e?\s+le", text, flags=re.DOTALL
    )
    if texte_match:
        texte = texte_match.group(1).strip()

    # Photos
    BASE = "http://www.tunisie-annonce.com"
    seen_photos: set[str] = set()
    photos: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "/upload2/" in src and src.endswith(".jpg"):
            full = src if src.startswith("http") else BASE + src
            if full not in seen_photos:
                seen_photos.add(full)
                photos.append(full)

    return {
        "surface_m2":       surface,
        "gouvernorat":      gouvernorat,
        "delegation":       delegation,
        "ville":            ville,
        "adresse":          adresse,
        "date_publication": date_publication,
        "date_maj":         date_maj,
        "type_vendeur":     type_vendeur,
        "nom_vendeur":      nom_vendeur,
        "adresse_agence":   adresse_agence,
        "telephone":        phones,
        "texte":            texte,
        "photos":           photos,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FONCTIONS PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_links(data=None) -> list[dict]:
    """
    ÉTAPE 1 — Parcourt les pages listing de tunisie-annonce.com et collecte
    toutes les annonces immobilières (vente + location).

    Args:
        data: ignoré (convention pipeline — premier maillon reçoit None)

    Returns:
        list[dict]: annonces brutes au format intermédiaire _champs
    """
    session     = requests.Session()
    limiter     = RateLimiter(min_delay=1.5, max_delay=3.0)
    all_records = []

    # On scrape vente (10102) + location (10101) pour couvrir les 2 types
    for transaction_code in ("10102", "10101"):
        logger.info(f"[TunisieAnnonce] Code transaction : {transaction_code}")

        for page in range(1, MAX_PAGES + 1):
            page_url = f"{BASE_URL}?rech_page_num={page}&rech_cod_typ={transaction_code}"

            limiter.wait()
            start      = time.time()
            resp       = safe_get(page_url, session=session)
            elapsed_ms = int((time.time() - start) * 1000)

            if resp is None:
                logger.error(f"[TunisieAnnonce] Page {page} ignorée (échec requête)")
                continue

            records = _parse_listing_page(resp.text, transaction_code=transaction_code)
            for r in records:
                r["_temps_scraping_ms"] = elapsed_ms

            logger.info(
                f"[TunisieAnnonce] tx={transaction_code} page={page} : "
                f"{len(records)} annonces (total : {len(all_records) + len(records)})"
            )
            all_records.extend(records)

            if not records:
                logger.info("[TunisieAnnonce] Page vide — fin de cette transaction.")
                break

    deduped = deduplicate(all_records, key="listing.url_source")
    # deduplicate attend le schéma standard, on fait une dédup manuelle ici
    seen  = set()
    unique = []
    for r in all_records:
        url = r.get("_url")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    # ── Limite pour les tests — retirer en production ──────────────────────
    unique = unique[:10]
    # ───────────────────────────────────────────────────────────────────────

    logger.info(f"[TunisieAnnonce] scrape_links terminé : {len(unique)} annonces uniques")
    return unique


def scrape_details(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 2 — Visite la fiche détail de chaque annonce pour enrichir :
    surface, localisation complète (gouvernorat/délégation/ville),
    contact (téléphone, nom agence), description, photos.

    Args:
        data: liste d'annonces brutes (sortie de scrape_links)

    Returns:
        list[dict]: annonces enrichies
    """
    session      = requests.Session()
    limiter      = RateLimiter(min_delay=1.5, max_delay=3.0)
    total        = len(data)
    failures     = 0
    MAX_FAILURES = 50

    for i, listing in enumerate(data, start=1):
        url = listing.get("_url")
        if not url:
            continue

        limiter.wait()
        resp = safe_get(url, session=session)

        if resp is None:
            listing["_erreurs"] = [f"Échec fiche détail : {url}"]
            failures += 1
            if failures >= MAX_FAILURES:
                logger.error("[TunisieAnnonce] Trop d'échecs — arrêt enrichissement.")
                break
            continue

        d = _parse_detail_page(resp.text)

        if d["surface_m2"] is not None:
            listing["_superficie"] = d["surface_m2"]
        if d["gouvernorat"]:
            listing["_gouvernorat"] = d["gouvernorat"]
        if d["delegation"]:
            listing["_delegation"] = d["delegation"]
        if d["ville"]:
            listing["_ville"] = d["ville"]
        if d["adresse"]:
            listing["_adresse"] = d["adresse"]
        if d["date_publication"]:
            listing["_date_publication"] = d["date_publication"]
        if d["date_maj"]:
            listing["_date_maj"] = d["date_maj"]
        if d["type_vendeur"]:
            listing["_type_vendeur"] = d["type_vendeur"]
        if d["nom_vendeur"]:
            listing["_nom_vendeur"] = d["nom_vendeur"]
        if d["telephone"]:
            listing["_telephone"] = d["telephone"]
        if d["texte"]:
            listing["_description"] = d["texte"]

        listing["_photos"] = [
            {"url": u, "url_thumb": None, "legende": None, "ordre": idx, "type": None}
            for idx, u in enumerate(d["photos"])
        ]

        if i % 100 == 0:
            logger.info(f"[TunisieAnnonce] Enrichissement : {i}/{total}")

    logger.info(
        f"[TunisieAnnonce] scrape_details terminé : {total - failures}/{total} enrichies"
    )
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
        photos    = r.get("_photos", [])

        listing = new_listing()
        listing["listing"].update({
            "id_source":        id_source,
            "id_universel":     f"tunisie_annonce_{id_source}" if id_source else None,
            "url_source":       r.get("_url"),
            "url_canonique":    r.get("_url"),
            "date_scraping":    now_iso,
            "date_publication": r.get("_date_publication"),
            "date_maj":         r.get("_date_maj"),
            "statut":           "actif",
            "langue":           "fr",
        })
        listing["transaction"].update({
            "type": r.get("_transaction"),
            "prix": r.get("_prix"),
        })
        listing["bien"].update({
            "type":              r.get("_type_bien"),
            "superficie_totale": r.get("_superficie"),
        })
        listing["localisation"].update({
            "gouvernorat": r.get("_gouvernorat"),
            "delegation":  r.get("_delegation"),
            "ville":       r.get("_ville") or r.get("_localite"),
            "localite":    r.get("_localite"),
            "adresse":     r.get("_adresse"),
        })
        listing["description"].update({
            "titre": r.get("_titre"),
            "texte": r.get("_description"),
        })
        listing["medias"].update({
            "photos":        (
                photos if (photos and isinstance(photos[0], dict))
                else [
                    {"url": u, "url_thumb": None, "legende": None, "ordre": idx, "type": None}
                    for idx, u in enumerate(photos)
                ]
            ),
            "nombre_photos": len(photos),
        })
        listing["contact"].update({
            "type_vendeur": r.get("_type_vendeur"),
            "nom_vendeur":  r.get("_nom_vendeur"),
            "nom_agence":   r.get("_nom_vendeur") if r.get("_type_vendeur") == "agence" else None,
            "telephone":    r.get("_telephone", []),
        })
        listing["metadonnees_scraping"].update({
            "source":            SOURCE_NAME,
            "methode":           "requests",
            "statut_scraping":   "succes",
            "erreurs":           r.get("_erreurs", []),
            "temps_scraping_ms": r.get("_temps_scraping_ms"),
        })

        results.append(listing)

    exclues = len(data) - len(results)
    logger.info(
        f"[TunisieAnnonce] normaliser terminé : {len(results)} annonces ({exclues} exclues)"
    )
    return results
