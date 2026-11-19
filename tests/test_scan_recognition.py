"""Offline route tests: no credentials, model downloads or paid Vision requests."""
import asyncio
import importlib.util
import io
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from services.request_logging import request_logging_middleware

class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.food = AsyncMock(return_value=[])
        self.ocr = AsyncMock(return_value=None)
        mocks = {
            'services.classification_service': types.SimpleNamespace(detect_food=self.food),
            'services.ocr_service': types.SimpleNamespace(detect_text_type=self.ocr),
            'services.expiry_prediction_service': types.SimpleNamespace(get_expiry_date=lambda _: None),
            'services.image_preprocessing': types.SimpleNamespace(preprocess_image_for_mode=lambda b, **kw: b),
        }
        with patch.dict(sys.modules, mocks):
            spec = importlib.util.spec_from_file_location('scan_under_test', 'api/scan.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
    def scan(self, mode):
        file = UploadFile(io.BytesIO(b'photo'), filename='photo.jpg', headers=Headers({'content-type': 'image/jpeg'}))
        return asyncio.run(self.module.scan_image(mode, file))
    def multi(self):
        file = UploadFile(io.BytesIO(b'photo'), filename='photo.jpg', headers=Headers({'content-type': 'image/jpeg'}))
        return asyncio.run(self.module.scan_multi(file))
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

    def test_fallback_ocr_outage_is_503_in_single_and_multi_modes(self):
        # Even malformed provider responses that contain items alongside
        # an error must not be treated as successful detection.
        self.ocr.return_value = {
            'error': 'vision_unavailable: secret-provider-credentials',
            'items': [{'name': 'untrusted', 'confidence': .99}],
        }
        for route in (lambda: self.scan('food'), self.multi):
            with self.subTest(route=route):
                with self.assertRaises(HTTPException) as error:
                    route()
                self.assertEqual(error.exception.status_code, 503)
                self.assertEqual(
                    error.exception.detail,
                    'Product recognition is unavailable. Please try again later.',
                )
                self.assertNotIn('secret-provider-credentials', error.exception.detail)

    def test_successful_zero_items_remains_unknown_in_both_food_modes(self):
        for ocr in (None, {'type': 'unknown', 'items': []}):
            self.ocr.return_value = ocr
            with self.subTest(ocr=ocr):
                for result in (self.scan('food'), self.multi()):
                    self.assertEqual(result['type'], 'unknown')
                    self.assertEqual(result['items'], [])
                    self.assertTrue(result['needs_review'])

    def test_successful_ocr_fallback_items_preserve_both_response_contracts(self):
        self.ocr.return_value = {
            'type': 'food',
            'items': [{'name': 'yogurt', 'confidence': .87, 'needs_review': False}],
        }
        single = self.scan('food')
        multi = self.multi()
        self.assertEqual(single['type'], 'food')
        self.assertEqual(single['requested_type'], 'food')
        self.assertEqual(multi['type'], 'multi')
        self.assertEqual(multi['requested_type'], 'multi')
        for response in (single, multi):
            self.assertEqual(response['items'], ['yogurt'])
            self.assertEqual(response['item_details'][0]['name'], 'yogurt')
            self.assertEqual(response['confidence'], .87)
            self.assertFalse(response['needs_review'])

    def test_multi_visual_detection_skips_ocr_fallback(self):
        self.food.return_value = [{'name': 'apple', 'confidence': .96}]
        result = self.multi()
        self.assertEqual(result['type'], 'multi')
        self.assertEqual(result['items'], ['apple'])
        self.ocr.assert_not_awaited()

    def test_provider_outage_preserves_correlation_id_without_leaking_error(self):
        app = FastAPI()
        app.middleware('http')(request_logging_middleware)
        app.include_router(self.module.router, prefix='/scan')
        self.ocr.return_value = {
            'error': 'vision_error: upstream-key-private-token',
            'items': [],
        }
        with patch('services.request_logging._LOG.info') as recorded:
            with TestClient(app) as client:
                response = client.post(
                    '/scan/multi',
                    files={'file': ('food.jpg', b'photo', 'image/jpeg')},
                    headers={'X-Request-ID': 'scan-fallback-40'},
                )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['X-Request-ID'], 'scan-fallback-40')
        self.assertNotIn('upstream-key-private-token', response.text)
        event = json.loads(recorded.call_args.args[0])
        self.assertEqual(event['request_id'], 'scan-fallback-40')
        self.assertEqual(event['route'], '/scan/multi')
        self.assertEqual(event['status'], 503)
        self.assertEqual(event['failure_category'], 'service_unavailable')
        self.assertNotIn('upstream-key-private-token', json.dumps(event))
