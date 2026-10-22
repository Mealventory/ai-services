import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MOCK_VISION = os.getenv("MOCK_VISION", "").lower() in ("true", "1", "yes") or os.getenv("GEMINI_API_KEY") == "mock"
    MODEL_NAME = "MobileNetV2"

settings = Settings()