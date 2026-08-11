from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_collection

COLLECTION = "users"


def _col():
    return get_collection(COLLECTION)


def ensure_indexes() -> None:
    """
    Crée l'index unique sur email.
    Appelé une seule fois au démarrage du service.
    MongoDB ne recrée pas l'index s'il existe déjà.
    """
    _col().create_index(
        [("email", ASCENDING)],
        unique=True,
        name="email_unique",
    )
    print("[UserRepository] Index unique sur 'email' vérifié.")


def find_by_email(email: str) -> dict | None:
    """Retourne le document user ou None si introuvable."""
    return _col().find_one({"email": email.lower().strip()})


def insert_user(doc: dict) -> str:
    """
    Insère un nouveau document user.

    Returns:
        str: l'_id MongoDB inséré sous forme de string.

    Raises:
        DuplicateKeyError: si l'email existe déjà (géré dans auth_service).
    """
    result = _col().insert_one(doc)
    return str(result.inserted_id)


def find_by_id(user_id: str) -> dict | None:
    """Retourne le document user par son ObjectId string."""
    from bson import ObjectId
    try:
        return _col().find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
