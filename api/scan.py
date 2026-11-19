# api/scan.py
from typing import Annotated, Literal
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from datetime import date

from services.classification_service import detect_food
from services.ocr_service import detect_text_type
from services.expiry_prediction_service import get_expiry_date
from services.image_preprocessing import preprocess_image_for_mode
from schemas.scan import ScanResponse, ExpiryPredictionResponse

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def check_ocr_result(result: dict | None, *, purpose: Literal["product", "text"]) -> dict | None:
    """Apply one provider-error policy to all scan modes.

    None and successful zero-item responses mean recognition completed without
    a match. Provider errors are *not* empty detections. Keep upstream error
    messages out of client responses and leave request ID/status logging to
    the existing HTTP middleware.
    """
    if result and result.get("error"):
        detail = (
            "Product recognition is unavailable. Please try again later."
            if purpose == "product"
            else "Text recognition is unavailable. Please try again later."
        )
        raise HTTPException(status_code=503, detail=detail)
    return result


async def read_scan_upload(file: UploadFile) -> bytes:
    """Read at most the upload limit plus one byte, closing on every outcome.

    UploadFile is commonly backed by a spooled file. Reading without a size
    bound unnecessarily copies an arbitrarily large upload into process memory.
    A single extra byte is enough to detect and reject oversized uploads.
    """
    try:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Unsupported image type. Use one of: image/jpeg, image/png, image/webp",
            )

        content = await file.read(MAX_IMAGE_BYTES + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image is too large. Max size is 8MB")
        return content
    finally:
        await file.close()


@router.post(
    "/",
    response_model=ScanResponse,
    responses={400: {"description": "Invalid request payload"},
               413: {"description": "Image exceeds max size"},
               415: {"description": "Unsupported media type"},
               503: {"description": "Recognition provider unavailable"}}
)
async def scan_image(
    mode: Annotated[Literal["food", "tag", "receipt"], Form(...)],
    file: Annotated[UploadFile, File(...)],
):
    content = await read_scan_upload(file)

    try:
        content = preprocess_image_for_mode(content, mode=mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="Corrupt or undecodable image file. Please provide a valid photo.")

    if mode == "food":
        items = await detect_food(content)
        if not items:
            # Packaging often has readable food names even when visual labels are generic.
            packaging = check_ocr_result(await detect_text_type(content), purpose="product")
            items = packaging.get('items', []) if packaging else []
        if items:
            conf = max(item["confidence"] for item in items)
            needs_rev = any(item.get("needs_review", False) for item in items) or conf < 0.80
            return {
                "type": "food",
                "requested_type": mode,
                "confidence": conf,
                "needs_review": needs_rev,
                "items": [item["name"] for item in items],
                "item_details": items,
            }

        return {
            "type": "unknown",
            "requested_type": mode,
            "confidence": 0.0,
            "needs_review": True,
            "items": [],
            "message": "No food item matched with enough confidence. Try a clearer image.",
        }

    text_result = check_ocr_result(
        await detect_text_type(content, expected_type=mode), purpose="text"
    )
    if not text_result:
        return {
            "type": "unknown",
            "requested_type": mode,
            "confidence": 0.0,
            "needs_review": True,
            "items": [],
            "message": "No readable text detected.",
        }

    if text_result["type"] not in {mode, "unknown"}:
        return {
            "type": "mismatch",
            "requested_type": mode,
            "detected_type": text_result["type"],
            "confidence": text_result["confidence"],
            "needs_review": True,
            "items": [item["name"] for item in text_result.get("items", [])],
            "message": f"Image looks like '{text_result['type']}', not '{mode}'.",
            "text_preview": text_result["text_preview"],
        }

    details = text_result.get("items", [])
    conf = text_result["confidence"]
    needs_rev = any(item.get("needs_review", False) for item in details) or conf < 0.80 or text_result.get("needs_user_input", False)
    return {
        "type": text_result["type"],
        "requested_type": mode,
        "confidence": conf,
        "needs_review": needs_rev,
        "items": [item["name"] for item in details],
        "item_details": details,
        "text_preview": text_result["text_preview"],
        "expiry_dates": text_result.get("expiry_dates", []),
        "needs_user_input": text_result.get("needs_user_input", False),
        "prompt": text_result.get("prompt"),
    }


@router.post("/predict-expiry", response_model=ExpiryPredictionResponse)
async def predict_expiry(
    name: str,
    avg_shelf_life_days: int,
    temperature: float = 20.0,
    humidity: float = 50.0,
    purchase_date: date | None = None
):
    """
    Predict expiry date for a food item.
    """
    purchase_date = purchase_date or date.today()
    food_data = {
        "avg_shelf_life_days": avg_shelf_life_days,
        "temperature": temperature,
        "humidity": humidity,
        "purchase_date": purchase_date.strftime("%Y-%m-%d"),
    }

    predicted_expiry = get_expiry_date(food_data)

    return {
        "name": name,
        "purchase_date": purchase_date,
        "predicted_expiry_date": predicted_expiry
    }


@router.post(
    "/multi",
    response_model=ScanResponse,
    responses={400: {"description": "Invalid request payload"},
               413: {"description": "Image exceeds max size"},
               415: {"description": "Unsupported media type"},
               503: {"description": "Recognition provider unavailable"}}
)
async def scan_multi(
    file: Annotated[UploadFile, File(...)],
):
    content = await read_scan_upload(file)

    try:
        content = preprocess_image_for_mode(content, mode="food")
    except ValueError:
        raise HTTPException(status_code=400, detail="Corrupt or undecodable image file. Please provide a valid photo.")

    items = await detect_food(content)
    if not items:
        packaging = check_ocr_result(await detect_text_type(content), purpose="product")
        items = packaging.get('items', []) if packaging else []

    if items:
        conf = max(item["confidence"] for item in items)
        needs_rev = any(item.get("needs_review", False) for item in items) or conf < 0.80
        return {
            "type": "multi",
            "requested_type": "multi",
            "confidence": conf,
            "needs_review": needs_rev,
            "items": [item["name"] for item in items],
            "item_details": items,
        }

    return {
        "type": "unknown",
        "requested_type": "multi",
        "confidence": 0.0,
        "needs_review": True,
        "items": [],
        "message": "No food items detected.",
    }
