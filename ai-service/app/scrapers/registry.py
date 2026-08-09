from typing import Callable

from app.scrapers.tecnocasa.tecnocasa_scraper import scrape_links as tc_links
from app.scrapers.tecnocasa.tecnocasa_details import scrape_details as tc_details
from app.scrapers.tecnocasa.normaliser_tecnocasa import normaliser as tc_normaliser

from app.scrapers.mubawab.mubawab_scraper import scrape_links as mb_links
from app.scrapers.mubawab.mubawab_details import scrape_details as mb_details
from app.scrapers.mubawab.mubawab_telephone import scrape_telephones as mb_telephones, retry_telephones as mb_retry_telephones
from app.scrapers.mubawab.normaliser_mubawab import normaliser as mb_normaliser

from app.scrapers.tayara.scraper import (
    scrape_links   as ta_links,
    scrape_details as ta_details,
    normaliser     as ta_normaliser,
)

from app.scrapers.tunisie_annonce.scraper import (
    scrape_links   as tn_links,
    scrape_details as tn_details,
    normaliser     as tn_normaliser,
)

from app.scrapers.fi_dari.scraper import (
    scrape_links   as fd_links,
    scrape_details as fd_details,
    normaliser     as fd_normaliser,
)

from app.scrapers.scraper_Home_in_Tunisia.pipeline import (
    scrape_links   as hit_links,
    scrape_details as hit_details,
    normaliser     as hit_normaliser,
)

# ─── Type alias ──────────────────────────────────────────────────────────────

ScraperConfig = dict[str, list[Callable] | str]

# ─── Registry ────────────────────────────────────────────────────────────────
#
# Pour ajouter un nouveau scraper :
#   1. Créer app/scrapers/<source>/ avec __init__.py
#   2. Exposer scrape_links(data=None), scrape_details(data), normaliser(data)
#   3. Importer ici et ajouter une entrée dans SCRAPERS
#   → Aucune autre modification nécessaire dans le reste du code
#
# Convention pipeline :
#   - Première étape  : func(data=None) → list
#   - Étapes suivantes: func(data: list) → list
#   - Dernière étape  : func(data: list) → list  (données normalisées)
#
# Parallélisme : chaque source tourne dans son propre threading.Thread (daemon).
# Un 409 Conflict est retourné si on tente de relancer une source déjà en cours.

SCRAPERS: dict[str, ScraperConfig] = {
    "tecnocasa": {
        "pipeline": [
            tc_links,       # scrape_links(data=None)   → liste de liens bruts
            tc_details,     # scrape_details(links)     → liste enrichie
            tc_normaliser,  # normaliser(annonces)      → format standard
        ],
        "collection": "tecnocasa_properties",
    },
    "mubawab": {
        "pipeline": [
            mb_links,            # scrape_links(data=None)     → liste d'URLs
            mb_details,          # scrape_details(links)       → liste enrichie (sans tel)
            mb_telephones,       # scrape_telephones(annonces) → 1er passage Selenium
            mb_retry_telephones, # retry_telephones(annonces)  → 2ème passage sur les ratés
            mb_normaliser,       # normaliser(annonces)        → format standard
        ],
        "collection": "mubawab_properties",
    },
    "tayara": {
        "pipeline": [
            ta_links,       # scrape_links(data=None)   → annonces brutes API JSON
            ta_details,     # scrape_details(annonces)  → enrichissement fiche HTML
            ta_normaliser,  # normaliser(annonces)      → format standard
        ],
        "collection": "tayara_properties",
    },
    "tunisie_annonce": {
        "pipeline": [
            tn_links,       # scrape_links(data=None)   → annonces brutes listing HTML
            tn_details,     # scrape_details(annonces)  → enrichissement fiche détail
            tn_normaliser,  # normaliser(annonces)      → format standard
        ],
        "collection": "tunisie_annonce_properties",
    },
    "fi_dari": {
        "pipeline": [
            fd_links,       # scrape_links(data=None)   → URLs vente/location/neuf (Playwright)
            fd_details,     # scrape_details(entries)   → fiches détail (Playwright JSON-LD+RSC)
            fd_normaliser,  # normaliser(annonces)      → dédup + format standard
        ],
        "collection": "fi_dari_properties",
    },
    "home_in_tunisia": {
        "pipeline": [
            hit_links,      # scrape_links(data=None)   → items bruts vente+location (Playwright)
            hit_details,    # scrape_details(items)     → annonces standard (requests)
            hit_normaliser, # normaliser(annonces)      → dédup + id_universel garanti
        ],
        "collection": "home_in_tunisia_properties",
    },
}
