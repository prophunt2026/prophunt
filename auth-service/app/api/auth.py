from fastapi import APIRouter, status

from app.schemas.auth import (
    SignupRequest, UserResponse,
    SigninRequest, TokenResponse,
    RefreshRequest, RefreshResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte utilisateur",
    description=(
        "Crée un nouvel utilisateur avec le rôle USER.\n\n"
        "Le rôle ne peut pas être choisi par le client.\n\n"
        "**Règles mot de passe :** 8–64 caractères, "
        "au moins 1 majuscule, 1 minuscule, 1 chiffre, 1 caractère spécial."
    ),
)
def signup(request: SignupRequest) -> UserResponse:
    return auth_service.signup(request)


@router.post(
    "/signin",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authentifier un utilisateur",
    description=(
        "Vérifie les identifiants et retourne un Access Token + un Refresh Token.\n\n"
        "Le rôle est lu depuis MongoDB — le client ne peut pas choisir ADMIN.\n\n"
        "En cas d'échec, le message d'erreur est intentionnellement générique "
        "(ne révèle pas si c'est l'email ou le mot de passe qui est incorrect)."
    ),
)
def signin(request: SigninRequest) -> TokenResponse:
    return auth_service.signin(request)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Renouveler l'Access Token",
    description=(
        "Échange un Refresh Token valide contre un nouvel Access Token "
        "et un nouveau Refresh Token (rotation).\n\n"
        "L'ancien Refresh Token est révoqué immédiatement après utilisation.\n\n"
        "Un Access Token présenté ici sera refusé (type vérifié)."
    ),
)
def refresh(request: RefreshRequest) -> RefreshResponse:
    return auth_service.refresh(request)
