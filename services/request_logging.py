"""Structured, privacy-safe HTTP logging for the AI service."""
import json
import logging
import re
import time
from uuid import uuid4

from fastapi import Request

_LOG = logging.getLogger("mealventory.ai.requests")
_LOG.setLevel(logging.INFO)
# Ensure INFO events reach the process logs even if the root logger is unconfigured.
if not _LOG.hasHandlers():
    _LOG.addHandler(logging.StreamHandler())
_ALLOWED_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


async def request_logging_middleware(request: Request, call_next):
    incoming_id = request.headers.get("X-Request-ID", "")
    request_id = incoming_id if _ALLOWED_ID.fullmatch(incoming_id) else uuid4().hex
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        event = {
            "event": "http_request",
            "service": "ai-services",
            "request_id": request_id,
            "method": request.method,
            "route": getattr(route, "path", None) or "<unmatched>",
            "status": status,
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
            "failure_category": (
                "none" if status < 400 else
                "service_unavailable" if status in (502, 503, 504) else
                "server_error" if status >= 500 else "client_error"
            ),
        }
        # Never log query parameters (which can contain food names), image
        # payloads, authorization headers, or upstream exception messages.
        _LOG.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
