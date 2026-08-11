import re
from pydantic import BaseModel, EmailStr, field_validator


# ─── Règles mot de passe ──────────────────────────────────────────────────────
#
# Longueur  : 8 à 64 caractères
# Contenu   : au moins 1 majuscule, 1 minuscule, 1 chiffre, 1 caractère spécial

_PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])"
    r"(?=.*[A-Z])"
    r"(?=.*\d)"
    r"(?=.*[!@#$%^&*()\-_=+\[\]{};':\",./<>?])"
    r".{8,64}$"
)


# ─── Signup ───────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """
    Corps POST /signup.
    Pas de champ role — impossible de passer ADMIN via signup.
    """
    email:    EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not _PASSWORD_REGEX.match(v):
            raise ValueError(
                "Le mot de passe doit contenir 8 à 64 caractères, "
                "avec au moins 1 majuscule, 1 minuscule, 1 chiffre "
                "et 1 caractère spécial (!@#$%^&*...)."
            )
        return v


class UserResponse(BaseModel):
    """Réponse signup — sans password ni password_hash."""
    id:         str
    email:      str
    role:       str
    created_at: str


# ─── Signin ───────────────────────────────────────────────────────────────────

class SigninRequest(BaseModel):
    """Corps POST /signin."""
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    """
    Réponse signin — contient access_token + refresh_token.
    Ne contient jamais password ni password_hash.
    """
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int   # durée en secondes de l'access token


# ─── Refresh ──────────────────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    """Corps POST /refresh."""
    refresh_token: str


class RefreshResponse(BaseModel):
    """
    Réponse /refresh — nouvel access token + nouveau refresh token (rotation).
    """
    access_token:  str
    refresh_token: str   # nouveau token (rotation)
    token_type:    str = "bearer"
    expires_in:    int
