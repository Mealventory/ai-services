import asyncio
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

class ClassificationPolicyTests(unittest.TestCase):
    def setUp(self):
        mocks = {
            'google.cloud': types.SimpleNamespace(vision=types.SimpleNamespace()),
            'models.produce_classifier': types.SimpleNamespace(classify_image=lambda _: []),
            'services.image_preprocessing': types.SimpleNamespace(preprocess_for_classification=lambda _: None),
        }
        with patch.dict(sys.modules, mocks):
            spec = importlib.util.spec_from_file_location('classification_under_test', 'services/classification_service.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.preprocess_for_classification = lambda _: None
    def detect(self, labels, predictions):
        self.module._detect_food_with_vision_labels = lambda _: labels
        self.module.classify_image = lambda _: predictions
        return asyncio.run(self.module.detect_food(b'photo'))
    def test_missing_produce_and_aliases_are_supported(self):
        for label, name in [('Avocado', 'avocado'), ('Ginger root', 'ginger'), ('Figs', 'fig')]:
            self.assertEqual(self.module._normalize_label(label), name)
            self.assertIn(name, self.module.FOOD_KEYWORDS)
    def test_vision_avocado_wins_over_classifier_lemon(self):
        labels = [{'name': 'avocado', 'confidence': .9}]
        self.assertEqual(self.detect(labels, [('id', 'lemon', .25)]), labels)
    def test_weak_lemon_is_not_accepted_without_vision(self):
        self.assertEqual(self.detect([], [('id', 'lemon', .25)]), [])
    def test_food_runner_up_cannot_override_nonfood_winner(self):
        self.assertEqual(self.detect([], [('id', 'table', .85), ('id', 'lemon', .12)]), [])
    def test_strong_classifier_fallback(self):
        self.assertEqual(self.detect([], [('id', 'fig', .9), ('id', 'lemon', .05)])[0]['name'], 'fig')

    def test_specific_citrus_labels_are_preserved(self):
        for label, expected in [('mandarin orange', 'mandarin'), ('Clementines', 'clementine'), ('Tangerines', 'tangerine'), ('Citrus', 'citrus fruit')]:
            self.assertEqual(self.module._normalize_label(label), expected)

    def test_visual_orange_fallback_is_presented_as_citrus(self):
        result = self.detect([], [('id', 'orange', .95), ('id', 'lemon', .02)])
        self.assertEqual(result[0]['name'], 'citrus fruit')
