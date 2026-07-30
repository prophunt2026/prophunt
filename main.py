"""
Point d'entrée : lance les deux scrapers (dossiers tayara/ et
tunisie_annonce/), exporte les résultats dans data/<source>/, et une
fusion globale dans data/annonces_merged.json/.csv.

=====================================================================
ÉTAPES DU SCRAPING (pour présentation / réunion) :
  1. Choix des sites          -> tayara.tn + tunisie-annonce.com
  2. Analyse structure HTML   -> voir docstrings dans tayara/scraper.py
                                  et tunisie_annonce/scraper.py
  3. Schéma de données commun -> common/schema.py (new_listing())
  4. Scripts d'extraction     -> tayara/scraper.py, tunisie_annonce/scraper.py
  5. Gestion erreurs/limites  -> common/utils.py (safe_get, RateLimiter)
  6. Tests avant exécution    -> test_parsers.py
  7. Exécution réelle + export -> ce fichier (main.py)

MISES À JOUR (demande manager) :
  - Objectif : 1000+ annonces par site
      -> Tayara : scrape_api() appelle directement l'API JSON interne du
         site (bien plus rapide/fiable qu'un navigateur simulé — voir la
         docstring de tayara/scraper.py pour le détail de la découverte)
      -> Tunisie-Annonce : scrape(max_pages=40) (pagination classique)
  - Correctif "surface null" :
      -> Tayara : la description complète est incluse dès la page de
         liste (API) -> la superficie en est extraite directement, pas
         besoin de fiche détail séparée
      -> Tunisie-Annonce : enrich_with_details() visite la fiche détail
         de chaque annonce pour récupérer la superficie (absente de la
         page de liste sur ce site)
=====================================================================
"""

from common.utils import export_to_csv, export_to_json, get_logger
from tayara import scraper as tayara_scraper
from tunisie_annonce import scraper as tunisie_annonce_scraper

logger = get_logger("main")

TARGET_PER_SITE = 1000
ENRICH_DETAILS_LIMIT = None  # Tunisie-Annonce uniquement ; None = toutes les annonces


def run_all():
    logger.info("=== Démarrage du scraping PropHunter TN ===")

    # --- ÉTAPE 7a : scraping du site n°1 (Tayara) — via l'API interne ---
    # enrich_details=True : passe 2 qui visite chaque fiche /item/ID/ pour
    # récupérer toutes les photos + le téléphone + les adParams structurés.
    logger.info("--- Tayara (API interne + enrichissement fiches détail, objectif 1000+) ---")
    tayara_data = tayara_scraper.scrape_api(target=TARGET_PER_SITE, enrich_details=True)
    export_to_json(tayara_data, "data/tayara/tayara.json")   # export brut (structure complète)
    export_to_csv(tayara_data, "data/tayara/tayara.csv")     # export aplati (pour Excel)

    # --- ÉTAPE 7b : scraping du site n°2 (Tunisie-Annonce) — pagination classique ---
    logger.info("--- Tunisie-Annonce (40 pages, objectif 1000+) ---")
    ta_data = tunisie_annonce_scraper.scrape(max_pages=40, transaction_code="10102")  # Vente
    logger.info("--- Tunisie-Annonce : enrichissement des fiches détail (superficie...) ---")
    ta_data = tunisie_annonce_scraper.enrich_with_details(ta_data, limit=ENRICH_DETAILS_LIMIT)
    export_to_json(ta_data, "data/tunisie_annonce/tunisie_annonce.json")
    export_to_csv(ta_data, "data/tunisie_annonce/tunisie_annonce.csv")

    # --- ÉTAPE 7c : fusion des deux sources ---
    # Les deux scrapers utilisent le même schéma (common/schema.py), donc
    # on peut simplement additionner les deux listes sans transformation.
    merged = tayara_data + ta_data
    export_to_json(merged, "data/annonces_merged.json")
    export_to_csv(merged, "data/annonces_merged.csv")

    logger.info(
        f"=== Terminé : {len(tayara_data)} (Tayara) + {len(ta_data)} (Tunisie-Annonce) "
        f"= {len(merged)} annonces au total ==="
    )
    return merged


if __name__ == "__main__":
    run_all()