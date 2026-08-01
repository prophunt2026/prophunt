from config import OUTPUT_PATH
from storage import load_existing_records, clean_existing_records, merge_scrape_into_existing, atomic_save_records
from scraper_location import scrape_all_location


def update_dataset_location(max_properties=None, delay=1.0, headless=True, path=OUTPUT_PATH):
    # 1. Charger la BDD existante (contient déjà les biens en vente scrapés précédemment)
    existing_by_key = load_existing_records(path)
    print(f"Base chargée : {len(existing_by_key)} biens trouvés dans '{path}'.")

    # 2. NETTOYAGE : Purger les biens internationaux, hôtels et commerces existants
    existing_by_key = clean_existing_records(existing_by_key)

    # 3. Lancer le scraping des biens en LOCATION
    freshly_scraped = scrape_all_location(max_properties=max_properties, delay=delay, headless=headless)

    # 4. Fusionner (les clés id_source des locations n'entrent pas en collision
    #    avec celles des ventes) et sauvegarder
    is_full_scrape = max_properties is None
    final_records, stats = merge_scrape_into_existing(
        existing_by_key,
        freshly_scraped,
        is_full_scrape=is_full_scrape
    )

    atomic_save_records(final_records, path)

    print("\n--- Bilan (location) ---")
    print(f"Total nettoyé et conservé en BDD : {len(final_records)}")
    return final_records, stats


if __name__ == "__main__":
    # Conseil : lance d'abord avec max_properties=5 et headless=False pour
    # vérifier visuellement que LISTING_URL_LOCATION affiche bien des locations
    # (voir le commentaire dans config.py), avant un scraping complet.
    update_dataset_location(max_properties=None, delay=1.0, headless=True)
