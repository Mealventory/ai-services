from fastapi import FastAPI
from api.scan import router as scan_router
from api.barcode import router as barcode_router
from api.foodkeeper import router as foodkeeper_router
from fastapi.responses import JSONResponse
from services.ocr_service import vision_credentials_configured
from services.request_logging import request_logging_middleware
from models import produce_classifier

app = FastAPI(
    title="Mealventory AI Service",
    description="AI microservice for OCR and produce classification"
)

app.middleware("http")(request_logging_middleware)

app.include_router(scan_router, prefix="/scan", tags=["Scan"])
app.include_router(barcode_router, prefix="/barcode", tags=["Barcode"])
app.include_router(foodkeeper_router, prefix="/foodkeeper", tags=["FoodKeeper"])


@app.get("/")
def health_check():
    return {"status": "AI service running"}


@app.get("/ready")
def readiness_check():
    """Report local scan dependency readiness without making remote API calls."""
    model_loaded = getattr(produce_classifier, "model", None) is not None
    vision_configured = vision_credentials_configured()
    checks = {
        "model": "ready" if model_loaded else "unavailable",
        "vision": "configured" if vision_configured else "unconfigured",
    }
    ready = model_loaded and vision_configured
    status = "ready" if ready else ("degraded" if model_loaded or vision_configured else "unavailable")
    body = {"status": status, "checks": checks}
    return body if ready else JSONResponse(status_code=503, content=body)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
