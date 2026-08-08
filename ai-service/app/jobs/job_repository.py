import uuid
from datetime import datetime, timezone
from pymongo.errors import PyMongoError
from app.database.mongodb import get_collection
from app.jobs.models import ScrapingJob, JobStatus

COLLECTION_NAME = "scraping_jobs"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _col():
    return get_collection(COLLECTION_NAME)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Public interface ─────────────────────────────────────────────────────────

def create_job(source: str) -> ScrapingJob:
    """
    Crée un nouveau job PENDING dans MongoDB et le retourne.
    """
    job = ScrapingJob(
        job_id=str(uuid.uuid4()),
        source=source,
        status=JobStatus.PENDING,
    )
    _col().insert_one({"_id": job.job_id, **job.to_dict()})
    return job


def update_job(job_id: str, **kwargs) -> None:
    """
    Met à jour les champs spécifiés d'un job existant.

    Exemple :
        update_job(job_id, status=JobStatus.RUNNING, step="scrape_links")
    """
    # Sérialiser les enums et datetimes
    fields: dict = {}
    for key, value in kwargs.items():
        if isinstance(value, JobStatus):
            fields[key] = value.value
        elif isinstance(value, datetime):
            fields[key] = value.isoformat()
        else:
            fields[key] = value

    try:
        _col().update_one({"_id": job_id}, {"$set": fields})
    except PyMongoError as e:
        print(f"[JobRepository] Erreur update job {job_id}: {e}")


def get_job(job_id: str) -> dict | None:
    """Retourne le document du job ou None s'il n'existe pas."""
    doc = _col().find_one({"_id": job_id}, {"_id": 0})
    return doc


def get_latest_job(source: str) -> dict | None:
    """
    Retourne le job le plus récent pour une source donnée.
    Utilisé par GET /scraping/{source}/status.
    """
    doc = _col().find_one(
        {"source": source},
        {"_id": 0},
        sort=[("started_at", -1)],
    )
    return doc


def is_running(source: str) -> tuple[bool, str | None]:
    """
    Vérifie si un job PENDING ou RUNNING existe pour cette source.

    Returns:
        (True, job_id)  si un job actif existe
        (False, None)   sinon
    """
    doc = _col().find_one(
        {
            "source": source,
            "status": {"$in": [JobStatus.PENDING.value, JobStatus.RUNNING.value]},
        },
        {"_id": 1},
    )
    if doc:
        return True, str(doc["_id"])
    return False, None
