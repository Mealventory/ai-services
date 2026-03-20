from google.cloud import vision

client = vision.ImageAnnotatorClient()

async def detect_text_type(image_bytes):
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        return None

    full_text = texts[0].description
    line_count = len(full_text.split("\n"))

    if line_count > 5:
        return {
            "type": "receipt",
            "confidence": 0.85
        }
    else:
        return {
            "type": "tag",
            "confidence": 0.75
        }