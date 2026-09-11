import os
from config import settings
from google.cloud import vision

# Set credentials from config
if settings.GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS

client = vision.ImageAnnotatorClient()

print("Google Vision Auth Successful")