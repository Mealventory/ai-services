"""Deterministic zero-cost mock vision engine for local testing and CI."""
import os
from config import settings


def is_mock_vision_active() -> bool:
    """Return True if mock vision pipeline is explicitly enabled via config or environment."""
    if getattr(settings, "MOCK_VISION", False):
        return True
    gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(settings, "GEMINI_API_KEY", "")
    if gemini_key == "mock":
        return True
    mock_env = os.getenv("MOCK_VISION", "").strip().lower()
    return mock_env in ("true", "1", "yes")


MOCK_FOOD_ITEMS = [
    {
        "name": "milk",
        "label": "Whole Milk",
        "confidence": 0.98,
        "source": "mock_vision",
        "category": "Dairy",
        "unit": "bottle",
        "quantity": 1,
    },
    {
        "name": "egg",
        "label": "Eggs",
        "confidence": 0.95,
        "source": "mock_vision",
        "category": "Dairy",
        "unit": "carton",
        "quantity": 12,
    },
    {
        "name": "bread",
        "label": "Sourdough Bread",
        "confidence": 0.92,
        "source": "mock_vision",
        "category": "Bakery",
        "unit": "loaf",
        "quantity": 1,
    },
    {
        "name": "apple",
        "label": "Apples",
        "confidence": 0.90,
        "source": "mock_vision",
        "category": "Produce",
        "unit": "pieces",
        "quantity": 4,
    },
    {
        "name": "chicken",
        "label": "Chicken Breast",
        "confidence": 0.88,
        "source": "mock_vision",
        "category": "Meat",
        "unit": "lbs",
        "quantity": 2,
    },
]


def get_mock_food_items() -> list[dict]:
    """Return synthetic high-confidence food items for offline testing."""
    return [dict(item) for item in MOCK_FOOD_ITEMS]


def get_mock_text_result(expected_type: str | None = None) -> dict:
    """Return synthetic OCR and expiry extraction for receipts or tags."""
    if expected_type == "tag":
        return {
            "type": "tag",
            "confidence": 0.94,
            "text_preview": "NUTRITION FACTS\nBEST BEFORE / MEILLEUR AVANT: 2026-10-30\nKEEP REFRIGERATED",
            "items": [
                {
                    "name": "milk",
                    "quantity": 1,
                    "unit": "bottle",
                    "confidence": 0.95,
                    "price": None,
                }
            ],
            "expiry_dates": ["2026-10-30"],
            "needs_user_input": False,
            "prompt": None,
            "expected_type": "tag",
        }

    # Default to receipt mode
    return {
        "type": "receipt",
        "confidence": 0.96,
        "text_preview": "GROCERY STORE\nWHOLE MILK $3.99\nEGGS 12PK $4.49\nSOURDOUGH BREAD $4.99\nAPPLES $5.20\nCHICKEN BREAST $11.50\nTOTAL $30.17",
        "items": [
            {"name": item["name"], "quantity": item["quantity"], "unit": item["unit"], "confidence": item["confidence"], "price": 4.99}
            for item in MOCK_FOOD_ITEMS
        ],
        "expiry_dates": [],
        "needs_user_input": False,
        "prompt": None,
        "expected_type": expected_type or "receipt",
    }
