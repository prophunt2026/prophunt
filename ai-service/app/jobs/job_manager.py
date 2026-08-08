import threading
from app.jobs import job_repository
from app.jobs.models import JobStatus, ScrapingJob


class JobManager:
    """
    Frontière de migration entre le transport (threading / Celery)
    et la logique métier (ScrapingService).

    Règle : ce fichier est le SEUL endroit qui sait comment lancer
    une tâche en arrière-plan. Remplacer threading par Celery =
    modifier uniquement la méthode _launch().
    """

    def __init__(self, scraping_service):
        # Injection de dépendance — évite l'import circulaire
        self._service = scraping_service

    # ─── Public ──────────────────────────────────────────────────────────────

    def submit(self, source: str) -> tuple[ScrapingJob, bool]:
        """
        Soumet un job de scraping pour la source donnée.

        Returns:
            (job, False)  si le job a été créé et lancé
            (job, True)   si un job est déjà en cours (caller retourne 409)
        """
        running, existing_id = job_repository.is_running(source)
        if running:
            existing = job_repository.get_job(existing_id)
            # Reconstituer un objet minimal pour la réponse 409
            job = ScrapingJob(
                job_id=existing_id,
                source=source,
                status=JobStatus(existing.get("status", "running")),
            )
            return job, True

        job = job_repository.create_job(source)
        self._launch(job.job_id, source)
        return job, False

    # ─── Private ─────────────────────────────────────────────────────────────

    def _launch(self, job_id: str, source: str) -> None:
        """
        Lance le scraping en arrière-plan.

        ── AUJOURD'HUI : threading.Thread ──
        Pour migrer vers Celery, remplacer le contenu de cette méthode par :
            celery_app.send_task("tasks.run_scraping", args=[job_id, source])

        ── DEMAIN : Celery ──
        """
        thread = threading.Thread(
            target=self._service.run,
            args=(job_id, source),
            daemon=True,   # s'arrête si uvicorn s'arrête
            name=f"scraping-{source}-{job_id[:8]}",
        )
        thread.start()
        print(f"[JobManager] Thread lancé : {thread.name}")
