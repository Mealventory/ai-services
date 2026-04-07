import asyncio
from typing import List

from google.cloud import vision

from models.produce_classifier import classify_image
from services.image_preprocessing import preprocess_for_classification

FOOD_KEYWORDS = {
    "banana",
    "apple",
    "orange",
    "lemon",
    "broccoli",
    "pizza",
    "cheeseburger",
    "hotdog",
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
}

FOOD_LABEL_ALIASES = {
    "granny smith": "apple",
    "red delicious": "apple",
    "gala": "apple",
    "fuji": "apple",
    "honeycrisp": "apple",
    "green apple": "apple",
    "bell pepper": "pepper",
    "sweet pepper": "pepper",
    "ground beef": "beef",
    "beef steak": "beef",
    "chicken breast": "chicken",
    "chicken thigh": "chicken",
    "salmon": "fish",
    "tuna": "fish",
}


def _map_alias(label_text: str) -> str | None:
    lowered = label_text.lower()
    for alias, target in FOOD_LABEL_ALIASES.items():
        if alias in lowered:
            return target
    return None


def _normalize_label(label: str) -> str:
    lowered = label.lower().replace("_", " ")
    alias_match = _map_alias(lowered)
    if alias_match:
        return alias_match
    for part in lowered.split(","):
        candidate = part.strip()
        if candidate in FOOD_KEYWORDS:
            return candidate
    tokens = lowered.split()
    for token in tokens:
        if token in FOOD_KEYWORDS:
            return token
    return lowered.strip()


def _detect_food_with_vision_labels(image_bytes: bytes) -> List[dict]:
    """Fallback detector for real-world photos where classifier confidence is low."""
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.label_detection(image=image)
        if response.error.message:
            return []
    except Exception:
        return []

    items: List[dict] = []
    seen: set[str] = set()

    for label in response.label_annotations:
        normalized = _normalize_label(label.description)
        if normalized in FOOD_KEYWORDS and normalized not in seen and float(label.score) >= 0.45:
            seen.add(normalized)
            items.append(
                {
                    "name": normalized,
                    "label": label.description,
                    "confidence": round(float(label.score), 4),
                    "source": "vision_label",
                }
            )

    return items


async def detect_food(image_bytes):
    processed = preprocess_for_classification(image_bytes)
    predictions = await asyncio.to_thread(classify_image, processed)

    items: List[dict] = []
    seen: set[str] = set()

    for _, label, confidence in predictions:
        normalized = _normalize_label(label)
        if normalized in FOOD_KEYWORDS and confidence > 0.2 and normalized not in seen:
            seen.add(normalized)
            items.append(
                {
                    "name": normalized,
                    "label": label,
                    "confidence": round(float(confidence), 4),
                    "source": "classification",
                }
            )

    if items:
        return items

    # Fallback for common user photos when classification model is uncertain.
    fallback_items = await asyncio.to_thread(_detect_food_with_vision_labels, image_bytes)
    return fallback_items
