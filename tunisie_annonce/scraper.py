"""
Scraper pour tunisie-annonce.com — rubrique Immobilier.
Remplit le schéma standard défini dans common/schema.py.

Structure observée (analyse HTML) :
- Liste d'annonces : http://www.tunisie-annonce.com/AnnoncesImmobilier.asp
  avec pagination via rech_page_num, et filtre transaction via rech_cod_typ
  (10101=Location, 10102=Vente, 10104=Terrain).
- Chaque ligne de résultat contient : région/localité, type de transaction,
  type de bien, titre + lien vers la fiche détail, prix, date de modification.
- Page HTML "à l'ancienne" (tableaux), aucun JavaScript nécessaire.

FICHE DÉTAIL — champs disponibles (observés sur le site) :
  Localisation : Tunisie > Gouvernorat > Délégation > Ville
  Adresse, Surface, Prix, Texte
  Insérée le JJ/MM/AAAA, Modifiée le JJ/MM/AAAA
  Photos : /upload2/YYYYMM/tunisie-annonce.com/photos/*.jpg (dupliquées dans le HTML)
  Contact Particulier : "Contact : Particulier Mob : XXXXXXXX"
  Contact Agence     : "Contact : Professionnel <NOM AGENCE> <ADRESSE> Tél : XXX Mob : XXX"
"""

import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from common.schema import new_listing
from common.utils import RateLimiter, deduplicate, export_to_csv, export_to_json, get_logger, safe_get

BASE_URL = "http://www.tunisie-annonce.com/AnnoncesImmobilier.asp"
SOURCE_NAME = "tunisie_annonce"

logger = get_logger(SOURCE_NAME)

# rech_cod_typ -> type de transaction normalisé
TRANSACTION_MAP = {
    "10101": "location",
    "10102": "vente",
    "10104": "vente",  # terrains, généralement en vente
}

TYPE_KEYWORDS = {
    "app.": "appartement",
    "maison": "villa",
    "villa": "villa",
    "terrain": "terrain",
    "bureau": "local_commercial",
    "duplex": "duplex",
    "surface": "local_commercial",
}


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


def parse_listing_page(html: str, transaction_code: str | None = None) -> list[dict]:
    """ÉTAPES 2+3+4 : lit le HTML (structure analysée plus haut dans ce
    fichier), et range chaque annonce trouvée dans le schéma commun défini
    dans common/schema.py."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for link in soup.select("a[href*='Details_Annonces_Immobilier.asp']"):
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if not title or not href:
            continue

        row = link.find_parent("tr")
        row_text = row.get_text(" ", strip=True) if row else link.parent.get_text(" ", strip=True)

        price_match = re.search(r"(?<![a-zA-Zàâéèêëïîôùûü])(\d{1,3}(?:\s\d{3})+|\d{4,})(?!\d)", row_text)
        price = _parse_price(price_match.group(1)) if price_match else None

        date_match = re.search(r"\d{2}/\d{2}/\d{4}", row_text)
        date_maj = date_match.group(0) if date_match else None

        localite_link = row.find("a", href=re.compile(r"rech_cod_loc")) if row else None
        localite = localite_link.get_text(strip=True) if localite_link else None

        full_url = href if href.startswith("http") else "http://www.tunisie-annonce.com/" + href.lstrip("/")

        listing = new_listing()
        listing["listing"].update({
            "id_source": _extract_id(full_url),
            "url_source": full_url,
            "date_scraping": now_iso,
            "date_maj": date_maj,
            "statut": "actif",
            "langue": "fr",
        })
        listing["transaction"].update({
            "type": TRANSACTION_MAP.get(transaction_code),
            "prix": price,
        })
        listing["bien"].update({
            "type": _guess_type(row_text),
        })
        listing["localisation"].update({
            "localite": localite,
        })
        listing["description"].update({
            "titre": title,
        })
        listing["metadonnees_scraping"].update({
            "source": SOURCE_NAME,
            "methode": "requests",
            "statut_scraping": "succes",
        })
        records.append(listing)

    return records


def scrape(max_pages: int = 3, transaction_code: str | None = None) -> list[dict]:
    """
    max_pages : nombre de pages de résultats à parcourir (~25-30 annonces/page)
    transaction_code : filtre optionnel, ex. "10102" pour Vente uniquement
                        (4453 annonces "Vente" dispo au total sur le site
                        au moment de l'analyse -> largement > 1000, donc
                        max_pages=40 suffit pour l'objectif de 1000+)
    """
    session = requests.Session()
    limiter = RateLimiter(min_delay=1.5, max_delay=3.0)  # ÉTAPE 5 : pause entre requêtes
    all_records = []

    for page in range(1, max_pages + 1):
        page_url = f"{BASE_URL}?rech_page_num={page}"
        if transaction_code:
            page_url += f"&rech_cod_typ={transaction_code}"

        # ÉTAPE 5 : requête HTTP avec retries automatiques (common/utils.safe_get)
        limiter.wait()
        start = time.time()
        resp = safe_get(page_url, session=session)
        elapsed_ms = int((time.time() - start) * 1000)

        if resp is None:
            logger.error(f"Page {page} ignorée (échec de la requête)")
            continue

        # ÉTAPE 4 : extraction des données depuis le HTML reçu
        records = parse_listing_page(resp.text, transaction_code=transaction_code)
        for r in records:
            r["metadonnees_scraping"]["temps_scraping_ms"] = elapsed_ms
        logger.info(f"Page {page} : {len(records)} annonces extraites (total : {len(all_records) + len(records)})")
        all_records.extend(records)

        if not records:
            logger.info("Plus d'annonces trouvées, arrêt anticipé.")
            break

    return deduplicate(all_records, key="listing.url_source")


# ---------------------------------------------------------------------------
# CORRECTIF — la surface (et la description complète, les dates de
# publication/modification, le type de contact...) ne sont PAS sur la page
# de liste, seulement sur la fiche détail. Champ observé sur la fiche :
#   "Surface 161,2 m²", "Adresse ...", "Insérée le JJ/MM/AAAA",
#   "Modifiée le JJ/MM/AAAA", "Contact : Particulier|Professionnel"
# ---------------------------------------------------------------------------
def parse_detail_page(html: str) -> dict:
    """Parse la fiche détail d'une annonce tunisie-annonce.com.

    Retourne un dict avec :
        surface_m2       : float ou None
        gouvernorat      : str ou None  (ex. "Tunis")
        delegation       : str ou None  (ex. "Carthage")
        ville            : str ou None  (ex. "Sidi Bousaid")
        adresse          : str ou None
        date_publication : str (JJ/MM/AAAA) ou None
        date_maj         : str (JJ/MM/AAAA) ou None
        type_vendeur     : "particulier" | "agence" | None
        nom_vendeur      : str ou None  (nom agence si Professionnel)
        adresse_agence   : str ou None
        telephone        : list[str]   (Tél + Mob combinés, dédupliqués)
        texte            : str ou None
        photos           : list[str]   (URLs absolues, dédupliquées)
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # --- Surface ---
    surface = None
    surf_match = re.search(r"Surface\s+([\d\s,.]+?)\s*m", text)
    if surf_match:
        try:
            surface = float(surf_match.group(1).strip().replace(" ", "").replace(",", "."))
        except ValueError:
            pass

    # --- Localisation : "Tunisie > Gouvernorat > Délégation > Ville" ---
    gouvernorat = delegation = ville = None
    loc_match = re.search(
        r"Localisation\s+Tunisie\s*>\s*([^>]+?)\s*>\s*([^>]+?)\s*>\s*([^A-Z][^\s>]+(?:\s+[^\s>]+)*?)\s+(?:Adresse|Surface|Prix|Texte)",
        text,
    )
    if loc_match:
        gouvernorat = loc_match.group(1).strip()
        delegation  = loc_match.group(2).strip()
        ville       = loc_match.group(3).strip()
    else:
        # Fallback : seulement gouvernorat + délégation (sans ville)
        loc2 = re.search(
            r"Localisation\s+Tunisie\s*>\s*([^>]+?)\s*>\s*([^A-Z][^\s>]+(?:\s+[^\s>]+)*?)\s+(?:Adresse|Surface|Prix|Texte)",
            text,
        )
        if loc2:
            gouvernorat = loc2.group(1).strip()
            delegation  = loc2.group(2).strip()

    # --- Adresse ---
    adresse = None
    adresse_match = re.search(r"Adresse\s+(.+?)\s+(?:Surface|Prix|Texte)", text)
    if adresse_match:
        adresse = adresse_match.group(1).strip()

    # --- Dates ---
    date_pub_match = re.search(r"Ins[ée]r[ée]e?\s+le\s+(\d{2}/\d{2}/\d{4})", text)
    date_publication = date_pub_match.group(1) if date_pub_match else None

    date_maj_match = re.search(r"Modifi[ée]e?\s+le\s+(\d{2}/\d{2}/\d{4})", text)
    date_maj = date_maj_match.group(1) if date_maj_match else None

    # --- Bloc Contact ---
    # Particulier : "Contact : Particulier Mob : 56497093"
    # Agence      : "Contact : Professionnel Business immobilière <adresse> Tél : 71709337 Mob : +216 98 532 100"
    type_vendeur = nom_vendeur = adresse_agence = None
    phones: list[str] = []

    contact_match = re.search(r"Contact\s*:\s*(Particulier|Professionnel)(.*?)(?:Mail\s*:|$)", text, re.DOTALL)
    if contact_match:
        kind = contact_match.group(1).strip()
        bloc = contact_match.group(2).strip()

        if kind == "Particulier":
            type_vendeur = "particulier"
        else:
            type_vendeur = "agence"
            # Le nom de l'agence est le premier morceau avant l'adresse/Tél/Mob
            # "Business immobilière 1 avenue mostapha hjeij 1 er étage A3 ariana 2080 Tél : ..."
            nom_match = re.match(r"^(.+?)\s+(?:\d|Tél\s*:|Mob\s*:)", bloc)
            if nom_match:
                nom_vendeur = nom_match.group(1).strip()
            # Adresse agence : entre nom et Tél/Mob
            addr_match = re.search(r"^.+?\s+(\d.+?)\s+(?:Tél\s*:|Mob\s*:)", bloc)
            if addr_match:
                adresse_agence = addr_match.group(1).strip()

        # Téléphones (Tél et Mob) — on extrait tous les numéros
        raw_phones = re.findall(r"(?:Tél|Mob)\s*:\s*([\d\s\+]{6,20})", bloc)
        for p in raw_phones:
            cleaned = re.sub(r"\s+", "", p.strip())
            if cleaned and cleaned not in phones:
                phones.append(cleaned)

    # --- Texte descriptif ---
    texte = None
    texte_match = re.search(r"Texte\s+(.+?)\s+Ins[ée]r[ée]e?\s+le", text, flags=re.DOTALL)
    if texte_match:
        texte = texte_match.group(1).strip()

    # --- Photos : /upload2/...jpg, dédupliquées, URLs absolues ---
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
        "surface_m2": surface,
        "gouvernorat": gouvernorat,
        "delegation": delegation,
        "ville": ville,
        "adresse": adresse,
        "date_publication": date_publication,
        "date_maj": date_maj,
        "type_vendeur": type_vendeur,
        "nom_vendeur": nom_vendeur,
        "adresse_agence": adresse_agence,
        "telephone": phones,
        "texte": texte,
        "photos": photos,
    }


def enrich_with_details(
    records: list[dict],
    session: requests.Session | None = None,
    limit: int | None = None,
    max_failures: int = 50,
) -> list[dict]:
    """Visite la fiche détail de chaque annonce pour compléter :
    - Toutes les photos
    - Gouvernorat + délégation + ville
    - Nom du vendeur (agence)
    - Tél + Mob
    - Surface, adresse, description, dates
    """
    session = session or requests.Session()
    limiter = RateLimiter(min_delay=1.5, max_delay=3.0)
    targets = records[:limit] if limit else records
    total = len(targets)
    failures = 0

    for i, listing in enumerate(targets, start=1):
        url = listing["listing"]["url_source"]
        if not url:
            continue

        limiter.wait()
        resp = safe_get(url, session=session)
        if resp is None:
            listing["metadonnees_scraping"]["erreurs"].append(f"Échec fiche détail: {url}")
            failures += 1
            if failures >= max_failures:
                logger.error("Trop d'échecs — arrêt de l'enrichissement.")
                break
            continue

        d = parse_detail_page(resp.text)

        # Surface
        if d["surface_m2"] is not None:
            listing["bien"]["superficie_totale"] = d["surface_m2"]

        # Localisation
        if d["gouvernorat"]:
            listing["localisation"]["gouvernorat"] = d["gouvernorat"]
        if d["delegation"]:
            listing["localisation"]["delegation"] = d["delegation"]
        if d["ville"]:
            listing["localisation"]["ville"] = d["ville"]
        if d["adresse"]:
            listing["localisation"]["adresse"] = d["adresse"]

        # Dates
        if d["date_publication"]:
            listing["listing"]["date_publication"] = d["date_publication"]
        if d["date_maj"]:
            listing["listing"]["date_maj"] = d["date_maj"]

        # Contact
        if d["type_vendeur"]:
            listing["contact"]["type_vendeur"] = d["type_vendeur"]
        if d["nom_vendeur"]:
            listing["contact"]["nom_vendeur"] = d["nom_vendeur"]
            listing["contact"]["nom_agence"]  = d["nom_vendeur"]
        if d["adresse_agence"]:
            listing["contact"]["site_web"] = None  # garder None, adresse_agence pas dans schema direct
            # On met l'adresse agence dans la localisation si pas d'adresse déjà
            if not listing["localisation"]["adresse"]:
                listing["localisation"]["adresse"] = d["adresse_agence"]
        if d["telephone"]:
            listing["contact"]["telephone"] = d["telephone"]

        # Description
        if d["texte"]:
            listing["description"]["texte"] = d["texte"]

        # Photos — toujours mettre à jour nombre_photos même si 0
        listing["medias"]["photos"] = [
            {"url": u, "url_thumb": None, "legende": None, "ordre": idx, "type": None}
            for idx, u in enumerate(d["photos"])
        ]
        listing["medias"]["nombre_photos"] = len(d["photos"])

        if i % 100 == 0:
            logger.info(f"Enrichissement fiches détail : {i}/{total}")

    logger.info(f"Enrichissement terminé : {total - failures}/{total} annonces traitées")
    return records


if __name__ == "__main__":
    # ~30 annonces/page -> 40 pages ≈ 1200 annonces (objectif 1000+)
    data = scrape(max_pages=40, transaction_code="10102")

    # Enrichissement avec les fiches détail (superficie, adresse, contact...)
    # met 'limit=' plus bas pour tester rapidement sur un échantillon.
    data = enrich_with_details(data)

    export_to_json(data, "data/tunisie_annonce/tunisie_annonce.json")
    export_to_csv(data, "data/tunisie_annonce/tunisie_annonce.csv")
