from fastapi import HTTPException, status
from jose import JWTError
from pymongo.errors import DuplicateKeyError

from app.models.user import UserDocument
from app.repositories import user_repository, refresh_token_repository
from app.schemas.auth import (
    SignupRequest, UserResponse,
    SigninRequest, TokenResponse,
    RefreshRequest, RefreshResponse,
)
from app.security.password import hash_password, verify_password
from app.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)

# ─── Message générique d'authentification ─────────────────────────────────────
# Ne jamais révéler si c'est l'email ou le password qui est incorrect.
_AUTH_ERROR = "Email ou mot de passe incorrect."


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNUP
# ═══════════════════════════════════════════════════════════════════════════════

def signup(request: SignupRequest) -> UserResponse:
    """
    Crée un nouvel utilisateur avec rôle USER.
    Le rôle est imposé côté serveur — jamais fourni par le client.
    """
    email = request.email.lower().strip()

    if user_repository.find_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un compte existe déjà avec l'adresse : {email}",
        )

    password_hash = hash_password(request.password)
    doc           = UserDocument.create(email=email, password_hash=password_hash)

    try:
        inserted_id = user_repository.insert_user(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un compte existe déjà avec l'adresse : {email}",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la création du compte.",
        )

    doc["_id"] = inserted_id
    return UserResponse(**UserDocument.to_response(doc))


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNIN
# ═══════════════════════════════════════════════════════════════════════════════

def signin(request: SigninRequest) -> TokenResponse:
    """
    Authentifie un utilisateur et retourne access_token + refresh_token.

    Étapes :
      1. Chercher l'utilisateur par email.
      2. Vérifier le password avec bcrypt.
      3. Générer l'Access Token (sub, email, role, type=access, exp).
      4. Générer le Refresh Token (sub, type=refresh, exp).
      5. Stocker le Refresh Token en base (révocable).
      6. Retourner les tokens — jamais le password_hash.

    Sécurité :
      - Même message d'erreur si email inexistant ou password incorrect
        (évite l'énumération de comptes).
      - Le rôle provient de MongoDB — jamais du client.
    """
    email = request.email.lower().strip()
    user  = user_repository.find_by_email(email)

    # Vérification email + password avec message générique
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_AUTH_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user["_id"])
    role    = user["role"]   # rôle lu depuis MongoDB — jamais fourni par le client

    # Génération des tokens
    access_token, expires_in = create_access_token(
        user_id=user_id,
        email=email,
        role=role,
    )
    refresh_token, expires_at = create_refresh_token(user_id=user_id)

    # Persistance du refresh token (pour révocation)
    try:
        refresh_token_repository.insert(
            token=refresh_token,
            user_id=user_id,
            expires_at=expires_at,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la génération du token.",
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REFRESH avec rotation
# ═══════════════════════════════════════════════════════════════════════════════

def refresh(request: RefreshRequest) -> RefreshResponse:
    """
    Échange un Refresh Token valide contre un nouvel Access Token
    + un nouveau Refresh Token (rotation).

    Étapes :
      1. Décoder + valider la signature JWT du refresh token.
      2. Vérifier que type == "refresh" (un access token est refusé).
      3. Vérifier que le token existe en base et n'est pas révoqué.
      4. Révoquer l'ancien token (rotation).
      5. Relire l'utilisateur depuis MongoDB (rôle à jour).
      6. Générer un nouvel Access Token + un nouveau Refresh Token.
      7. Stocker le nouveau Refresh Token.
      8. Retourner les nouveaux tokens.

    Rotation :
      L'ancien Refresh Token est révoqué dès son utilisation.
      Une tentative de réutilisation de l'ancien token sera refusée
      à l'étape 3 (is_revoked=True).
    """
    _token_invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token invalide ou expiré.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1 + 2 — Décodage JWT + vérification type="refresh"
    try:
        payload = decode_refresh_token(request.refresh_token)
    except JWTError:
        raise _token_invalid

    user_id = payload.get("sub")
    if not user_id:
        raise _token_invalid

    # 3 — Vérification en base (non révoqué, non expiré)
    stored = refresh_token_repository.find_valid(request.refresh_token)
    if not stored:
        raise _token_invalid

    # 4 — Révocation de l'ancien token (rotation)
    refresh_token_repository.revoke(request.refresh_token)

    # 5 — Relecture de l'utilisateur (rôle à jour)
    user = user_repository.find_by_id(user_id)
    if not user:
        raise _token_invalid

    # 6 — Génération des nouveaux tokens
    new_access_token, expires_in = create_access_token(
        user_id=user_id,
        email=user["email"],
        role=user["role"],
    )
    new_refresh_token, new_expires_at = create_refresh_token(user_id=user_id)

    # 7 — Persistance du nouveau Refresh Token
    try:
        refresh_token_repository.insert(
            token=new_refresh_token,
            user_id=user_id,
            expires_at=new_expires_at,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors du renouvellement du token.",
        )

    return RefreshResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )
