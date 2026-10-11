"""Readiness contract tests; no Google calls or model downloads are made."""
import importlib.util
import json
import sys
import types
import unittest
from unittest.mock import patch
from fastapi import APIRouter


class ReadinessTests(unittest.TestCase):
    def load_main(self, configured, model_loaded=True):
        router = APIRouter()
        classifier = types.SimpleNamespace(model=object() if model_loaded else None)
        modules = {
            "api.scan": types.SimpleNamespace(router=router),
            "services.ocr_service": types.SimpleNamespace(
                vision_credentials_configured=lambda: configured
            ),
            "models.produce_classifier": classifier,
            "models": types.SimpleNamespace(produce_classifier=classifier),
        }
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("readiness_main", "main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    def test_ready_when_model_and_vision_configuration_are_available(self):
        module = self.load_main(True)
        result = module.readiness_check()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["checks"], {"model": "ready", "vision": "configured"})

    def test_liveness_does_not_check_vision(self):
        module = self.load_main(False)
        self.assertEqual(module.health_check(), {"status": "AI service running"})

    def test_degraded_when_vision_configuration_is_missing(self):
        module = self.load_main(False)
        result = module.readiness_check()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(json.loads(result.body), {
            "status": "degraded",
            "checks": {"model": "ready", "vision": "unconfigured"},
        })

    def test_unavailable_when_model_and_vision_are_missing(self):
        module = self.load_main(False, model_loaded=False)
        result = module.readiness_check()
        self.assertEqual(result.status_code, 503)
        self.assertIn(b'"status":"unavailable"', result.body)


if __name__ == "__main__":
    unittest.main()
