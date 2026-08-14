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

            # ── 1. Sauvegarde dans la collection dédiée IA ───────────────────
            print(f"[ScrapingService:{source}] Étape 1 : Sauvegarde dans '{collection_name}' (prophunter_ia)")
            job_repository.update_job(job_id, step="save_to_ia_collection")
            save_result = save_properties(data, collection_name)

            # ── 2. Synchronisation automatique vers CRUD (prophunter.properties) ──
            print(f"[ScrapingService:{source}] Étape 2 : Synchronisation vers prophunter.properties")
            job_repository.update_job(job_id, step="sync_site_to_crud")
            from app.services.sync_service import sync_site_to_crud
            sync_result = sync_site_to_crud(source)

            # ── 3. Succès ───────────────────────────────────────────────────────
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
                    "synced_crud": sync_result.get("synced", 0),
                    "last_sync_date": sync_result.get("last_sync_date"),
                    "collection": collection_name,
                },
            )
            print(
                f"[ScrapingService:{source}] Pipeline complet réussi — "
                f"scraped={len(data) if data else 0} | "
                f"inserted_ia={save_result['inserted']} | "
                f"synced_crud={sync_result.get('synced', 0)}"
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
