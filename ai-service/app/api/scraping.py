from fastapi import APIRouter, HTTPException
from app.services.scraping_service import ScrapingService

router = APIRouter(prefix="/scraping", tags=["scraping"])

_service = ScrapingService()


@router.post("/tecnocasa")
def scrape_tecnocasa():
    """
    Lance le pipeline de scraping Tecnocasa complet :
      1. Collecte des liens
      2. Scraping des pages de détail
      3. Normalisation au format standard PropHunter
      4. Enregistrement dans MongoDB (prophunter_ia > tecnocasa_properties)

    Retourne une confirmation JSON avec le nombre d'annonces enregistrées.
    """
    try:
        result = _service.run_tecnocasa()
        return result
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
