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

## Current implementation and future direction

The overview above is retained from the local repository. The current code uses
Google Vision and Keras MobileNetV2; it does not implement every capability in
the target design below. See [SETUP.md](SETUP.md) for environment setup.

---

# Mealventory AI & Vision Microservice: Target Final State & Purpose

## 1. Purpose of the Repository
The `ai-services` repository provides the artificial intelligence, computer vision, and food heuristics intelligence for the **Mealventory** platform. Implemented with **FastAPI (Python 3.11+)** and powered by **Google Gemini 1.5 Flash Structured Multimodal API**, it transforms raw sensory inputs (camera photos of paper grocery receipts, loose fresh produce, packaged goods, and barcodes) into clean, structured, and actionable pantry inventory data.

### Key Functional Responsibilities:
- **Receipt OCR & Line Item Extraction**: Parse cluttered, unevenly lit supermarket receipts (e.g., Walmart, Costco, Trader Joe's) into clean item names, prices, quantities, and category labels.
- **Multi-Item Produce & Pantry Vision**: Detect multiple individual fresh items in a single photo (e.g., apples, bananas, bell peppers on a countertop), providing normalized 2D bounding boxes `[ymin, xmin, ymax, xmax]` for interactive user review.
- **USDA FoodKeeper Shelf-Life Heuristics**: Map recognized food items to the official USDA FoodKeeper database, estimating precise expiration dates across different storage zones (Pantry, Fridge, Freezer) using fuzzy string matching (`RapidFuzz`).
- **OpenFoodFacts Barcode Fallback Engine**: Resolve EAN-13 and UPC barcodes against the OpenFoodFacts API v2, extracting verified brand names, food categories, and packaging imagery.
- **Mockable Offline Development**: Provide a deterministic mock pipeline (`GEMINI_API_KEY=mock`) allowing backend and frontend developers to test vision and OCR flows completely offline without incurring API costs.

---

## 2. Target Architecture & Pipeline Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                     AI SERVICE INTERNAL PIPELINE                       │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                            POST /scan/multi
                      (Image Buffer + Scan Mode)
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
             [Receipt Mode]                [Produce/Food Mode]
                     │                             │
          Gemini 1.5 Flash OCR           Gemini 1.5 Flash Vision
         (Structured JSON Prompt)        (Multi-Item Bounding Boxes)
                     │                             │
                     └──────────────┬──────────────┘
                                    │
                                    ▼
                     [Extracted Normalized Items]
                     - Name, Quantity, Unit, Zone
                                    │
                                    ▼
                     USDA FoodKeeper Fuzzy Matcher
                      (RapidFuzz Token Sort Ratio)
                                    │
                                    ▼
                    [Calculated Shelf-Life & Expiry]
                     - Expiry Date (YYYY-MM-DD)
                     - Confidence Score (0.00 - 1.00)
                                    │
                                    ▼
                       Standardized API Response
```

### Module Organization
```
ai-services/
├── api/
│   ├── v1/
│   │   ├── scan.py                   # Multi-mode vision & OCR endpoints
│   │   ├── barcode.py                # OpenFoodFacts barcode resolution
│   │   ├── heuristics.py             # Direct USDA FoodKeeper query endpoints
│   │   └── health.py                 # Liveness & model readiness check
│   └── router.py                     # Unified router
│
├── core/
│   ├── config.py                     # Pydantic Settings (GEMINI_API_KEY, thresholds)
│   └── logging.py                    # Structured logging
│
├── data/
│   └── foodkeeper.json               # Seeded USDA FoodKeeper reference database
│
├── models/                           # Pydantic v2 Contract Schemas
│   ├── detection.py                  # DetectedItem, BoundingBox, ScanResponse
│   └── barcode.py                    # BarcodeProductResponse
│
├── services/                         # Core AI & Heuristic Engines
│   ├── gemini_vision.py              # Google GenAI SDK interface with JSON schema enforcement
│   ├── foodkeeper_engine.py          # Fuzzy matching & shelf life calculator
│   ├── barcode_service.py            # OpenFoodFacts client with local cache
│   ├── image_preprocessor.py         # Contrast enhancement, resizing & orientation correction
│   └── mock_engine.py                # Deterministic synthetic vision response generator
│
├── tests/                            # Pytest suite with real & synthetic images
│   ├── test_ocr.py
│   ├── test_foodkeeper.py
│   └── test_barcode.py
│
├── Dockerfile                        # Multi-stage image with OpenCV/GL dependencies
└── requirements.txt                  # Locked Python 3.11 requirements
```

---

## 3. Standardized Output Contract (`POST /scan/multi`)

```json
{
  "scan_type": "receipt",
  "processing_time_ms": 782,
  "detected_store": "Trader Joe's",
  "items": [
    {
      "name": "Organic Honeycrisp Apples",
      "quantity": 1.0,
      "unit": "bag",
      "category": "Produce",
      "confidence": 0.96,
      "suggested_zone": "fridge",
      "shelf_life_days": 21,
      "estimated_expiry": "2026-09-28",
      "heuristic_source": "USDA_FOODKEEPER",
      "bounding_box": null
    },
    {
      "name": "Greek Whole Milk Yogurt",
      "quantity": 2.0,
      "unit": "tub",
      "category": "Dairy",
      "confidence": 0.94,
      "suggested_zone": "fridge",
      "shelf_life_days": 14,
      "estimated_expiry": "2026-09-21",
      "heuristic_source": "USDA_FOODKEEPER",
      "bounding_box": null
    }
  ]
}
```

---

## 4. Key Performance & Reliability Targets
- **Inference Latency**: < 1.5s for receipt OCR; < 1.0s for multi-item produce vision.
- **JSON Schema Guarantee**: 100% adherence to Pydantic models through Gemini 1.5 Flash `response_schema` enforcement (eliminating malformed regex JSON failures).
- **Graceful Fallback**: In the event of OCR ambiguity, the service preserves the raw text snippet and marks confidence as `< 0.70`, allowing the user to review and correct on the mobile client.
