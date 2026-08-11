from datetime import datetime
from pymongo import ASCENDING, DESCENDING

from app.database.mongodb import get_collection
from app.models.refresh_token import RefreshTokenDocument

COLLECTION = "refresh_tokens"


def _col():
    return get_collection(COLLECTION)


def ensure_indexes() -> None:
    """
    Crée les index nécessaires sur refresh_tokens.
    - Index TTL sur expires_at : MongoDB supprime automatiquement les tokens expirés.
    - Index sur token : lookup rapide lors du /refresh.
    - Index sur user_id : pour révoquer tous les tokens d'un utilisateur.
    """
    # TTL : suppression automatique après expiration (nettoyage gratuit)
    _col().create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="expires_at_ttl",
    )
    # Lookup par token brut
    _col().create_index(
        [("token", ASCENDING)],
        unique=True,
        name="token_unique",
    )
    # Révocation par utilisateur
    _col().create_index(
        [("user_id", ASCENDING)],
        name="user_id_idx",
    )
    print("[RefreshTokenRepository] Index refresh_tokens vérifiés.")


def insert(token: str, user_id: str, expires_at: datetime) -> None:
    """Insère un nouveau Refresh Token en base."""
    doc = RefreshTokenDocument.create(token, user_id, expires_at)
    _col().insert_one(doc)


def find_valid(token: str) -> dict | None:
    """
    Recherche un Refresh Token valide (non révoqué, non expiré).
    L'expiration est aussi gérée côté JWT mais on vérifie en base
    pour détecter les tokens révoqués manuellement.
    """
    now = datetime.utcnow()
    return _col().find_one({
        "token":      token,
        "is_revoked": False,
        "expires_at": {"$gt": now},
    })


def revoke(token: str) -> None:
    """Révoque un Refresh Token (rotation ou logout)."""
    _col().update_one(
        {"token": token},
        {"$set": {"is_revoked": True}},
    )


def revoke_all_for_user(user_id: str) -> None:
    """Révoque tous les Refresh Tokens d'un utilisateur (ex: logout global)."""
    _col().update_many(
        {"user_id": user_id, "is_revoked": False},
        {"$set": {"is_revoked": True}},
    )
