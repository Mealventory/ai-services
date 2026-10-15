"""Image preprocessing pipeline with EXIF rotation, color normalization, OCR enhancement, and decode validation."""
import io
import numpy as np
from PIL import Image, ImageOps, ImageEnhance

MAX_CLASSIFICATION_SIZE = (224, 224)
MAX_OCR_DIMENSION = 2400
MAX_FOOD_DIMENSION = 1600


def decode_and_normalize_image(image_bytes: bytes) -> Image.Image:
    """Safely decode raw image bytes, verify integrity, fix EXIF orientation, and normalize to RGB.

    Raises:
        ValueError: If image is empty, corrupt, or cannot be decoded.
    """
    if not image_bytes:
        raise ValueError("Image bytes are empty")

    try:
        bio = io.BytesIO(image_bytes)
        img = Image.open(bio)
        img.verify()
        # Re-open after verify() as documented by Pillow
        bio.seek(0)
        img = Image.open(bio)
        img.load()
    except Exception as exc:
        raise ValueError(f"Corrupt or undecodable image: {exc}") from exc

    # Correct EXIF rotation from mobile cameras
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    if img.mode != "RGB":
        img = img.convert("RGB")

    return img


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