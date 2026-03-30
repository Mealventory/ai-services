import asyncio
from typing import List

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


def _normalize_label(label: str) -> str:
    lowered = label.lower().replace("_", " ")
    for part in lowered.split(","):
        candidate = part.strip()
        if candidate in FOOD_KEYWORDS:
            return candidate
    tokens = lowered.split()
    for token in tokens:
        if token in FOOD_KEYWORDS:
            return token
    return lowered.strip()


async def detect_food(image_bytes):
    processed = preprocess_for_classification(image_bytes)
    predictions = await asyncio.to_thread(classify_image, processed)

    items: List[dict] = []
    seen: set[str] = set()

    for _, label, confidence in predictions:
        normalized = _normalize_label(label)
        if normalized in FOOD_KEYWORDS and confidence > 0.35 and normalized not in seen:
            seen.add(normalized)
            items.append(
                {
                    "name": normalized,
                    "label": label,
                    "confidence": round(float(confidence), 4),
                    "source": "classification",
                }
            )

    return items