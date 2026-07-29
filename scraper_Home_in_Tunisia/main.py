from config import OUTPUT_PATH
from storage import load_existing_records, clean_existing_records, merge_scrape_into_existing, atomic_save_records
from scraper import scrape_all

def update_dataset(max_properties=None, delay=1.0, headless=True, path=OUTPUT_PATH):
    # 1. Charger la BDD existante
    existing_by_key = load_existing_records(path)
    print(f"Base chargée : {len(existing_by_key)} biens trouvés dans '{path}'.")

    # 2. NETTOYAGE : Purger les biens internationaux, hôtels et commerces existants
    existing_by_key = clean_existing_records(existing_by_key)

    # 3. Lancer le scraping
    freshly_scraped = scrape_all(max_properties=max_properties, delay=delay, headless=headless)

    # 4. Fusionner et sauvegarder
    is_full_scrape = max_properties is None
    final_records, stats = merge_scrape_into_existing(
        existing_by_key, 
        freshly_scraped, 
        is_full_scrape=is_full_scrape
    )
    
    atomic_save_records(final_records, path)
    
    print("\n--- Bilan ---")
    print(f"Total nettoyé et conservé en BDD : {len(final_records)}")
    return final_records, stats

if __name__ == "__main__":
    update_dataset(max_properties=None, delay=1.0, headless=True)