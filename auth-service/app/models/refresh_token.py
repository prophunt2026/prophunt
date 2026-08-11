from datetime import datetime, timezone


class RefreshTokenDocument:
    """
    Représente un document refresh_tokens dans MongoDB.

    Approche de stockage choisie : on stocke le token JWT brut.
    Justification :
      - Le token JWT est déjà signé et ne peut pas être forgé sans le secret.
      - Le stockage en base permet la révocation explicite (is_revoked=True).
      - La rotation garantit qu'un token utilisé ne peut pas être réutilisé.
      - Alternative (hash SHA-256) : plus sécurisée mais nécessite un lookup
        exact — on la réserve pour une implémentation OAuth2 complète future.
    """

    @staticmethod
    def create(token: str, user_id: str, expires_at: datetime) -> dict:
        """
        Construit un document refresh_token prêt pour l'insertion MongoDB.
        """
        now = datetime.now(timezone.utc)
        return {
            "token":      token,
            "user_id":    user_id,
            "expires_at": expires_at,
            "is_revoked": False,
            "created_at": now,
        }
