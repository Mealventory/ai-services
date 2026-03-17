from fastapi import FastAPI
from api.scan import router as scan_router

app = FastAPI(
    title="Mealventory AI Service",
    description="AI microservice for OCR and produce classification"
)

app.include_router(scan_router, prefix="/scan", tags=["Scan"])


@app.get("/")
def health_check():
    return {"status": "AI service running"}