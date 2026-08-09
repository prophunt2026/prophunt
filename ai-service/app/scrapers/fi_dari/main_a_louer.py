import asyncio
from app.scrapers.fi_dari import fidari_common

URL_CIBLE = "https://fi-dari.tn/fr/immobilier/a-louer"
CATEGORY = "location"

async def main():
    print("Démarrage : Scraping LOCATION")
    await fidari_common.scrape_category_with_playwright(URL_CIBLE, CATEGORY)
    print("Scraping LOCATION terminé.")

if __name__ == "__main__":
    asyncio.run(main())