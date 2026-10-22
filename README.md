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

### Implemented Versioned API Contract

The service exposes strongly typed Pydantic contracts declared in [`schemas/scan.py`](schemas/scan.py) and snapshotted in [`contracts/openapi.json`](contracts/openapi.json):

1. **`POST /scan/`**: Accepts multipart form data with `file` and `mode` (`food` | `receipt` | `tag`).
   - Returns a typed [`ScanResponse`](schemas/scan.py):
     - `type`: Result mode or status (`food`, `receipt`, `tag`, `mismatch`, `unknown`).
     - `items`: List of string names for backend and client compatibility.
     - `item_details`: Array of [`FoodItemDetail`](schemas/scan.py) with `name`, `confidence`, `label`, `category`, `quantity`, `unit`, `price`.
     - `confidence`: Highest confidence score across detected items (`0.0` - `1.0`).
     - `expiry_dates`: Extracted expiration date strings.
     - `needs_user_input` & `prompt`: Flags prompting user input when tag expiry is detected without food name.
2. **`POST /scan/predict-expiry`**: Predicts food shelf-life from purchase date and storage conditions.
   - Returns a typed [`ExpiryPredictionResponse`](schemas/scan.py) with `name`, `purchase_date`, and `predicted_expiry_date`.
3. **`POST /scan/multi`**: Multi-item grocery and produce scanning endpoint.
   - Returns [`ScanResponse`](schemas/scan.py) with `type: "multi"`.
4. **Mock Pipeline**: Activating `GEMINI_API_KEY=mock` or `MOCK_VISION=true` intercepts visual and OCR calls, returning deterministic responses in `< 100ms` for zero-cost offline testing.

## Runtime health probes

- `GET /` is the cheap liveness probe. It confirms the FastAPI process responds
  and does not call Google APIs.
- `GET /ready` is the scan readiness probe. It returns 200 with
  `{"status":"ready","checks":{"model":"ready","vision":"configured"}}`
  when MobileNetV2 is loaded and an explicit, readable Google credentials file
  is configured. Missing required dependencies return 503 with `degraded` or
  `unavailable` status. The response contains dependency states only; it never
  includes credential values or filesystem paths.

Readiness checks local configuration only. It does not verify Google Vision
network access, API enablement, billing, or credential validity by making a
billable request. Check those separately when diagnosing live scan failures.

## Barcode lookup

`GET /barcode/{barcode}` resolves UPC and EAN barcodes through OpenFoodFacts.
The response includes the product name, brand, category, storage zone, and
packaging image when OpenFoodFacts has them. Successful and not-found results
are cached in memory per AI-service process. For refrigerated milk, the response
also includes opened-product guidance (`shelf_life_days: 3`, after opening);
unopened milk should follow the package best-before date. A warm cached lookup
is expected to be fast, while a first lookup depends on OpenFoodFacts response
time. A small curated Kroger fallback handles UPC `0001111090642` because that
product is not currently listed in OpenFoodFacts; its response uses
`source: "kroger_fallback"`.

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
│   └── foodkeeper.json               # Normalized USDA FoodKeeper snapshot (613 entries)
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

## FoodKeeper expiry endpoint

`POST /foodkeeper/predict-expiry` accepts `name`, `storage_zone` (`pantry`,
`fridge`, or `freezer`), and an optional `purchase_date`. It returns a
purchase-date-based estimate only when the best `token_sort_ratio` match is
above 75 and there is no tied food-group match. General preparation words such
as “fresh” and “fillet” are removed before matching. Published ranges use the
upper endpoint; month, week, and year values convert to 30, 7, and 365 days.
Text-only guidance and unsupported zones return `matched: false`.

The checked-in snapshot contains 613 usable food groups from USDA FoodKeeper
data version 128 (the USDA English JSON snapshot dated September 7, 2018).
It is a source-linked, offline snapshot; the importer at
`Scripts/import_foodkeeper.py` converts the USDA workbook JSON export into the
runtime format. Shelf-life estimates describe storage guidance and quality,
not a guarantee that food is safe to eat.

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

---

## 5. Scan Accuracy & Latency Benchmark Suite

The repository includes a repeatable evaluation harness for measuring recognition quality, exact-match expiry parsing, and latency:

```bash
# Run deterministic offline benchmarks
python -m benchmarks.runner

# Compare against saved baseline to detect regressions
python -m benchmarks.runner --baseline benchmarks/baselines/default_baseline.json
```

See [benchmarks/README.md](benchmarks/README.md) for full benchmark documentation and CLI flags.

