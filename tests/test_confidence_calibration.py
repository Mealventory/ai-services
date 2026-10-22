"""Tests for confidence calibration and uncertainty representation (#19)."""
import unittest
from utils.confidence_scoring import (
    calibrate_confidence,
    evaluate_detection,
    RecognitionSource,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_REVIEW_THRESHOLD,
    CONFIDENCE_REJECT_THRESHOLD,
)


class TestConfidenceCalibration(unittest.TestCase):
    def test_high_confidence_clean_acceptance(self):
        result = evaluate_detection("apple", 0.95, RecognitionSource.VISION_LABEL)
        self.assertEqual(result["name"], "apple")
        self.assertEqual(result["confidence"], 0.95)
        self.assertFalse(result["needs_review"])
        self.assertTrue(result["is_accepted"])

    def test_review_confidence_triggers_needs_review(self):
        result = evaluate_detection("banana", 0.72, RecognitionSource.VISION_LABEL)
        self.assertEqual(result["confidence"], 0.72)
        self.assertTrue(result["needs_review"])
        self.assertTrue(result["is_accepted"])

    def test_low_confidence_rejected(self):
        result = evaluate_detection("mystery", 0.42, RecognitionSource.VISION_LABEL)
        self.assertEqual(result["confidence"], 0.42)
        self.assertTrue(result["needs_review"])
        self.assertFalse(result["is_accepted"])

    def test_classification_runner_up_margin_penalty(self):
        # Ambiguous classification: top prediction 0.85, runner-up 0.80 (margin 0.05 < 0.20)
        # penalty: 0.20 - 0.05 = 0.15 => 0.85 - 0.15 = 0.70
        calibrated = calibrate_confidence(
            0.85,
            source=RecognitionSource.CLASSIFICATION,
            runner_up_confidence=0.80,
        )
        self.assertEqual(calibrated, 0.70)
        
        # When evaluated, this penalized score falls into review range
        eval_res = evaluate_detection(
            "orange",
            0.85,
            source=RecognitionSource.CLASSIFICATION,
            runner_up_confidence=0.80,
        )
        self.assertTrue(eval_res["needs_review"])
        self.assertTrue(eval_res["is_accepted"])

    def test_classification_wide_margin_no_penalty(self):
        # Clear classification: top 0.92, runner-up 0.50 (margin 0.42 >= 0.20)
        calibrated = calibrate_confidence(
            0.92,
            source=RecognitionSource.CLASSIFICATION,
            runner_up_confidence=0.50,
        )
        self.assertEqual(calibrated, 0.92)

    def test_ocr_alias_confidence_capped(self):
        # OCR alias shouldn't exceed 0.85
        calibrated = calibrate_confidence(0.99, source=RecognitionSource.OCR_ALIAS)
        self.assertEqual(calibrated, 0.85)

    def test_ocr_partial_confidence_capped_at_review(self):
        # Partial match capped at 0.65
        calibrated = calibrate_confidence(0.90, source=RecognitionSource.OCR_PARTIAL)
        self.assertEqual(calibrated, 0.65)


if __name__ == "__main__":
    unittest.main()
