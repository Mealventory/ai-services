"""Metrics evaluation for scan accuracy and latency benchmarks."""
from typing import Any, Dict, List, Optional
import math


def normalize_token(token: str) -> str:
    """Normalize a food name or date token for comparison."""
    return token.strip().lower()


def calculate_item_set_metrics(expected_items: List[str], actual_items: List[str]) -> Dict[str, float]:
    """Calculate precision, recall, and F1 score for food item recognition."""
    expected_set = {normalize_token(x) for x in expected_items}
    actual_set = {normalize_token(x) for x in actual_items}

    if not expected_set and not actual_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "true_positives": 0, "false_positives": 0, "false_negatives": 0}

    true_positives = len(expected_set & actual_set)
    false_positives = len(actual_set - expected_set)
    false_negatives = len(expected_set - actual_set)

    precision = true_positives / len(actual_set) if actual_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def calculate_exact_match(expected: Any, actual: Any) -> bool:
    """Check exact match between expected and actual value."""
    if isinstance(expected, list) and isinstance(actual, list):
        norm_exp = sorted([normalize_token(str(x)) for x in expected])
        norm_act = sorted([normalize_token(str(x)) for x in actual])
        return norm_exp == norm_act

    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False

    return normalize_token(str(expected)) == normalize_token(str(actual))


def calculate_latency_stats(latencies_ms: List[float]) -> Dict[str, float]:
    """Compute summary statistics for a collection of latency measurements in milliseconds."""
    if not latencies_ms:
        return {"count": 0, "min_ms": 0.0, "max_ms": 0.0, "mean_ms": 0.0, "p50_ms": 0.0, "p90_ms": 0.0, "p95_ms": 0.0}

    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)

    def percentile(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_lats[int(k)]
        d0 = sorted_lats[int(f)] * (c - k)
        d1 = sorted_lats[int(c)] * (k - f)
        return d0 + d1

    return {
        "count": n,
        "min_ms": round(sorted_lats[0], 2),
        "max_ms": round(sorted_lats[-1], 2),
        "mean_ms": round(sum(sorted_lats) / n, 2),
        "p50_ms": round(percentile(0.50), 2),
        "p90_ms": round(percentile(0.90), 2),
        "p95_ms": round(percentile(0.95), 2),
    }


def compare_with_baseline(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    allowed_f1_drop: float = 0.05,
    allowed_latency_increase_ratio: float = 0.25,
) -> Dict[str, Any]:
    """Compare current benchmark results against baseline and detect regressions."""
    regressions: List[str] = []
    comparison_summary: Dict[str, Any] = {}

    curr_modes = current.get("modes", {})
    base_modes = baseline.get("modes", {})

    for mode, curr_data in curr_modes.items():
        if mode not in base_modes:
            continue
        base_data = base_modes[mode]

        # Check F1 regression
        curr_f1 = curr_data.get("f1_macro", 0.0)
        base_f1 = base_data.get("f1_macro", 0.0)
        f1_delta = curr_f1 - base_f1
        if f1_delta < -allowed_f1_drop:
            regressions.append(
                f"Mode '{mode}' F1 regressed from {base_f1} to {curr_f1} (drop: {round(f1_delta, 4)})"
            )

        # Check Latency regression
        curr_lat = curr_data.get("latency", {}).get("mean_ms", 0.0)
        base_lat = base_data.get("latency", {}).get("mean_ms", 0.0)
        lat_ratio = (curr_lat - base_lat) / base_lat if base_lat > 0 else 0.0
        if lat_ratio > allowed_latency_increase_ratio and (curr_lat - base_lat) > 50.0:
            regressions.append(
                f"Mode '{mode}' latency increased by {round(lat_ratio * 100, 1)}% ({base_lat}ms -> {curr_lat}ms)"
            )

        # Check Expiry date exact-match regression for tag mode
        if mode == "tag":
            curr_exp = curr_data.get("expiry_exact_match_rate", 0.0)
            base_exp = base_data.get("expiry_exact_match_rate", 0.0)
            if curr_exp < base_exp:
                regressions.append(
                    f"Tag mode expiry exact match rate dropped from {base_exp} to {curr_exp}"
                )

        comparison_summary[mode] = {
            "f1_current": curr_f1,
            "f1_baseline": base_f1,
            "f1_delta": round(f1_delta, 4),
            "latency_mean_current_ms": curr_lat,
            "latency_mean_baseline_ms": base_lat,
            "latency_delta_percent": round(lat_ratio * 100, 2),
        }

    return {
        "has_regressions": len(regressions) > 0,
        "regressions": regressions,
        "mode_comparisons": comparison_summary,
    }
