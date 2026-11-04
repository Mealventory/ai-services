"""AI logs use the incoming backend request ID without sensitive payloads."""
import json
import logging
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.request_logging import request_logging_middleware


def _app():
    app = FastAPI()
    app.middleware("http")(request_logging_middleware)

    @app.get("/lookup/{barcode}")
    def lookup(barcode: str):
        return {"ok": True}

    return app


def test_ai_request_id_echoed_and_logged_without_sensitive_data(caplog):
    caplog.set_level(logging.INFO, logger="mealventory.ai.requests")
    with TestClient(_app()) as client:
        response = client.get(
            "/lookup/123456789012?password=private-password",
            headers={"X-Request-ID": "scan-789", "Authorization": "Bearer private-token"},
        )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "scan-789"
    records = [
        json.loads(record.message) for record in caplog.records
        if record.name == "mealventory.ai.requests"
    ]
    assert len(records) == 1
    event = records[0]
    assert event["request_id"] == "scan-789"
    assert event["route"] == "/lookup/{barcode}"
    assert event["service"] == "ai-services"
    assert event["status"] == 200
    assert "123456789012" not in caplog.text
    assert "private-password" not in caplog.text
    assert "private-token" not in caplog.text


def test_ai_rejects_invalid_request_id(caplog):
    caplog.set_level(logging.INFO, logger="mealventory.ai.requests")
    with TestClient(_app()) as client:
        response = client.get("/lookup/42", headers={"X-Request-ID": "invalid\nnewline"})
    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
    assert "invalid" not in caplog.text
