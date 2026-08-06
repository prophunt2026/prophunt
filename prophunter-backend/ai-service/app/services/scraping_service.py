from app.scrapers.tecnocasa.tecnocasa_scraper import scrape_links
from app.scrapers.tecnocasa.tecnocasa_details import scrape_details
from app.scrapers.tecnocasa.normaliser_tecnocasa import normaliser
from app.database.property_repository import save_properties


class ScrapingService:
  

    def run_tecnocasa(self) -> dict:
        """
        Lance le scraping complet Tecnocasa, enregistre les résultats
        dans MongoDB et retourne une confirmation.

        Returns:
            dict: { status, source, saved }
        """
        print("=== [ScrapingService] Étape 1 : collecte des liens ===")
        links = scrape_links()

        print(f"=== [ScrapingService] Étape 2 : scraping des détails ({len(links)} annonces) ===")
        details = scrape_details(links)

        print(f"=== [ScrapingService] Étape 3 : normalisation ({len(details)} annonces) ===")
        normalized = normaliser(details)

        print(f"=== [ScrapingService] Étape 4 : enregistrement MongoDB ({len(normalized)} annonces) ===")
        result = save_properties(normalized)

        print(
            f"=== [ScrapingService] Terminé — "
            f"insérées : {result['inserted']} | "
            f"mises à jour : {result['updated']} | "
            f"ignorées : {result['ignored']} ==="
        )

        return {
            "status": "success",
            "source": "tecnocasa",
            "scraped": len(normalized),
            "inserted": result["inserted"],
            "updated": result["updated"],
            "ignored": result["ignored"],
        }
