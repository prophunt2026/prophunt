import asyncio
from fidari_common import scrape_category_with_playwright

if __name__ == "__main__":
    asyncio.run(
        scrape_category_with_playwright(
            target_url="https://fi-dari.tn/fr/immobilier/a-vendre",
            category_key="vente"
        )
    )