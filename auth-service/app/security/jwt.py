import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

# ─── Configuration (lue depuis .env, jamais hardcodée) ───────────────────────

def _secret() -> str:
    v = os.getenv("JWT_SECRET_KEY")
    if not v:
        raise EnvironmentError("JWT_SECRET_KEY manquant dans .env")
    return v

def _algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")

def _access_expire_minutes() -> int:
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

def _refresh_expire_days() -> int:
    return int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ─── Création des tokens ──────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str) -> tuple[str, int]:
    """
    Génère un JWT Access Token.

    Payload :
        sub   → user_id (identifiant MongoDB)
        email → email de l'utilisateur
        role  → rôle récupéré depuis MongoDB (jamais fourni par le client)
        type  → "access"
        exp   → expiration

    Returns:
        (token_str, expires_in_seconds)
    """
    expire_minutes = _access_expire_minutes()
    expire         = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload = {
        "sub":   user_id,
        "email": email,
        "role":  role,
        "type":  "access",
        "exp":   expire,
    }
    token = jwt.encode(payload, _secret(), algorithm=_algorithm())
    return token, expire_minutes * 60


def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    """
    Génère un JWT Refresh Token.

    Payload :
        sub   → user_id
        type  → "refresh"   (différent de "access" — vérification obligatoire)
        exp   → expiration (durée longue)

    Note : on ne met PAS role dans le refresh token — le rôle sera relu
    depuis MongoDB au moment du /refresh pour avoir la valeur à jour.

    Returns:
        (token_str, expires_at_datetime)
    """
    expire_days = _refresh_expire_days()
    expires_at  = datetime.now(timezone.utc) + timedelta(days=expire_days)

    payload = {
        "sub":  user_id,
        "type": "refresh",
        "exp":  expires_at,
    }
    token = jwt.encode(payload, _secret(), algorithm=_algorithm())
    return token, expires_at


# ─── Décodage et validation ───────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    """
    Décode et valide un JWT (signature + expiration).

    Returns:
        payload dict

    Raises:
        JWTError si le token est invalide, expiré ou mal signé.
    """
    return jwt.decode(token, _secret(), algorithms=[_algorithm()])


def decode_refresh_token(token: str) -> dict:
    """
    Décode un token et vérifie strictement que type == "refresh".
    Un Access Token présenté ici sera rejeté.

    Returns:
        payload dict

    Raises:
        JWTError si invalide, expiré ou type != "refresh".
    """
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise JWTError("Token type invalide : 'refresh' attendu")
    return payload


def decode_access_token(token: str) -> dict:
    """
    Décode un token et vérifie strictement que type == "access".
    Un Refresh Token présenté ici sera rejeté.

    Returns:
        payload dict

    Raises:
        JWTError si invalide, expiré ou type != "access".
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Token type invalide : 'access' attendu")
    return payload
