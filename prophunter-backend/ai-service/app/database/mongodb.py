import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure


load_dotenv()


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"[MongoDB] Variable d'environnement manquante : '{key}'. "
            f"Vérifiez le fichier ai-service/.env."
        )
    return value


MONGODB_URI     = _require_env("MONGODB_URI")
DATABASE_NAME   = _require_env("MONGODB_DATABASE")

# ─── Client (singleton) ───────────────────────────────────────────────────────

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """
    Retourne le client MongoClient (singleton).
    Lève une erreur explicite si la connexion est impossible.
    """
    global _client

    if _client is None:
        try:
            _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            print(f"[MongoDB] Connecté à {MONGODB_URI} — database : {DATABASE_NAME}")
        except ConnectionFailure as e:
            _client = None
            raise ConnectionError(
                f"[MongoDB] Impossible de se connecter à {MONGODB_URI} : {e}"
            )

    return _client


def get_collection(collection_name: str) -> Collection:
    """
    Retourne une collection MongoDB depuis la database configurée dans .env.

    Args:
        collection_name: nom de la collection (ex: 'tecnocasa_properties')

    Returns:
        Collection pymongo prête à l'emploi.
    """
    client = get_client()
    return client[DATABASE_NAME][collection_name]
