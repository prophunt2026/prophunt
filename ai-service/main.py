from contextlib import asynccontextmanager

# pyrefly: ignore [missing-import]
from fastapi import FastAPI

from app.api.scraping import router as scraping_router
from app.jobs import job_repository
from app.jobs.models import JobStatus


def _cleanup_orphan_jobs() -> None:
    """
    Au démarrage, marque comme FAILED tous les jobs PENDING ou RUNNING
    qui sont en réalité orphelins (le processus qui les exécutait est mort).

    Appelé automatiquement à chaque démarrage/rechargement d'uvicorn.
    """
    try:
        col = job_repository._col()
        result = col.update_many(
            {"status": {"$in": [JobStatus.PENDING.value, JobStatus.RUNNING.value]}},
            {"$set": {
                "status": JobStatus.FAILED.value,
                "error":  "Job interrompu — le serveur a redémarré avant la fin du scraping.",
            }},
        )
        if result.modified_count > 0:
            print(
                f"[Startup] {result.modified_count} job(s) orphelin(s) marqué(s) FAILED "
                f"(interrompus par un redémarrage précédent)."
            )
        else:
            print("[Startup] Aucun job orphelin détecté.")
    except Exception as e:
        # Ne pas bloquer le démarrage si MongoDB est indisponible
        print(f"[Startup] Impossible de nettoyer les jobs orphelins : {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Au démarrage ──────────────────────────────────────────────────────────
    _cleanup_orphan_jobs()
    try:
        from app.database.property_repository import ensure_all_indexes
        ensure_all_indexes()
    except Exception as e:
        print(f"[Startup] Erreur lors de l'initialisation des index : {e}")
    yield
    # ── À l'arrêt (optionnel) ─────────────────────────────────────────────────



app = FastAPI(
    title="PropHunter TN - AI Service",
    description="AI microservice for PropHunter TN",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(scraping_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai-service"}
