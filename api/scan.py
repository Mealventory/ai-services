from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from services.classification_service import detect_food
from services.ocr_service import detect_text_type

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024

@router.post(
    "/",
    responses={
        400: {"description": "Invalid request payload"},
        413: {"description": "Image exceeds max size"},
        415: {"description": "Unsupported media type"},
    },
)
async def scan_image(
    mode: Annotated[Literal["food", "tag", "receipt"], Form(...)],
    file: Annotated[UploadFile, File(...)],
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Use one of: image/jpeg, image/png, image/webp",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large. Max size is 8MB")

    if mode == "food":
        items = await detect_food(content)
        if items:
            return {
                "type": "food",
                "requested_type": mode,
                "confidence": max(item["confidence"] for item in items),
                "items": [item["name"] for item in items],
                "item_details": items,
            }

        return {
            "type": "unknown",
            "requested_type": mode,
            "confidence": 0.0,
            "items": [],
            "message": "No food item matched with enough confidence. Try a clearer image.",
        }

    text_result = await detect_text_type(content, expected_type=mode)
    if not text_result:
        return {
            "type": "unknown",
            "requested_type": mode,
            "confidence": 0.0,
            "items": [],
            "message": "No readable text detected.",
        }

    if text_result["type"] not in {mode, "unknown"}:
        return {
            "type": "mismatch",
            "requested_type": mode,
            "detected_type": text_result["type"],
            "confidence": text_result["confidence"],
            "items": text_result.get("items", []),
            "message": f"Image looks like '{text_result['type']}', not '{mode}'.",
            "text_preview": text_result["text_preview"],
        }

    if text_result["type"] == "unknown":
        return {
            "type": "unknown",
            "requested_type": mode,
            "confidence": 0.0,
            "items": [],
            "message": "OCR unavailable or no readable text detected.",
            "error": text_result.get("error"),
        }

    return {
        "type": text_result["type"],
        "requested_type": mode,
        "confidence": text_result["confidence"],
        "items": [item["name"] for item in text_result.get("items", [])],
        "item_details": text_result.get("items", []),
        "text_preview": text_result["text_preview"],
    }


@router.post(
    "/detect-food",
    responses={
        400: {"description": "Invalid request payload"},
        415: {"description": "Unsupported media type"},
    },
)
async def detect_food_legacy(file: Annotated[UploadFile, File(...)]):
    """Backward-compatible endpoint expected by backend integrations."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Use one of: image/jpeg, image/png, image/webp",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    items = await detect_food(content)
    return {
        "type": "food" if items else "unknown",
        "items": [item["name"] for item in items],
        "item_details": items,
        "confidence": max((item["confidence"] for item in items), default=0.0),
    }