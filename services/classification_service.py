import asyncio
import re
from typing import List

from google.cloud import vision

from models.produce_classifier import classify_image
from services.image_preprocessing import preprocess_for_classification

FOOD_KEYWORDS = {
    "avocado",
    "ginger",
    "yogurt",
    "yoghurt",
    "banana",
    "apple",
    "orange",
    "mandarin",
    "clementine",
    "tangerine",
    "citrus fruit",
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
    "fig",
    "pomegranate",
    "pineapple",
    "watermelon",
    "pepper",
    "cabbage",
    "artichoke",
}

FOOD_LABEL_ALIASES = {
    "mandarin orange": "mandarin",
    "mandarins": "mandarin",
    "clementines": "clementine",
    "tangerines": "tangerine",
    "citrus": "citrus fruit",
    "ginger root": "ginger",
    "gingerroot": "ginger",
    "figs": "fig",
    "avocados": "avocado",
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
        if re.search(r"\b" + re.escape(alias) + r"\b", lowered):
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


from services.mock_engine import is_mock_vision_active, get_mock_food_items


def _detect_food_with_vision_labels(image_bytes: bytes) -> List[dict]:
    """Fallback detector for real-world photos where classifier confidence is low."""
    if is_mock_vision_active():
        return get_mock_food_items()
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
        if normalized == "orange":
            normalized = "citrus fruit"
        if normalized in FOOD_KEYWORDS and normalized not in seen and float(label.score) >= 0.50:
            seen.add(normalized)
            items.append(
                {
                    "name": normalized,
                    "label": label.description,
                    "confidence": round(float(label.score), 4),
                    "source": "vision_label",
                }
            )

    # Generic and specific labels describe the same fruit, not extra items.
    if any(item['name'] in {'mandarin', 'clementine', 'tangerine'} for item in items):
        items = [item for item in items if item['name'] != 'citrus fruit']
    return items


async def detect_food(image_bytes):
    # ImageNet is a general classifier with incomplete grocery coverage. A weak
    # food guess must never suppress the broader Vision detector.
    vision_items = await asyncio.to_thread(_detect_food_with_vision_labels, image_bytes)
    if vision_items:
        return vision_items

    try:
        processed = preprocess_for_classification(image_bytes)
        predictions = await asyncio.to_thread(classify_image, processed)
    except Exception:
        return []

    if not predictions:
        return []
    ranked = sorted(predictions, key=lambda prediction: float(prediction[2]), reverse=True)
    _, label, confidence = ranked[0]
    runner_up = float(ranked[1][2]) if len(ranked) > 1 else 0.0
    normalized = _normalize_label(label)
    # Conservative fallback: only the overall winner, with a clear margin.
    # These are guardrails, not a calibrated guarantee of recognition accuracy.
    if normalized not in FOOD_KEYWORDS or float(confidence) < 0.80 or float(confidence) - runner_up < 0.30:
        return []
    if normalized == "orange":
        normalized = "citrus fruit"
    return [{
        "name": normalized, "label": label,
        "confidence": round(float(confidence), 4), "source": "classification",
    }]
