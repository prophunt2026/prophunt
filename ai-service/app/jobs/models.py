from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


@dataclass
class ScrapingJob:
    """
    Représente un job de scraping.
    Stocké dans MongoDB (collection scraping_jobs) et utilisé en mémoire.
    """
    job_id:      str
    source:      str
    status:      JobStatus           = JobStatus.PENDING
    step:        str | None          = None
    started_at:  datetime | None     = None
    finished_at: datetime | None     = None
    result:      dict[str, Any] | None = None
    error:       str | None          = None

    def to_dict(self) -> dict:
        return {
            "job_id":      self.job_id,
            "source":      self.source,
            "status":      self.status.value,
            "step":        self.step,
            "started_at":  self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result":      self.result,
            "error":       self.error,
        }

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
