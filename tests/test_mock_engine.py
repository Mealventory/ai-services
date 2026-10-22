"""Unit and integration tests for deterministic mock vision pipeline."""
import asyncio
import io
import os
import time
import unittest
from unittest.mock import patch

from starlette.datastructures import Headers
from fastapi import UploadFile

from config import settings
from api.scan import scan_image, scan_multi
from services.mock_engine import is_mock_vision_active, get_mock_food_items, get_mock_text_result


class TestMockVisionEngine(unittest.TestCase):
    def test_mock_vision_active_flag(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock"}):
            self.assertTrue(is_mock_vision_active())

        with patch.dict(os.environ, {"MOCK_VISION": "true"}):
            self.assertTrue(is_mock_vision_active())

        with patch.dict(os.environ, {"MOCK_VISION": "1"}):
            self.assertTrue(is_mock_vision_active())

        with patch.dict(os.environ, {"MOCK_VISION": "false", "GEMINI_API_KEY": ""}):
            with patch.object(settings, "MOCK_VISION", False):
                with patch.object(settings, "GEMINI_API_KEY", None):
                    self.assertFalse(is_mock_vision_active())

    def test_mock_food_items_structure(self):
        items = get_mock_food_items()
        self.assertEqual(len(items), 5)
        names = [item["name"] for item in items]
        self.assertEqual(names, ["milk", "egg", "bread", "apple", "chicken"])
        for item in items:
            self.assertIn("confidence", item)
            self.assertGreater(item["confidence"], 0.80)
            self.assertIn("quantity", item)
            self.assertIn("unit", item)

    def test_mock_text_result(self):
        receipt = get_mock_text_result("receipt")
        self.assertEqual(receipt["type"], "receipt")
        self.assertEqual(len(receipt["items"]), 5)

        tag = get_mock_text_result("tag")
        self.assertEqual(tag["type"], "tag")
        self.assertIn("2026-10-30", tag["expiry_dates"])

    def test_scan_multi_deterministic_mock_latency_and_payload(self):
        """Acceptance Criteria: When an image is submitted to /scan/multi with GEMINI_API_KEY=mock,

        a valid mock response with 5 realistic food items is returned in < 100ms.
        """
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        file = UploadFile(io.BytesIO(dummy_png), filename="test.png", headers=Headers({"content-type": "image/png"}))

        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock"}):
            start = time.perf_counter()
            response = asyncio.run(scan_multi(file))
            duration_ms = (time.perf_counter() - start) * 1000

            self.assertLess(duration_ms, 100.0, f"Expected < 100ms, took {duration_ms:.2f}ms")
            self.assertEqual(response["type"], "multi")
            self.assertEqual(len(response["items"]), 5)
            self.assertEqual(response["items"], ["milk", "egg", "bread", "apple", "chicken"])
            self.assertGreaterEqual(response["confidence"], 0.88)

    def test_scan_food_mode_with_mock_vision(self):
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        file = UploadFile(io.BytesIO(dummy_jpeg), filename="test.jpg", headers=Headers({"content-type": "image/jpeg"}))

        with patch.dict(os.environ, {"MOCK_VISION": "true"}):
            result = asyncio.run(scan_image("food", file))
            self.assertEqual(result["type"], "food")
            self.assertEqual(len(result["items"]), 5)
            self.assertIn("milk", result["items"])

    def test_scan_receipt_mode_with_mock_vision(self):
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        file = UploadFile(io.BytesIO(dummy_jpeg), filename="receipt.jpg", headers=Headers({"content-type": "image/jpeg"}))

        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock"}):
            result = asyncio.run(scan_image("receipt", file))
            self.assertEqual(result["type"], "receipt")
            self.assertEqual(len(result["items"]), 5)


if __name__ == "__main__":
    unittest.main()
