"""Confidence calibration and uncertainty representation across AI recognition pipelines."""
from enum import Enum
from typing import Any, Dict, Optional


class RecognitionSource(str, Enum):
    CLASSIFICATION = "classification"
    VISION_LABEL = "vision_label"
    OCR_EXACT = "ocr_exact"
    OCR_ALIAS = "ocr_alias"
    OCR_PARTIAL = "ocr_partial"
    MOCK_VISION = "mock_vision"


# Standardized Decision Thresholds
CONFIDENCE_HIGH_THRESHOLD = 0.80      # Cleanly accepted without review prompts
CONFIDENCE_REVIEW_THRESHOLD = 0.65    # Surfaced for review, needs_review = True
CONFIDENCE_REJECT_THRESHOLD = 0.50    # Suppressed / rejected as unknown


def calibrate_confidence(
    raw_confidence: float,
    source: str = RecognitionSource.VISION_LABEL,
    runner_up_confidence: Optional[float] = None,
) -> float:
    """Calibrate raw detection score to a normalized 0.0 - 1.0 confidence score.

    Takes into account model source semantics and margin between top predictions.
    """
    raw = max(0.0, min(1.0, float(raw_confidence)))

    if source == RecognitionSource.CLASSIFICATION:
        # Softmax margin penalty: penalize ambiguous predictions where runner-up is close
        if runner_up_confidence is not None:
            margin = raw - max(0.0, min(1.0, float(runner_up_confidence)))
            if margin < 0.20:
                raw = max(0.0, raw - (0.20 - margin))

    elif source == RecognitionSource.OCR_ALIAS:
        # Alias matches carry slightly more uncertainty than exact full-word hits
        raw = min(raw, 0.85)

    elif source == RecognitionSource.OCR_PARTIAL:
        # Substring or noisy token matches capped at review threshold
        raw = min(raw, 0.65)

    return round(raw, 4)


def evaluate_detection(
    name: str,
    raw_confidence: float,
    source: str = RecognitionSource.VISION_LABEL,
    runner_up_confidence: Optional[float] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Evaluate and enrich a detected item with calibrated confidence and review status."""
    calibrated = calibrate_confidence(raw_confidence, source, runner_up_confidence)
    needs_review = calibrated < CONFIDENCE_HIGH_THRESHOLD
    is_accepted = calibrated >= CONFIDENCE_REJECT_THRESHOLD

    return {
        "name": name,
        "confidence": calibrated,
        "needs_review": needs_review,
        "is_accepted": is_accepted,
        "source": str(source),
        **extra,
    }
