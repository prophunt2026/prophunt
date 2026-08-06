from fastapi import FastAPI
from app.api.scraping import router as scraping_router

app = FastAPI(
    title="PropHunter TN - AI Service",
    description="AI microservice for PropHunter TN",
    version="1.0.0",
)

app.include_router(scraping_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai-service"}
