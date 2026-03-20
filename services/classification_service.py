from models.produce_classifier import classify_image
from services.image_preprocessing import preprocess_for_classification

FOOD_KEYWORDS = [
    "banana", "apple", "orange", "lemon", "broccoli",
    "pizza", "cheeseburger", "hotdog", "carrot", "strawberry"
]

async def detect_food(image_bytes):
    processed = preprocess_for_classification(image_bytes)
    predictions = classify_image(processed)

    for _, label, confidence in predictions:
        if label.lower() in FOOD_KEYWORDS and confidence > 0.4:
            return {
                "type": "food",
                "label": label,
                "confidence": float(confidence)
            }

    return None