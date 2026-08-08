from typing import Callable
from app.scrapers.tecnocasa.tecnocasa_scraper import scrape_links as tc_links
from app.scrapers.tecnocasa.tecnocasa_details import scrape_details as tc_details
from app.scrapers.tecnocasa.normaliser_tecnocasa import normaliser as tc_normaliser
from app.scrapers.mubawab.mubawab_scraper import scrape_links as mb_links
from app.scrapers.mubawab.mubawab_details import scrape_details as mb_details
from app.scrapers.mubawab.mubawab_telephone import scrape_telephones as mb_telephones, retry_telephones as mb_retry_telephones
from app.scrapers.mubawab.normaliser_mubawab import normaliser as mb_normaliser

# ─── Type alias ──────────────────────────────────────────────────────────────

ScraperConfig = dict[str, list[Callable] | str]

# ─── Registry ────────────────────────────────────────────────────────────────
#
# Pour ajouter un nouveau scraper :
#   1. Créer app/scrapers/<source>/ avec les fonctions du pipeline
#   2. Importer les fonctions ici
#   3. Ajouter une entrée dans SCRAPERS
#   → Aucune autre modification nécessaire dans le reste du code
#
# Convention pipeline :
#   - Première étape  : func(data=None) → list
#   - Étapes suivantes: func(data: list) → list
#   - Dernière étape  : func(data: list) → list  (données normalisées)

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
            mb_links,           # scrape_links(data=None)     → liste d'URLs
            mb_details,         # scrape_details(links)       → liste enrichie (sans tel)
            mb_telephones,      # scrape_telephones(annonces) → 1er passage Selenium
            mb_retry_telephones,# retry_telephones(annonces)  → 2ème passage sur les ratés
            mb_normaliser,      # normaliser(annonces)        → format standard
        ],
        "collection": "mubawab_properties",
    },

    # ── Futures sources ───────────────────────────────────────────────────────
    # "tayara": {
    #     "pipeline": [ta_links, ta_details, ta_normaliser],
    #     "collection": "tayara_properties",
    # },
    # "tunisie_annonce": {
    #     "pipeline": [tn_links, tn_details, tn_normaliser],
    #     "collection": "tunisie_annonce_properties",
    # },
    # "home_in_tunisia": {
    #     "pipeline": [hi_links, hi_details, hi_normaliser],
    #     "collection": "home_in_tunisia_properties",
    # },
    # "fi_dari": {
    #     "pipeline": [fd_links, fd_details, fd_normaliser],
    #     "collection": "fi_dari_properties",
    # },
}
