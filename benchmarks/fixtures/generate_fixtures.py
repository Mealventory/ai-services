"""Deterministic generator for synthetic scan benchmark fixture images.

Ensures no private receipts, sensitive photos, or copyrighted assets are committed.
"""
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = FIXTURES_DIR / "fixtures.json"


def generate_fixture_image(fixture: dict) -> bytes:
    """Generate a clean synthetic image corresponding to a benchmark fixture."""
    mode = fixture.get("mode", "food")
    img_id = fixture.get("id", "fixture")

    if mode == "receipt":
        # Narrow vertical receipt look
        img = Image.new("RGB", (600, 1000), color=(250, 250, 245))
        draw = ImageDraw.Draw(img)
        # Header banner
        draw.rectangle([(20, 20), (580, 80)], fill=(235, 235, 230))
        # Draw receipt text
        text = fixture.get("synthetic_text", "RECEIPT")
        draw.text((40, 100), text, fill=(30, 30, 30))
        # Barcode stripes at the bottom
        for x in range(50, 550, 15):
            draw.line([(x, 900), (x, 960)], fill=(20, 20, 20), width=4)

    elif mode == "tag":
        # Small rectangular tag
        img = Image.new("RGB", (640, 400), color=(240, 245, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(30, 30), (610, 370)], outline=(100, 140, 180), width=3)
        text = fixture.get("synthetic_text", "BEST BEFORE 2026-12-31")
        draw.text((60, 120), text, fill=(20, 40, 80))

    else:
        # Food mode: colored produce / packaging representation
        category = fixture.get("category", "produce")
        bg_colors = {
            "produce": (245, 255, 245),
            "dairy": (245, 250, 255),
            "bakery": (255, 250, 240),
        }
        accent_colors = {
            "apple": (210, 45, 45),
            "banana": (245, 215, 60),
            "milk": (230, 240, 250),
            "bread": (195, 140, 75),
            "yogurt": (220, 230, 245),
        }
        item_name = fixture.get("expected_items", ["food"])[0] if fixture.get("expected_items") else "food"
        img = Image.new("RGB", (640, 640), color=bg_colors.get(category, (245, 245, 245)))
        draw = ImageDraw.Draw(img)
        # Center object
        color = accent_colors.get(item_name, (180, 180, 180))
        draw.ellipse([(160, 160), (480, 480)], fill=color, outline=(80, 80, 80), width=2)
        draw.text((220, 300), f"SAMPLE: {item_name.upper()}", fill=(20, 20, 20))

    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=90)
    return bio.getvalue()


def ensure_fixtures_generated():
    """Ensure all declared fixture image files are generated on disk."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing {MANIFEST_PATH}")

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for fix in data.get("fixtures", []):
        filename = fix.get("filename")
        if not filename:
            continue
        dest = FIXTURES_DIR / filename
        if not dest.exists():
            img_bytes = generate_fixture_image(fix)
            dest.write_bytes(img_bytes)


if __name__ == "__main__":
    ensure_fixtures_generated()
    print("All benchmark fixture images verified and generated.")
