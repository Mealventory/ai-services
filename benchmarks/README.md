# Scan Accuracy and Latency Benchmark Suite

Repeatable evaluation harness for measuring recognition accuracy, date parsing fidelity, and execution latency across Mealventory scan pipelines (`food`, `receipt`, and `tag`).

## 🎯 Objectives
- **Measurable Recognition Quality**: Quantify precision, recall, and F1-score across standardized food fixture sets.
- **Exact-Match Expiry Fidelity**: Explicitly measure exact matches on expiration and best-before date extraction.
- **Latency Distribution Tracking**: Profile per-image and aggregate latency distributions (min, mean, p50, p90, p95, max).
- **Automated Regression Prevention**: Compare changes against a saved baseline JSON file; fail CI on regressions exceeding allowable thresholds.
- **Zero Sensitive Data**: All fixtures are synthetic, deterministic, non-sensitive samples generated locally without private receipts or copyrighted imagery.

---

## 🚀 Running the Benchmarks

### 1. Default Run (Deterministic Offline Mode)
Runs all 10 fixtures across all modes without external network or Google Vision billing calls:
```bash
python -m benchmarks.runner
```

### 2. Compare Against Saved Baseline
Evaluates fixtures and validates that performance meets or exceeds the baseline:
```bash
python -m benchmarks.runner --baseline benchmarks/baselines/default_baseline.json
```
Exit code is `0` on success and `1` if an accuracy drop or latency regression is detected.

### 3. Save / Update Baseline
```bash
python -m benchmarks.runner --save-baseline benchmarks/baselines/default_baseline.json
```

### 4. Mode-Specific Evaluation
Target specific modes (`food`, `receipt`, or `tag`):
```bash
python -m benchmarks.runner --mode food
python -m benchmarks.runner --mode receipt
python -m benchmarks.runner --mode tag
```

### 5. Live Cloud Evaluation (Opt-in)
Evaluates using active Google Cloud Vision and Gemini credentials:
```bash
python -m benchmarks.runner --live
```

---

## 📊 Evaluation Metrics

| Metric | Scope | Target |
|---|---|---|
| **Precision** | Macro average per mode | `>= 80.0%` |
| **Recall** | Macro average per mode | `>= 80.0%` |
| **F1-Score** | Harmonic mean of P & R | `>= 0.8000` |
| **Scan Type Accuracy** | Correct classification (`food`, `receipt`, `tag`) | `100.0%` |
| **Expiry Exact Match** | Normalized exact-match date string | `100.0%` on tag mode |
| **Mean Latency** | Offline / Local mock | `< 50ms` |

---

## 📁 Directory Structure
```
benchmarks/
├── README.md                      # Documentation & usage instructions
├── __init__.py
├── runner.py                      # Main CLI benchmark runner
├── metrics.py                     # Item metrics, exact match, latency stats & baseline comparator
├── baselines/
│   └── default_baseline.json      # Version-controlled reference baseline
├── fixtures/
│   ├── fixtures.json              # Fixture manifest (expected items, types, dates)
│   ├── generate_fixtures.py       # Deterministic PIL fixture generator
│   └── *.jpg                      # Generated fixture images
└── reports/
    └── latest_benchmark.json      # Machine-readable JSON summary artifact
```
