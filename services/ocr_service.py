import asyncio
import os
import re

from google.cloud import vision

from config import settings
from services.expiry_dates import extract_expiry_dates as _extract_expiry_dates


def _configure_google_credentials():
    """Set GOOGLE_APPLICATION_CREDENTIALS from settings when provided."""
    configured = settings.GOOGLE_APPLICATION_CREDENTIALS
    if configured and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = configured


_configure_google_credentials()
client = None


def vision_credentials_configured() -> bool:
    """Return whether an explicit, readable Google credentials file is configured.

    This intentionally does not contact Google or resolve ambient credentials;
    readiness probes must remain local and predictable.
    """
    configured = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    return bool(configured and os.path.isfile(configured) and os.access(configured, os.R_OK))


def _get_client():
    global client
    if client is None:
        client = vision.ImageAnnotatorClient()
    return client

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
    "meilleur avant",
    "melleur avant",
    "use by",
    "lot",
    "barcode",
    "net wt",
    "bb",
    "ma",
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
    "protein",
    "shake",
}

FOOD_ALIASES = {
    "apple": [r"\bapples?\b", r"\bappl\b"],
    "banana": [r"\bbananas?\b", r"\bbnan\b"],
    "orange": [r"\boranges?\b", r"\borg\b"],
    "milk": [r"\bmlk\b", r"\bwhole\s+milk\b", r"\b2%\s+milk\b", r"\blait\b"],
    "bread": [r"\bbread\b", r"\bbrd\b"],
    "rice": [r"\brice\b", r"\brce\b"],
    "chicken": [
        r"\bchicken\b",
        r"\bchk\b",
        r"\bchkn\b",
        r"\bchik\b",
        r"\b(chk|chkn|chik)\b.*\b(bst|breast|bnls|boneless)\b",
        r"\b(bst|breast|bnls|boneless)\b.*\b(chk|chkn|chik)\b",
    ],
    "beef": [r"\bbeef\b", r"\bbf\b", r"\bbff\b", r"\bground\s+beef\b"],
    "fish": [r"\bfish\b", r"\bsalmon\b", r"\btuna\b", r"\btilapia\b"],
    "cheese": [r"\bcheese\b", r"\bchs\b"],
    "yogurt": [r"\byogurt\b", r"\byog\b"],
    "butter": [r"\bbutter\b", r"\bbuttr\b"],
    "egg": [r"\beggs?\b", r"\begg\b"],
    "carrot": [r"\bcarrots?\b", r"\bcarr\b"],
    "potato": [r"\bpotatoes?\b", r"\bpotato\b", r"\bptto\b"],
    "tomato": [r"\btomatoes?\b", r"\btomato\b"],
    "pepper": [r"\bpepper(s)?\b", r"\bpepp\b"],
    "spinach": [r"\bspinach\b", r"\bspnch\b"],
    "protein": [
        r"\bprotein(e)?s?\b",
        r"\bprujeine\b",
        r"\bcore\s*power\b",
    ],
    "shake": [
        r"\bshake(s)?\b",
    ],
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


def _match_food_name(line: str) -> str | None:
    for token in re.findall(r"[a-zA-Z]+", line):
        if token in FOOD_TERMS:
            return token

    for canonical_name, patterns in FOOD_ALIASES.items():
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns):
            return canonical_name

    return None


def _extract_food_items(full_text: str) -> list[dict]:
    normalized_text = full_text.lower()
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    items: list[dict] = []

    for line in lines:
        matched_name = _match_food_name(line)

        if matched_name:
            items.append(
                {
                    "name": matched_name,
                    "confidence": 0.7,
                    "source": "ocr_alias" if matched_name in FOOD_ALIASES else "ocr",
                }
            )

    return items




async def detect_text_type(image_bytes, expected_type: str | None = None):
    image = vision.Image(content=image_bytes)
    try:
        response = await asyncio.to_thread(_get_client().document_text_detection, image=image)
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
    extracted_items = _extract_food_items(full_text)
    expiry_dates = _extract_expiry_dates(full_text)

    if expected_type == "tag" and expiry_dates:
        detected_type = "tag"
        confidence = max(confidence, 0.78)

    result = {
        "type": detected_type,
        "confidence": confidence,
        "text_preview": text_preview,
        "items": extracted_items,
        "expiry_dates": expiry_dates,
        "needs_user_input": expected_type == "tag" and not extracted_items,
        "prompt": (
            "Expiry date detected. Please provide food name and quantity."
            if expected_type == "tag" and expiry_dates and not extracted_items
            else None
        ),
    }

    if expected_type:
        result["expected_type"] = expected_type

    return result
