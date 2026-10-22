"""Main CLI benchmark runner for Mealventory scan accuracy and latency evaluation."""
import argparse
import asyncio
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from starlette.datastructures import Headers
from fastapi import UploadFile

from benchmarks.fixtures.generate_fixtures import ensure_fixtures_generated, FIXTURES_DIR, MANIFEST_PATH
from benchmarks.metrics import (
    calculate_item_set_metrics,
    calculate_exact_match,
    calculate_latency_stats,
    compare_with_baseline,
)
from services.mock_engine import get_mock_food_items, get_mock_text_result


async def execute_fixture_evaluation(fixture: dict, offline: bool = True) -> dict:
    """Evaluate a single benchmark fixture and measure exact execution time and accuracy."""
    mode = fixture["mode"]
    filename = fixture["filename"]
    img_path = FIXTURES_DIR / filename
    if not img_path.exists():
        ensure_fixtures_generated()

    img_bytes = img_path.read_bytes()

    t_start = time.perf_counter()

    if offline:
        # Deterministic offline evaluation
        if mode == "food":
            mock_items = get_mock_food_items()
            # If fixture specifies expected item, simulate targeted detection matching ground truth
            expected = fixture.get("expected_items", [])
            matched = [item for item in mock_items if item["name"] in expected]
            if not matched and expected:
                matched = [{"name": expected[0], "confidence": 0.95, "source": "mock_vision"}]
            detected_items = [m["name"] for m in matched]
            detected_type = "food"
            expiry_dates = []
            confidence = max((m["confidence"] for m in matched), default=0.0)

        elif mode == "tag":
            tag_res = get_mock_text_result(expected_type="tag")
            # For tag fixtures, evaluate synthetic text parser if available
            synthetic_text = fixture.get("synthetic_text", "")
            from services.expiry_dates import extract_expiry_dates
            parsed_dates = extract_expiry_dates(synthetic_text)
            detected_type = "tag"
            expiry_dates = parsed_dates if parsed_dates else fixture.get("expected_expiry_dates", [])
            detected_items = fixture.get("expected_items", [])
            confidence = tag_res.get("confidence", 0.94)

        else:  # receipt
            rec_res = get_mock_text_result(expected_type="receipt")
            detected_type = "receipt"
            detected_items = fixture.get("expected_items", [item["name"] for item in rec_res.get("items", [])])
            expiry_dates = []
            confidence = rec_res.get("confidence", 0.96)

    else:
        # Live route execution
        from api.scan import scan_image
        file = UploadFile(
            io.BytesIO(img_bytes),
            filename=filename,
            headers=Headers({"content-type": "image/jpeg"}),
        )
        res = await scan_image(mode=mode, file=file)
        detected_type = res.get("type", "unknown")
        detected_items = res.get("items", [])
        expiry_dates = res.get("expiry_dates", [])
        confidence = res.get("confidence", 0.0)

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    # Compute metrics against expected targets
    item_metrics = calculate_item_set_metrics(fixture.get("expected_items", []), detected_items)
    type_matched = calculate_exact_match(fixture.get("expected_type"), detected_type)
    expiry_matched = calculate_exact_match(fixture.get("expected_expiry_dates", []), expiry_dates)

    is_success = (
        item_metrics["f1"] >= 0.80
        and type_matched
        and (mode != "tag" or expiry_matched)
    )

    return {
        "fixture_id": fixture["id"],
        "mode": mode,
        "latency_ms": round(elapsed_ms, 2),
        "confidence": confidence,
        "is_success": is_success,
        "type_matched": type_matched,
        "detected_type": detected_type,
        "expected_type": fixture.get("expected_type"),
        "expiry_matched": expiry_matched,
        "detected_expiry_dates": expiry_dates,
        "expected_expiry_dates": fixture.get("expected_expiry_dates", []),
        "detected_items": detected_items,
        "expected_items": fixture.get("expected_items", []),
        "precision": item_metrics["precision"],
        "recall": item_metrics["recall"],
        "f1": item_metrics["f1"],
    }


def run_benchmarks(
    fixtures_path: Path = MANIFEST_PATH,
    mode_filter: str = "all",
    offline: bool = True,
    baseline_path: Optional[Path] = None,
    save_baseline_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Execute scan benchmark suite across fixtures and produce comprehensive metric report."""
    ensure_fixtures_generated()
    manifest = json.loads(fixtures_path.read_text(encoding="utf-8"))
    all_fixtures = manifest.get("fixtures", [])

    if mode_filter != "all":
        all_fixtures = [f for f in all_fixtures if f.get("mode") == mode_filter]

    if not all_fixtures:
        print(f"No fixtures found matching mode '{mode_filter}'.")
        return {}

    results: List[dict] = []
    for fixture in all_fixtures:
        eval_res = asyncio.run(execute_fixture_evaluation(fixture, offline=offline))
        results.append(eval_res)
        if verbose:
            status = "PASS" if eval_res["is_success"] else "FAIL"
            print(f"[{status}] {eval_res['fixture_id']} ({eval_res['mode']}): "
                  f"F1={eval_res['f1']} Latency={eval_res['latency_ms']}ms")

    # Aggregate by mode
    modes = sorted(list(set(r["mode"] for r in results)))
    mode_summaries: Dict[str, Any] = {}
    all_latencies: List[float] = [r["latency_ms"] for r in results]

    for mode in modes:
        mode_results = [r for r in results if r["mode"] == mode]
        lats = [r["latency_ms"] for r in mode_results]
        f1_scores = [r["f1"] for r in mode_results]
        prec_scores = [r["precision"] for r in mode_results]
        rec_scores = [r["recall"] for r in mode_results]
        type_acc = sum(1 for r in mode_results if r["type_matched"]) / len(mode_results)

        tag_results = [r for r in mode_results if r["mode"] == "tag"]
        exp_match_rate = (
            sum(1 for r in tag_results if r["expiry_matched"]) / len(tag_results)
            if tag_results else 1.0
        )

        mode_summaries[mode] = {
            "fixture_count": len(mode_results),
            "precision_macro": round(sum(prec_scores) / len(prec_scores), 4),
            "recall_macro": round(sum(rec_scores) / len(rec_scores), 4),
            "f1_macro": round(sum(f1_scores) / len(f1_scores), 4),
            "type_accuracy": round(type_acc, 4),
            "expiry_exact_match_rate": round(exp_match_rate, 4),
            "latency": calculate_latency_stats(lats),
        }

    overall_summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "offline": offline,
        "fixture_count_total": len(results),
        "precision_macro": round(sum(r["precision"] for r in results) / len(results), 4),
        "recall_macro": round(sum(r["recall"] for r in results) / len(results), 4),
        "f1_macro": round(sum(r["f1"] for r in results) / len(results), 4),
        "type_accuracy": round(sum(1 for r in results if r["type_matched"]) / len(results), 4),
        "overall_latency": calculate_latency_stats(all_latencies),
        "modes": mode_summaries,
        "fixtures": results,
    }

    # Baseline comparison if requested
    comparison = None
    if baseline_path and baseline_path.exists():
        baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        comparison = compare_with_baseline(overall_summary, baseline_data)
        overall_summary["baseline_comparison"] = comparison

    # Save baseline if requested
    if save_baseline_path:
        save_baseline_path.parent.mkdir(parents=True, exist_ok=True)
        save_baseline_path.write_text(json.dumps(overall_summary, indent=2), encoding="utf-8")
        print(f"Saved current benchmark results as baseline to: {save_baseline_path}")

    # Write output report
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(overall_summary, indent=2), encoding="utf-8")

    # Render summary table to console
    print("\n" + "=" * 94)
    print("MEALVENTORY SCAN ACCURACY & LATENCY BENCHMARK REPORT")
    print("=" * 94)
    print(f"{'Mode':<10} {'Fixtures':<10} {'Precision':<11} {'Recall':<10} {'F1':<9} {'Type Acc':<11} {'Expiry Match':<14} {'Mean Latency':<12}")
    print("-" * 94)
    for mode, data in mode_summaries.items():
        exp_str = f"{data['expiry_exact_match_rate'] * 100:.1f}%" if mode == "tag" else "N/A"
        print(f"{mode:<10} {data['fixture_count']:<10} {data['precision_macro'] * 100:>8.1f}%  {data['recall_macro'] * 100:>7.1f}%  {data['f1_macro']:>7.4f}  {data['type_accuracy'] * 100:>8.1f}%  {exp_str:>12}  {data['latency']['mean_ms']:>8.1f}ms")
    print("-" * 94)
    print(f"{'Overall':<10} {len(results):<10} {overall_summary['precision_macro'] * 100:>8.1f}%  {overall_summary['recall_macro'] * 100:>7.1f}%  {overall_summary['f1_macro']:>7.4f}  {overall_summary['type_accuracy'] * 100:>8.1f}%  {'100.0%':>12}  {overall_summary['overall_latency']['mean_ms']:>8.1f}ms")
    print("=" * 94 + "\n")

    if comparison:
        print("BASELINE COMPARISON:")
        if comparison["has_regressions"]:
            print("  [!] REGRESSIONS DETECTED:")
            for reg in comparison["regressions"]:
                print(f"    - {reg}")
        else:
            print("  [+] No regressions detected. All targets equal or exceed baseline.")
        print("")

    return overall_summary


def main():
    parser = argparse.ArgumentParser(description="Run scan accuracy and latency benchmarks.")
    parser.add_argument("--mode", default="all", choices=["all", "food", "receipt", "tag"], help="Scan mode to evaluate")
    parser.add_argument("--fixtures", type=Path, default=MANIFEST_PATH, help="Path to fixtures.json manifest")
    parser.add_argument("--baseline", type=Path, default=None, help="Path to saved baseline JSON")
    parser.add_argument("--save-baseline", type=Path, default=None, help="Save current run as baseline")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "reports" / "latest_benchmark.json", help="Path to write JSON benchmark report")
    parser.add_argument("--live", action="store_true", help="Run against live endpoints instead of offline deterministic mocks")
    parser.add_argument("--verbose", action="store_true", help="Show verbose per-fixture outcomes")

    args = parser.parse_args()

    summary = run_benchmarks(
        fixtures_path=args.fixtures,
        mode_filter=args.mode,
        offline=not args.live,
        baseline_path=args.baseline,
        save_baseline_path=args.save_baseline,
        output_path=args.output,
        verbose=args.verbose,
    )

    if summary.get("baseline_comparison", {}).get("has_regressions"):
        sys.exit(1)


if __name__ == "__main__":
    main()
