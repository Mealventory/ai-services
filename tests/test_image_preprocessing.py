"""Tests for EXIF orientation, RGB normalization, OCR enhancements, and corrupt image rejection."""
import asyncio
import io
import unittest
from PIL import Image

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api.scan import scan_image, scan_multi
from services.image_preprocessing import (
    decode_and_normalize_image,
    preprocess_image_for_mode,
    preprocess_for_classification,
)


class TestImagePreprocessing(unittest.TestCase):
    def _create_test_image(self, size=(200, 100), color=(255, 0, 0), mode="RGB", orientation=None):
        img = Image.new(mode, size, color)
        bio = io.BytesIO()
        exif = img.getexif()
        if orientation:
            # Tag 0x0112 is Orientation
            exif[0x0112] = orientation
            img.save(bio, format="JPEG", exif=exif)
        else:
            img.save(bio, format="JPEG")
        return bio.getvalue()

    def test_corrupt_bytes_rejected(self):
        with self.assertRaises(ValueError):
            decode_and_normalize_image(b"not-an-image-at-all-garbage-bytes")

        with self.assertRaises(ValueError):
            decode_and_normalize_image(b"")

    def test_color_format_normalized_to_rgb(self):
        # Grayscale 'L'
        gray_bytes = self._create_test_image(mode="L", color=128)
        img = decode_and_normalize_image(gray_bytes)
        self.assertEqual(img.mode, "RGB")

    def test_exif_orientation_correction(self):
        # Orientation 6 means 90 degrees CW rotation needed
        rotated_bytes = self._create_test_image(size=(300, 150), orientation=6)
        img = decode_and_normalize_image(rotated_bytes)
        # Transpose swaps width and height for orientation 6
        self.assertEqual(img.size, (150, 300))

    def test_receipt_preprocessing_preserves_dimensions_and_enhances(self):
        large_bytes = self._create_test_image(size=(3000, 1500))
        processed = preprocess_image_for_mode(large_bytes, mode="receipt")
        out_img = Image.open(io.BytesIO(processed))
        # Scaled down to max dimension 2400
        self.assertEqual(max(out_img.size), 2400)
        self.assertEqual(out_img.format, "JPEG")

    def test_food_preprocessing_scales_within_max_bounds(self):
        large_bytes = self._create_test_image(size=(2000, 1000))
        processed = preprocess_image_for_mode(large_bytes, mode="food")
        out_img = Image.open(io.BytesIO(processed))
        self.assertEqual(max(out_img.size), 1600)

    def test_classification_preprocessing_output_shape(self):
        img_bytes = self._create_test_image(size=(100, 100))
        arr = preprocess_for_classification(img_bytes)
        self.assertEqual(arr.shape, (1, 224, 224, 3))
        self.assertEqual(arr.dtype.name, "float32")

    def test_scan_route_returns_400_on_corrupt_image(self):
        corrupt_file = UploadFile(
            io.BytesIO(b"completely corrupt content"),
            filename="corrupt.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(scan_image("food", corrupt_file))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Corrupt or undecodable image", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
