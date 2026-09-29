"""Offline route tests: no credentials, model downloads or paid Vision requests."""
import asyncio
import importlib.util
import io
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.food = AsyncMock(return_value=[])
        self.ocr = AsyncMock(return_value=None)
        mocks = {
            'services.classification_service': types.SimpleNamespace(detect_food=self.food),
            'services.ocr_service': types.SimpleNamespace(detect_text_type=self.ocr),
            'services.expiry_prediction_service': types.SimpleNamespace(get_expiry_date=lambda _: None),
        }
        with patch.dict(sys.modules, mocks):
            spec = importlib.util.spec_from_file_location('scan_under_test', 'api/scan.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
    def scan(self, mode):
        file = UploadFile(io.BytesIO(b'photo'), filename='photo.jpg', headers=Headers({'content-type': 'image/jpeg'}))
        return asyncio.run(self.module.scan_image(mode, file))
    def test_packaging_ocr_fallback(self):
        self.ocr.return_value = {'items': [{'name': 'yogurt', 'confidence': .7}]}
        self.assertEqual(self.scan('food')['items'], ['yogurt'])
    def test_visual_success_does_not_call_ocr(self):
        self.food.return_value = [{'name': 'apple', 'confidence': .9}]
        self.assertEqual(self.scan('food')['items'], ['apple'])
        self.ocr.assert_not_called()
    def test_ocr_outage_is_not_empty_detection(self):
        for mode in ['food', 'receipt', 'tag']:
            self.ocr.return_value = {'error': 'vision_unavailable', 'items': []}
            with self.assertRaises(HTTPException) as error: self.scan(mode)
            self.assertEqual(error.exception.status_code, 503)
    def test_tag_keeps_date_without_inventing_food(self):
        self.ocr.return_value = {'type': 'tag', 'confidence': .8, 'items': [], 'text_preview': 'BEST BEFORE 2027 JA 25', 'expiry_dates': ['2027 JA 25'], 'needs_user_input': True}
        result = self.scan('tag')
        self.assertEqual(result['expiry_dates'], ['2027 JA 25'])
        self.assertEqual(result['items'], [])
