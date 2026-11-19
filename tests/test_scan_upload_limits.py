"""Bounded and deterministic scan-upload tests without any live model calls."""
import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api import scan


class FakeUpload:
    """An upload whose logical size need not be allocated or decoded."""

    def __init__(self, size, content_type="image/jpeg"):
        self.size = size
        self.content_type = content_type
        self.read_sizes = []
        self.closed = False

    async def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("Unbounded upload read")
        return b"x" * min(self.size, size)

    async def close(self):
        self.closed = True


class UploadLimitTests(unittest.TestCase):
    def test_single_and_multi_reject_oversized_streams_without_full_reads(self):
        for route in ("single", "multi"):
            with self.subTest(route=route):
                upload = FakeUpload(scan.MAX_IMAGE_BYTES + 100_000_000)
                with patch.object(scan, "preprocess_image_for_mode") as preprocess:
                    with self.assertRaises(HTTPException) as error:
                        if route == "single":
                            asyncio.run(scan.scan_image("food", upload))
                        else:
                            asyncio.run(scan.scan_multi(upload))
                self.assertEqual(error.exception.status_code, 413)
                self.assertEqual(upload.read_sizes, [scan.MAX_IMAGE_BYTES + 1])
                self.assertTrue(upload.closed)
                preprocess.assert_not_called()

    def test_empty_and_unsupported_uploads_close_on_both_routes(self):
        for route in ("single", "multi"):
            for size, mime, expected in (
                (0, "image/jpeg", 400),
                (10, "application/octet-stream", 415),
            ):
                with self.subTest(route=route, size=size, mime=mime):
                    upload = FakeUpload(size, content_type=mime)
                    with self.assertRaises(HTTPException) as error:
                        if route == "single":
                            asyncio.run(scan.scan_image("food", upload))
                        else:
                            asyncio.run(scan.scan_multi(upload))
                    self.assertEqual(error.exception.status_code, expected)
                    self.assertTrue(upload.closed)
                    self.assertEqual(
                        upload.read_sizes,
                        [] if expected == 415 else [scan.MAX_IMAGE_BYTES + 1],
                    )

    def test_read_failure_still_closes_upload(self):
        upload = FakeUpload(100)

        async def fail_read(size):
            raise OSError("disconnected upload stream")

        upload.read = fail_read
        with self.assertRaises(OSError):
            asyncio.run(scan.read_scan_upload(upload))
        self.assertTrue(upload.closed)

    def test_valid_uploads_still_scan_in_single_and_multi_modes(self):
        items = [{"name": "apple", "confidence": 0.96}]
        for route in ("single", "multi"):
            with self.subTest(route=route):
                upload = FakeUpload(5)
                with patch.object(scan, "preprocess_image_for_mode", side_effect=lambda content, **_: content):
                    with patch.object(scan, "detect_food", new_callable=AsyncMock, return_value=items):
                        result = (
                            asyncio.run(scan.scan_image("food", upload))
                            if route == "single"
                            else asyncio.run(scan.scan_multi(upload))
                        )
                self.assertEqual(result["items"], ["apple"])
                self.assertEqual(result["type"], "food" if route == "single" else "multi")
                self.assertEqual(upload.read_sizes, [scan.MAX_IMAGE_BYTES + 1])
                self.assertTrue(upload.closed)


if __name__ == "__main__":
    unittest.main()
