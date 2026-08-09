"""
pipeline.py — Fonctions pipeline PropHunter pour home_in_tunisia.

Convention :
    scrape_links(data=None)  → list[dict]   (items bruts vente + location)
    scrape_details(data)     → list[dict]   (annonces au format standard PropHunter)
    normaliser(data)         → list[dict]   (dédup + id_universel garanti)

Particularité : scraper.py et scraper_location.py utilisent sync_playwright.
On bridge via concurrent.futures.ThreadPoolExecutor pour éviter les conflits
d'event loop avec uvicorn (même approche que fi_dari).

Pas de fichier JSON : toutes les données vont directement dans MongoDB
via property_repository.save_properties() appelé par scraping_service.py.
"""

import concurrent.futures
import sys
from datetime import datetime, timezone

from app.scrapers.common.utils import get_logger
from app.scrapers.scraper_Home_in_Tunisia.parsers import is_valid_record

SOURCE_NAME = "home_in_tunisia"
logger = get_logger(SOURCE_NAME)

# Limite pour les tests — mettre None en production
TEST_LIMIT: int | None = 20


# ─── Bridge sync → thread isolé ──────────────────────────────────────────────

def _run_in_thread(fn, *args, **kwargs):
    """
    Exécute une fonction synchrone (sync_playwright) dans un thread dédié.
    Sur Windows, sync_playwright crée en interne un event loop via asyncio.
    On force WindowsProactorEventLoopPolicy AVANT l'appel pour éviter
    NotImplementedError sur subprocess_exec (Chromium).
    """
    import sys

    def _wrapper():
        if sys.platform == "win32":
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return fn(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_wrapper)
        return future.result()


# ═══════════════════════════════════════════════════════════════════════════════
# FONCTIONS PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_links(data=None) -> list[dict]:
    """
    ÉTAPE 1 — Collecte les items bruts depuis homeintunisia.com :
    - Vente    : /fr/acheter       (scroll infini Playwright)
    - Location : /fr/recherche?search_property_category=2 (scroll infini Playwright)

    Retourne une liste de dicts intermédiaires :
        { url, id, type_liste, nombre_pieces_liste, ..., _transaction: "vente"|"location" }

    Args:
        data: ignoré (convention pipeline — premier maillon reçoit None)

    Returns:
        list[dict]: items bruts avec _transaction taggé
    """
    from app.scrapers.scraper_Home_in_Tunisia.scraper import fetch_listing_items_with_playwright
    from app.scrapers.scraper_Home_in_Tunisia.scraper_location import fetch_listing_items_location_with_playwright
    from app.scrapers.scraper_Home_in_Tunisia.config import USER_AGENT
    from playwright.sync_api import sync_playwright

    all_items: list[dict] = []

    # ── Vente ─────────────────────────────────────────────────────────────────
    def _collect_vente():
        import sys
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.info("[HomeInTunisia] Collecte vente (Playwright)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            try:
                items = fetch_listing_items_with_playwright(page, max_scrolls=8)
                logger.info(f"[HomeInTunisia] Vente : {len(items)} items collectés")
                return items
            finally:
                browser.close()

    # ── Location ──────────────────────────────────────────────────────────────
    def _collect_location():
        import sys
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.info("[HomeInTunisia] Collecte location (Playwright)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            try:
                items = fetch_listing_items_location_with_playwright(page, max_scrolls=8)
                logger.info(f"[HomeInTunisia] Location : {len(items)} items collectés")
                return items
            finally:
                browser.close()

    vente_items    = _run_in_thread(_collect_vente)
    location_items = _run_in_thread(_collect_location)

    # Tagger la transaction sur chaque item
    for item in vente_items:
        item["_transaction"] = "vente"
    for item in location_items:
        item["_transaction"] = "location"

    all_items = vente_items + location_items

    # Déduplication par URL
    seen  = set()
    unique = []
    for item in all_items:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)

    # Limite test
    if TEST_LIMIT is not None:
        unique = unique[:TEST_LIMIT]
        logger.info(f"[HomeInTunisia] Mode test : limité à {TEST_LIMIT} items")

    logger.info(f"[HomeInTunisia] scrape_links terminé : {len(unique)} items uniques")
    return unique


def scrape_details(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 2 — Pour chaque item brut, visite la fiche détail via requests
    et construit l'annonce au format standard PropHunter (build_record).

    scraper.py et scraper_location.py téléchargent les fiches détail
    avec requests (pas Playwright) — pas besoin de bridge thread ici.

    Args:
        data: liste d'items bruts (sortie de scrape_links)

    Returns:
        list[dict]: annonces au format standard PropHunter (valides uniquement)
    """
    import time
    import requests
    from app.scrapers.scraper_Home_in_Tunisia.parsers import build_record
    from app.scrapers.scraper_Home_in_Tunisia.config import HEADERS

    total   = len(data)
    results = []
    ignored = 0

    for i, item in enumerate(data, start=1):
        url = item.get("url")
        if not url:
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            record = build_record(resp.text, url, listing_extra=item)

            # Forcer le type de transaction depuis le tag posé dans scrape_links
            # (plus fiable que l'inférence HTML sur certaines fiches)
            if item.get("_transaction"):
                record["transaction"]["type"] = item["_transaction"]
                if item["_transaction"] == "location":
                    record["transaction"]["loyer_mensuel"] = (
                        record["transaction"].get("loyer_mensuel")
                        or item.get("loyer_liste")
                    )

            is_valid, reason = is_valid_record(record)
            if not is_valid:
                logger.info(f"[HomeInTunisia] {i}/{total} ignoré ({reason}) : {url}")
                ignored += 1
                continue

            results.append(record)
            logger.info(
                f"[HomeInTunisia] {i}/{total} OK "
                f"({record['bien']['type']}, {record['transaction']['type']})"
            )

        except requests.RequestException as e:
            logger.warning(f"[HomeInTunisia] Erreur fetch {url} : {e}")

        time.sleep(1.0)

    logger.info(
        f"[HomeInTunisia] scrape_details terminé : "
        f"{len(results)} annonces ({ignored} ignorées)"
    )
    return results


def normaliser(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 3 — Déduplication par id_universel + garantit que chaque annonce
    a un id_universel PropHunter (fallback sur l'URL si id_source absent).

    Args:
        data: annonces au format standard PropHunter (sortie de scrape_details)

    Returns:
        list[dict]: annonces dédupliquées, prêtes pour save_properties()
    """
    if not data:
        return []

    now_iso    = datetime.now(timezone.utc).isoformat()
    seen: set  = set()
    unique     = []
    duplicates = 0

    for record in data:
        listing = record.get("listing", {})

        # Garantir id_universel
        id_universel = listing.get("id_universel")
        if not id_universel:
            id_source = listing.get("id_source") or listing.get("url_source", "").rstrip("/").split("/")[-1]
            id_universel = f"hit_{id_source}" if id_source else None
            record["listing"]["id_universel"] = id_universel

        if id_universel:
            if id_universel in seen:
                duplicates += 1
                continue
            seen.add(id_universel)

        # Mettre à jour date_scraping et source
        record["listing"]["date_scraping"] = now_iso
        record.setdefault("metadonnees_scraping", {})["source"] = SOURCE_NAME

        unique.append(record)

    logger.info(
        f"[HomeInTunisia] normaliser terminé : {len(unique)} annonces "
        f"({duplicates} doublons supprimés)"
    )
    return unique
