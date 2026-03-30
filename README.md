# Mealventory AI Service

AI microservice for image processing and OCR functionality.

Handles receipt scanning, produce identification, and ML-based classification.

---

## 🧠 Core Capabilities

- Google Vision OCR
- MobileNetV2 produce classification
- Image preprocessing
- Confidence scoring
- Structured inventory output

---

## 🛠 Tech Stack

- FastAPI
- TensorFlow / PyTorch
- Google Vision API
- Pillow
- NumPy

---

## 📂 Structure

## API Contract update

POST /scan/

- Request content type: multipart/form-data
- Required fields:
	- mode: one of food, tag, receipt
	- file: image/jpeg, image/png, or image/webp (max 8MB)

Examples:

- mode=food: classify food image only
- mode=receipt: OCR + receipt detection
- mode=tag: OCR + product tag detection
