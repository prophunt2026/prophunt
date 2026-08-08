from app.scrapers.registry import SCRAPERS
from app.database.property_repository import save_properties
from app.jobs import job_repository
from app.jobs.models import JobStatus, ScrapingJob


class ScrapingService:
    """
    Orchestrateur générique du pipeline de scraping.

    Responsabilité unique : exécuter le pipeline déclaré dans le registry
    pour la source demandée, sans connaître le contenu des étapes.

    Le service ne connaît ni Tecnocasa, ni Mubawab, ni threading, ni Celery.
    Il reçoit un job_id + une source, récupère la liste de fonctions dans
    SCRAPERS, les chaîne dans l'ordre et persiste les résultats.

    Convention pipeline :
        data = None
        for step in pipeline:
            data = step(data)   ← résultat de l'étape N → entrée de l'étape N+1
    """

    def run(self, job_id: str, source: str) -> None:
        """
        Exécute le pipeline complet pour la source donnée.
        Met à jour le job MongoDB à chaque étape.
        Marque le job COMPLETED ou FAILED selon le résultat.

        Args:
            job_id: identifiant du job MongoDB (scraping_jobs._id)
            source: clé du scraper dans le registry (ex: "tecnocasa")
        """
        config = SCRAPERS.get(source)

        if not config:
            job_repository.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=f"Source inconnue ou non encore implémentée : '{source}'. "
                      f"Sources disponibles : {list(SCRAPERS.keys())}",
                finished_at=ScrapingJob.now(),
            )
            return

        pipeline:        list = config["pipeline"]
        collection_name: str  = config["collection"]

        try:
            # ── Démarrage ────────────────────────────────────────────────────
            job_repository.update_job(
                job_id,
                status=JobStatus.RUNNING,
                started_at=ScrapingJob.now(),
            )

            # ── Chaînage des étapes ───────────────────────────────────────────
            data = None
            for step in pipeline:
                step_name = step.__name__
                print(f"[ScrapingService:{source}] Étape : {step_name}")
                job_repository.update_job(job_id, step=step_name)
                data = step(data)

            # ── Sauvegarde ───────────────────────────────────────────────────
            print(f"[ScrapingService:{source}] Sauvegarde dans '{collection_name}'")
            job_repository.update_job(job_id, step="save_properties")
            save_result = save_properties(data, collection_name)

            # ── Succès ───────────────────────────────────────────────────────
            job_repository.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                step="done",
                finished_at=ScrapingJob.now(),
                result={
                    "scraped":   len(data) if data else 0,
                    "inserted":  save_result["inserted"],
                    "updated":   save_result["updated"],
                    "ignored":   save_result["ignored"],
                    "collection": collection_name,
                },
            )
            print(
                f"[ScrapingService:{source}] Terminé — "
                f"scraped={len(data) if data else 0} "
                f"inserted={save_result['inserted']} "
                f"updated={save_result['updated']}"
            )

        except Exception as e:
            # ── Échec ─────────────────────────────────────────────────────────
            print(f"[ScrapingService:{source}] ERREUR : {e}")
            job_repository.update_job(
                job_id,
                status=JobStatus.FAILED,
                finished_at=ScrapingJob.now(),
                error=str(e),
            )
