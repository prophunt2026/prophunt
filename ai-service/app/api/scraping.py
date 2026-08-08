from fastapi import APIRouter, HTTPException
from app.services.scraping_service import ScrapingService
from app.jobs.job_manager import JobManager
from app.jobs import job_repository
from app.scrapers.registry import SCRAPERS

router = APIRouter(prefix="/scraping", tags=["scraping"])

# ─── Injection de dépendances ─────────────────────────────────────────────────
_service     = ScrapingService()
_job_manager = JobManager(_service)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{source}", status_code=202)
def start_scraping(source: str):
    """
    Lance un scraping en arrière-plan pour la source donnée.

    - Retourne **202 Accepted** immédiatement si le job est créé.
    - Retourne **409 Conflict** si un job est déjà en cours pour cette source.
    - Retourne **404** si la source n'est pas dans le registry.

    Suivre la progression via :  GET /scraping/{source}/status
    """
    if source not in SCRAPERS:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source}' inconnue. "
                   f"Sources disponibles : {list(SCRAPERS.keys())}",
        )

    job, already_running = _job_manager.submit(source)

    if already_running:
        raise HTTPException(
            status_code=409,
            detail=f"Un scraping '{source}' est déjà en cours (job_id: {job.job_id}).",
        )

    return {
        "job_id":  job.job_id,
        "source":  source,
        "status":  job.status.value,
        "message": f"Scraping '{source}' lancé en arrière-plan.",
    }


@router.get("/{source}/status")
def get_scraping_status(source: str):
    """
    Retourne l'état du dernier job de scraping pour la source donnée.

    - **pending**   : job créé, thread pas encore démarré
    - **running**   : scraping en cours (champ `step` indique l'étape actuelle)
    - **completed** : terminé avec succès (champ `result` contient les stats)
    - **failed**    : erreur (champ `error` contient le message)
    """
    if source not in SCRAPERS:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source}' inconnue. "
                   f"Sources disponibles : {list(SCRAPERS.keys())}",
        )

    job = job_repository.get_latest_job(source)

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Aucun job trouvé pour la source '{source}'.",
        )

    return job
