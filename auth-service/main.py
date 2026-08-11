from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

from app.database.mongodb import get_client
from app.repositories.user_repository import ensure_indexes as ensure_user_indexes
from app.repositories.refresh_token_repository import ensure_indexes as ensure_rt_indexes
from app.api.auth import router as auth_router

load_dotenv()


def _startup() -> None:
    """
    Au démarrage :
      1. Vérifie la connexion MongoDB.
      2. Crée l'index unique sur users.email.
      3. Crée les index sur refresh_tokens (TTL + unique token + user_id).
    """
    try:
        get_client()
        ensure_user_indexes()
        ensure_rt_indexes()
    except Exception as e:
        print(f"[Startup] Attention — MongoDB indisponible : {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    yield


app = FastAPI(
    title="PropHunter TN - Auth Service",
    description="Authentication microservice for PropHunter TN",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "auth-service"}
