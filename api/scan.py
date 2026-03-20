from fastapi import APIRouter, UploadFile, File
from services.classification_service import detect_food
from services.ocr_service import detect_text_type

router = APIRouter()

@router.post("/")
async def scan_image(file: UploadFile = File(...)):
    content = await file.read()

    # Step 1: Try food detection
    food_result = await detect_food(content)
    if food_result:
        return food_result

    # Step 2: Try text detection
    text_result = await detect_text_type(content)
    if text_result:
        return text_result

    return {
        "type": "unknown",
        "confidence": 0.0
    }