import asyncio
import os
import re

from google.cloud import vision

from config import settings


def _configure_google_credentials():
    """Set GOOGLE_APPLICATION_CREDENTIALS from settings when provided."""
    configured = settings.GOOGLE_APPLICATION_CREDENTIALS
    if configured and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = configured


_configure_google_credentials()
client = vision.ImageAnnotatorClient()

RECEIPT_KEYWORDS = {
    "subtotal",
    "total",
    "tax",
    "change",
    "cash",
    "receipt",
    "transaction",
    "item",
    "qty",
    "price",
    "amount",
    "store",
}

TAG_KEYWORDS = {
    "ingredients",
    "nutrition",
    "calories",
    "serving",
    "servings",
    "protein",
    "fat",
    "carbohydrate",
    "sodium",
    "exp",
    "best before",
    "use by",
    "lot",
    "barcode",
    "net wt",
}

FOOD_TERMS = {
    "apple",
    "banana",
    "orange",
    "lemon",
    "broccoli",
    "carrot",
    "strawberry",
    "tomato",
    "potato",
    "onion",
    "garlic",
    "cucumber",
    "lettuce",
    "egg",
    "milk",
    "bread",
    "rice",
    "chicken",
    "beef",
    "fish",
    "cheese",
    "yogurt",
    "butter",
    "spinach",
    "pepper",
    "mushroom",
    "avocado",
    "pasta",
    "beans",
}


def _keyword_hits(text: str, keywords: set[str]) -> int:
    return sum(1 for token in keywords if token in text)


def _classify_text(full_text: str) -> tuple[str, float]:
    normalized = full_text.lower()
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    line_count = len(lines)

    receipt_hits = _keyword_hits(normalized, RECEIPT_KEYWORDS)
    tag_hits = _keyword_hits(normalized, TAG_KEYWORDS)

    currency_hits = len(re.findall(r"[$€£]\s?\d+[\.,]?\d*", normalized))
    many_numbers = len(re.findall(r"\d", normalized)) >= 20

    receipt_score = receipt_hits + (2 if currency_hits >= 1 else 0) + (2 if line_count >= 8 else 0) + (1 if many_numbers else 0)
    tag_score = tag_hits + (2 if "nutrition" in normalized else 0) + (1 if line_count <= 8 else 0)

    if receipt_score >= tag_score:
        confidence = min(0.98, 0.55 + 0.06 * receipt_score)
        return "receipt", round(confidence, 2)

    confidence = min(0.98, 0.55 + 0.06 * tag_score)
    return "tag", round(confidence, 2)


def _extract_food_items(full_text: str) -> list[dict]:
    tokens = re.findall(r"[a-zA-Z]+", full_text.lower())
    seen: set[str] = set()
    items: list[dict] = []
    for token in tokens:
        if token in FOOD_TERMS and token not in seen:
            seen.add(token)
            items.append(
                {
                    "name": token,
                    "confidence": 0.7,
                    "source": "ocr",
                }
            )
    return items


async def detect_text_type(image_bytes, expected_type: str | None = None):
    image = vision.Image(content=image_bytes)
    try:
        response = await asyncio.to_thread(client.text_detection, image=image)
    except Exception as exc:
        result = {
            "type": "unknown",
            "confidence": 0.0,
            "text_preview": "",
            "items": [],
            "error": f"vision_unavailable: {exc}",
        }
        if expected_type:
            result["expected_type"] = expected_type
        return result
    if response.error.message:
        result = {
            "type": "unknown",
            "confidence": 0.0,
            "text_preview": "",
            "items": [],
            "error": f"vision_error: {response.error.message}",
        }
        if expected_type:
            result["expected_type"] = expected_type
        return result
    texts = response.text_annotations

    if not texts:
        return None

    full_text = texts[0].description
    detected_type, confidence = _classify_text(full_text)
    text_preview = " ".join(full_text.split())[:220]

    result = {
        "type": detected_type,
        "confidence": confidence,
        "text_preview": text_preview,
        "items": _extract_food_items(full_text),
    }

    if expected_type:
        result["expected_type"] = expected_type

    return result