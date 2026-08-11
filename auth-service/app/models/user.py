from enum import Enum
from datetime import datetime, timezone


class UserRole(str, Enum):
    USER  = "USER"
    ADMIN = "ADMIN"


class UserDocument:
    """
    Représente un document users dans MongoDB.
    Pas d'ORM — dict pur compatible pymongo.
    """

    @staticmethod
    def create(email: str, password_hash: str) -> dict:
        """
        Construit un nouveau document user prêt pour l'insertion MongoDB.
        Le rôle est toujours USER — jamais fourni par le client.
        """
        now = datetime.now(timezone.utc)
        return {
            "email":         email.lower().strip(),
            "password_hash": password_hash,
            "role":          UserRole.USER.value,
            "created_at":    now,
            "updated_at":    now,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        """
        Convertit un document MongoDB en dict de réponse API.
        Ne retourne jamais password_hash.
        """
        return {
            "id":         str(doc["_id"]),
            "email":      doc["email"],
            "role":       doc["role"],
            "created_at": doc["created_at"].isoformat()
            if isinstance(doc["created_at"], datetime)
            else doc["created_at"],
        }
