"""Contract tests verifying that scan responses strictly adhere to typed Pydantic models."""
import json
import unittest
from pathlib import Path
from pydantic import ValidationError

from main import app
from schemas.scan import (
    ScanResponse,
    ExpiryPredictionResponse,
    FoodItemDetail,
)

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"


class TestScanContracts(unittest.TestCase):
    def test_openapi_snapshot_is_valid_and_matches_live_schema(self):
        self.assertTrue(CONTRACT_PATH.exists(), "contracts/openapi.json snapshot must exist")
        snapshot = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        live = app.openapi()

        self.assertEqual(list(snapshot["paths"].keys()), list(live["paths"].keys()))
        self.assertIn("/scan/", snapshot["paths"])
        self.assertIn("/scan/multi", snapshot["paths"])
        self.assertIn("/scan/predict-expiry", snapshot["paths"])

    def test_food_scan_response_serialization(self):
        payload = {
            "type": "food",
            "requested_type": "food",
            "confidence": 0.95,
            "items": ["apple", "banana"],
            "item_details": [
                {"name": "apple", "confidence": 0.95, "label": "Honeycrisp Apple", "category": "Produce"},
                {"name": "banana", "confidence": 0.90, "label": "Yellow Banana", "category": "Produce"},
            ],
        }
        validated = ScanResponse.model_validate(payload)
        self.assertEqual(validated.type, "food")
        self.assertEqual(len(validated.items), 2)
        self.assertEqual(validated.item_details[0].name, "apple")

    def test_receipt_scan_response_serialization(self):
        payload = {
            "type": "receipt",
            "requested_type": "receipt",
            "confidence": 0.92,
            "items": ["milk", "bread"],
            "item_details": [
                {"name": "milk", "quantity": 1, "unit": "bottle", "confidence": 0.94, "price": 3.99},
                {"name": "bread", "quantity": 1, "unit": "loaf", "confidence": 0.90, "price": 2.49},
            ],
            "text_preview": "STORE RECEIPT TOTAL $6.48",
            "expiry_dates": [],
            "needs_user_input": False,
        }
        validated = ScanResponse.model_validate(payload)
        self.assertEqual(validated.type, "receipt")
        self.assertEqual(len(validated.items), 2)
        self.assertEqual(validated.item_details[0].price, 3.99)

    def test_tag_scan_response_serialization(self):
        payload = {
            "type": "tag",
            "requested_type": "tag",
            "confidence": 0.88,
            "items": ["yogurt"],
            "item_details": [
                {"name": "yogurt", "confidence": 0.88, "quantity": 1, "unit": "tub"},
            ],
            "text_preview": "BEST BEFORE 2026-11-15",
            "expiry_dates": ["2026-11-15"],
            "needs_user_input": False,
            "prompt": None,
        }
        validated = ScanResponse.model_validate(payload)
        self.assertEqual(validated.type, "tag")
        self.assertEqual(validated.expiry_dates, ["2026-11-15"])

    def test_mismatch_and_unknown_scan_responses(self):
        mismatch_payload = {
            "type": "mismatch",
            "requested_type": "food",
            "detected_type": "receipt",
            "confidence": 0.85,
            "items": ["milk"],
            "message": "Image looks like 'receipt', not 'food'.",
            "text_preview": "RECEIPT PREVIEW",
        }
        validated_mismatch = ScanResponse.model_validate(mismatch_payload)
        self.assertEqual(validated_mismatch.type, "mismatch")
        self.assertEqual(validated_mismatch.detected_type, "receipt")

        unknown_payload = {
            "type": "unknown",
            "requested_type": "food",
            "confidence": 0.0,
            "items": [],
            "message": "No food item matched.",
        }
        validated_unknown = ScanResponse.model_validate(unknown_payload)
        self.assertEqual(validated_unknown.type, "unknown")
        self.assertEqual(len(validated_unknown.items), 0)

    def test_malformed_response_fails_validation(self):
        # Confidence out of bounds
        with self.assertRaises(ValidationError):
            ScanResponse.model_validate({
                "type": "food",
                "confidence": 1.5,
                "items": ["milk"],
            })

        # Negative confidence
        with self.assertRaises(ValidationError):
            ScanResponse.model_validate({
                "type": "food",
                "confidence": -0.1,
                "items": ["milk"],
            })

    def test_expiry_prediction_response_validation(self):
        prediction = ExpiryPredictionResponse.model_validate({
            "name": "strawberries",
            "purchase_date": "2026-10-15",
            "predicted_expiry_date": "2026-10-22",
        })
        self.assertEqual(prediction.name, "strawberries")
        self.assertEqual(str(prediction.purchase_date), "2026-10-15")


if __name__ == "__main__":
    unittest.main()
