"""
Scraper pour fi-dari.tn — site Next.js App Router, rendu JS obligatoire.

Pipeline (convention PropHunter) :
    scrape_links(data=None)  → list[dict]   (URLs brutes par catégorie)
    scrape_details(data)     → list[dict]   (annonces au format standard via Playwright)
    normaliser(data)         → list[dict]   (dédup + validation finale)

3 catégories scrappées :
    - vente    : https://fi-dari.tn/fr/immobilier/a-vendre
    - location : https://fi-dari.tn/fr/immobilier/a-louer
    - neuf     : https://fi-dari.tn/fr/immobilier/neuf (résidences → logements individuels)

Particularité : fidari_common.scrape_category_with_playwright() est async (Playwright).
On le bridge avec asyncio.run() pour rester compatible avec le pipeline synchrone.
"""

import asyncio
import re
from datetime import datetime, timezone

from app.scrapers.common.utils import get_logger
from app.scrapers.fi_dari import fidari_common
from app.scrapers.fi_dari.fidari_mapper import map_to_standard_schema

SOURCE_NAME = "fi_dari"
logger = get_logger(SOURCE_NAME)

# Catégories à scraper — ordre : vente en premier (plus stable), neuf en dernier
CATEGORIES = [
    {"url": "https://fi-dari.tn/fr/immobilier/a-vendre",  "key": "vente"},
    {"url": "https://fi-dari.tn/fr/immobilier/a-louer",   "key": "location"},
    {"url": "https://fi-dari.tn/fr/immobilier/neuf",      "key": "neuf"},
]

# Limite pour les tests — mettre None en production
TEST_LIMIT: int | None = 5


# ─── Helper async → sync ─────────────────────────────────────────────────────

def _run(coro):
    """
    Exécute une coroutine Playwright depuis n'importe quel contexte :
    - thread background (pas d'event loop) → asyncio.run() direct
    - event loop déjà en cours (uvicorn main thread) → thread dédié

    Playwright sur Windows requiert ProactorEventLoop (Python 3.8+, défaut
    sur Windows). On force explicitement la policy pour éviter NotImplementedError
    sur subprocess_exec.
    """
    import concurrent.futures
    import sys

    def _run_in_new_thread():
        # Forcer ProactorEventLoop sur Windows (nécessaire pour Playwright)
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return asyncio.run(coro)

    # Toujours exécuter dans un thread dédié — garanti sans event loop existant
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_in_new_thread)
        return future.result()


# ─── Collecte des URLs (async interne) ───────────────────────────────────────

async def _collect_all_urls() -> list[dict]:
    """
    Parcourt les 3 catégories et retourne une liste de dicts :
        { "url": "https://fi-dari.tn/...", "category_key": "vente" }
    """
    from playwright.async_api import async_playwright

    all_entries = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        for cat in CATEGORIES:
            logger.info(f"[FiDari] Collecte URLs catégorie : {cat['key']} ({cat['url']})")
            try:
                urls = await fidari_common.collect_detail_urls_from_category(
                    page, cat["url"], max_pages=50
                )

                # Pour la rubrique neuf : résidences → logements individuels
                if cat["key"] == "neuf":
                    expanded = []
                    for project_url in urls:
                        unit_urls = await fidari_common.collect_unit_urls_from_project(
                            page, project_url
                        )
                        if unit_urls:
                            expanded.extend(unit_urls)
                        else:
                            expanded.append(project_url)
                    logger.info(
                        f"[FiDari] neuf : {len(urls)} résidences → {len(expanded)} logements"
                    )
                    urls = expanded

                for url in urls:
                    all_entries.append({"url": url, "category_key": cat["key"]})

                logger.info(
                    f"[FiDari] {cat['key']} : {len(urls)} URLs collectées"
                )

            except Exception as e:
                logger.error(f"[FiDari] Erreur collecte {cat['key']} : {e}")

        await browser.close()

    logger.info(f"[FiDari] scrape_links total : {len(all_entries)} URLs")
    return all_entries


# ─── Extraction des fiches détail (async interne) ────────────────────────────

async def _scrape_all_details(entries: list[dict]) -> list[dict]:
    """
    Visite chaque URL avec Playwright et mappe via fidari_mapper.
    Retourne des annonces au format standard PropHunter.
    """
    from playwright.async_api import async_playwright

    results = []
    total = len(entries)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        for idx, entry in enumerate(entries, start=1):
            url          = entry["url"]
            category_key = entry["category_key"]
            logger.info(f"[FiDari] Détail {idx}/{total} ({category_key}) : {url}")

            try:
                raw = await fidari_common.extract_detail_page_data(page, url)
                if raw:
                    standard = map_to_standard_schema(raw, category_key, url)
                    results.append(standard)
                else:
                    logger.warning(f"[FiDari] Fiche vide : {url}")
            except Exception as e:
                logger.error(f"[FiDari] Erreur fiche {url} : {e}")

        await browser.close()

    logger.info(f"[FiDari] scrape_details terminé : {len(results)}/{total} annonces")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# FONCTIONS PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_links(data=None) -> list[dict]:
    """
    ÉTAPE 1 — Collecte toutes les URLs d'annonces fi-dari.tn
    (vente + location + neuf) via Playwright.

    Args:
        data: ignoré (convention pipeline — premier maillon reçoit None)

    Returns:
        list[dict]: [{ "url": "...", "category_key": "vente|location|neuf" }, ...]
    """
    logger.info("[FiDari] scrape_links démarré — collecte des URLs (3 catégories)")
    entries = _run(_collect_all_urls())

    if TEST_LIMIT is not None:
        entries = entries[:TEST_LIMIT]
        logger.info(f"[FiDari] Mode test : limité à {TEST_LIMIT} annonces")

    return entries


def scrape_details(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 2 — Visite chaque fiche de détail via Playwright et mappe
    les données brutes (JSON-LD + RSC + DOM) au format standard PropHunter.

    Args:
        data: liste de dicts { url, category_key } (sortie de scrape_links)

    Returns:
        list[dict]: annonces au format standard PropHunter
    """
    if not data:
        logger.warning("[FiDari] scrape_details : aucune URL reçue")
        return []

    logger.info(f"[FiDari] scrape_details démarré — {len(data)} fiches à visiter")
    results = _run(_scrape_all_details(data))
    return results


def normaliser(data: list[dict]) -> list[dict]:
    """
    ÉTAPE 3 — Déduplication par id_universel + validation finale.

    Les annonces sans id_universel sont conservées (elles seront ignorées
    par property_repository.save_properties qui les comptera dans 'ignored').

    Args:
        data: annonces au format standard PropHunter (sortie de scrape_details)

    Returns:
        list[dict]: annonces dédupliquées, prêtes pour save_properties()
    """
    if not data:
        return []

    # Déduplication par id_universel
    seen: set[str] = set()
    unique: list[dict] = []
    duplicates = 0

    for annonce in data:
        id_u = annonce.get("listing", {}).get("id_universel")
        if id_u:
            if id_u in seen:
                duplicates += 1
                continue
            seen.add(id_u)
        unique.append(annonce)

    # Mise à jour de la date de scraping
    now_iso = datetime.now(timezone.utc).isoformat()
    for annonce in unique:
        annonce["listing"]["date_scraping"] = now_iso
        # S'assurer que la source est bien renseignée
        annonce.setdefault("metadonnees_scraping", {})["source"] = SOURCE_NAME

    logger.info(
        f"[FiDari] normaliser terminé : {len(unique)} annonces "
        f"({duplicates} doublons supprimés)"
    )
    return unique
