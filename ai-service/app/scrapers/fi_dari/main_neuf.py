import asyncio
from app.scrapers.fi_dari import fidari_common

URL_CIBLE = "https://fi-dari.tn/fr/immobilier/neuf"
CATEGORY = "neuf"

async def main():
    print("Démarrage : Scraping NEUF")
    await fidari_common.scrape_category_with_playwright(URL_CIBLE, CATEGORY)
    print("Scraping NEUF terminé.")

if __name__ == "__main__":
    asyncio.run(main())