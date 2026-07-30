import asyncio
import fidari_common

URL_CIBLE = "https://fi-dari.tn/fr/immobilier/a-louer"
CATEGORY = "location"
OUTPUT_FILE = "biens_a_louer.json"

async def main():
    print(f"🚀 Démarrage : Scraping LOCATION vers {OUTPUT_FILE}")
    
    # Redirection de la sortie vers le fichier spécifique
    fidari_common.SINGLE_OUTPUT_FILE = OUTPUT_FILE 
    
    # Appel de la fonction avec les 2 paramètres requis
    await fidari_common.scrape_category_with_playwright(URL_CIBLE, CATEGORY)
    
    print("🏁 Scraping LOCATION terminé.")

if __name__ == "__main__":
    asyncio.run(main())