"""Image preprocessing pipeline with EXIF rotation, color normalization, OCR enhancement, and decode validation."""
import io
import warnings
import numpy as np
from PIL import Image, ImageOps, ImageEnhance

MAX_CLASSIFICATION_SIZE = (224, 224)
MAX_OCR_DIMENSION = 2400
MAX_FOOD_DIMENSION = 1600

# The compressed file limit alone is insufficient: a tiny PNG or WebP can
# describe an enormous bitmap. Keep this separate from the output resize cap.
# Normal 12/24 MP phone photographs are supported; extreme decodes are not.
MAX_DECODE_PIXELS = 25_000_000
MAX_DECODE_EDGE = 10_000


def _check_image_dimensions(image: Image.Image) -> None:
    width, height = image.size
    if (
        width < 1
        or height < 1
        or width > MAX_DECODE_EDGE
        or height > MAX_DECODE_EDGE
        or width * height > MAX_DECODE_PIXELS
    ):
        raise ValueError("Image dimensions exceed the safe scanning limit")


def decode_and_normalize_image(image_bytes: bytes) -> Image.Image:
    """Verify headers and pixel dimensions before decoding any bitmap pixels.

    Raises:
        ValueError: If an image is too large, corrupt, empty or undecodable.
    """
    if not image_bytes:
        raise ValueError("Image bytes are empty")

    try:
        # Pillow's default decompression-bomb threshold is larger than our
        # explicit pixel budget. Convert its warnings to errors as well.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as probe:
                _check_image_dimensions(probe)
                probe.verify()

            # Reopen a separate buffer, since verify() may close the original
            # image's file pointer. Validate again before load().
            with Image.open(io.BytesIO(image_bytes)) as decoded:
                _check_image_dimensions(decoded)
                decoded.load()
                try:
                    normalized = ImageOps.exif_transpose(decoded)
                except (OSError, ValueError):
                    # Malformed EXIF metadata should not block a valid image.
                    normalized = decoded.copy()

                if normalized.mode != "RGB":
                    normalized = normalized.convert("RGB")
                return normalized
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image dimensions exceed the safe scanning limit") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Corrupt or undecodable image") from exc


def preprocess_image_for_mode(image_bytes: bytes, mode: str = "food") -> bytes:
    """Preprocess image bytes tailored to the scanning mode, returning normalized JPEG bytes."""
    img = decode_and_normalize_image(image_bytes)
    w, h = img.size

    if mode in ("receipt", "tag"):
        # Max dimension constraint while preserving high-fidelity text
        max_dim = MAX_OCR_DIMENSION
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_size = (int(round(w * scale)), int(round(h * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Conservative contrast and sharpness enhancement for thermal receipts and shelf tags
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.10)
    else:
        # Food / product mode
        max_dim = MAX_FOOD_DIMENSION
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_size = (int(round(w * scale)), int(round(h * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

    out_bio = io.BytesIO()
    img.save(out_bio, format="JPEG", quality=92, optimize=True)
    return out_bio.getvalue()


def preprocess_for_classification(image_bytes: bytes) -> np.ndarray:
    """Classification input preprocessor for MobileNetV2 with EXIF and RGB normalization."""
    img = decode_and_normalize_image(image_bytes)
    resized = img.resize(MAX_CLASSIFICATION_SIZE, Image.Resampling.BILINEAR)
    img_rgb = np.array(resized, dtype=np.float32)
    return np.expand_dims(img_rgb, axis=0)