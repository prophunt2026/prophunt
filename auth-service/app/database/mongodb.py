import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

# Charge le .env au moment de l'import du module
load_dotenv()

# ─── Client (singleton) ───────────────────────────────────────────────────────

_client: MongoClient | None = None


def _require_env(key: str) -> str:
    """Lit une variable d'environnement et lève une erreur claire si absente."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"[MongoDB] Variable d'environnement manquante : '{key}'. "
            f"Vérifiez le fichier auth-service/.env."
        )
    return value


def get_client() -> MongoClient:
    """
    Retourne le client MongoClient (singleton).
    Les variables d'env sont lues ici (à la première connexion), pas à l'import,
    ce qui permet au service de démarrer même si MongoDB est temporairement
    indisponible et de lever une erreur claire uniquement quand une requête
    DB est réellement effectuée.
    """
    global _client

    if _client is None:
        mongodb_uri   = _require_env("MONGODB_URI")
        database_name = _require_env("MONGODB_DATABASE")
        try:
            _client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            print(f"[MongoDB] Connecté à {mongodb_uri} — database : {database_name}")
        except ConnectionFailure as e:
            _client = None
            raise ConnectionError(
                f"[MongoDB] Impossible de se connecter à {mongodb_uri} : {e}"
            )

    return _client


def get_collection(collection_name: str) -> Collection:
    """
    Retourne une collection MongoDB depuis la database prophunter_auth.

    Args:
        collection_name: nom de la collection (ex: 'users')

    Returns:
        Collection pymongo prête à l'emploi.
    """
    database_name = _require_env("MONGODB_DATABASE")
    client        = get_client()
    return client[database_name][collection_name]
