"""Unit tests for the scan accuracy and latency benchmark suite (#16)."""
import unittest
from pathlib import Path

from benchmarks.metrics import (
    calculate_item_set_metrics,
    calculate_exact_match,
    calculate_latency_stats,
    compare_with_baseline,
)
from benchmarks.runner import run_benchmarks
from benchmarks.fixtures.generate_fixtures import MANIFEST_PATH


class TestBenchmarkSuite(unittest.TestCase):
    def test_item_set_metrics_perfect_match(self):
        metrics = calculate_item_set_metrics(["apple", "banana"], ["apple", "banana"])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 1.0)
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["false_negatives"], 0)

    def test_item_set_metrics_partial_match(self):
        # Expected: apple, banana. Actual: apple, orange.
        # TP=1, FP=1, FN=1 -> P=0.5, R=0.5, F1=0.5
        metrics = calculate_item_set_metrics(["apple", "banana"], ["apple", "orange"])
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)

    def test_item_set_metrics_empty_handling(self):
        # Both empty -> 1.0
        both_empty = calculate_item_set_metrics([], [])
        self.assertEqual(both_empty["f1"], 1.0)

        # Expected empty, actual has items -> precision 0.0, recall 1.0, f1 0.0
        actual_only = calculate_item_set_metrics([], ["milk"])
        self.assertEqual(actual_only["precision"], 0.0)
        self.assertEqual(actual_only["f1"], 0.0)

    def test_exact_match_comparisons(self):
        self.assertTrue(calculate_exact_match("food", "Food"))
        self.assertTrue(calculate_exact_match(["2026-11-20"], ["2026-11-20"]))
        self.assertFalse(calculate_exact_match("tag", "food"))
        self.assertFalse(calculate_exact_match(["2026-11-20"], ["2026-11-21"]))
        self.assertTrue(calculate_exact_match(None, None))
        self.assertFalse(calculate_exact_match("tag", None))

    def test_latency_stats_calculation(self):
        lats = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = calculate_latency_stats(lats)
        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["min_ms"], 10.0)
        self.assertEqual(stats["max_ms"], 50.0)
        self.assertEqual(stats["mean_ms"], 30.0)
        self.assertEqual(stats["p50_ms"], 30.0)

    def test_baseline_comparison_detects_f1_regression(self):
        current = {
            "modes": {
                "food": {"f1_macro": 0.70, "latency": {"mean_ms": 20.0}},
            }
        }
        baseline = {
            "modes": {
                "food": {"f1_macro": 0.95, "latency": {"mean_ms": 20.0}},
            }
        }
        comp = compare_with_baseline(current, baseline, allowed_f1_drop=0.05)
        self.assertTrue(comp["has_regressions"])
        self.assertTrue(any("F1 regressed" in r for r in comp["regressions"]))

    def test_baseline_comparison_detects_latency_regression(self):
        current = {
            "modes": {
                "tag": {"f1_macro": 1.0, "latency": {"mean_ms": 400.0}, "expiry_exact_match_rate": 1.0},
            }
        }
        baseline = {
            "modes": {
                "tag": {"f1_macro": 1.0, "latency": {"mean_ms": 100.0}, "expiry_exact_match_rate": 1.0},
            }
        }
        comp = compare_with_baseline(current, baseline)
        self.assertTrue(comp["has_regressions"])
        self.assertTrue(any("latency increased" in r for r in comp["regressions"]))

    def test_full_benchmark_runner_offline_execution(self):
        summary = run_benchmarks(
            fixtures_path=MANIFEST_PATH,
            mode_filter="all",
            offline=True,
        )
        self.assertEqual(summary["fixture_count_total"], 10)
        self.assertIn("food", summary["modes"])
        self.assertIn("receipt", summary["modes"])
        self.assertIn("tag", summary["modes"])
        self.assertEqual(summary["type_accuracy"], 1.0)
        self.assertEqual(summary["modes"]["tag"]["expiry_exact_match_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
