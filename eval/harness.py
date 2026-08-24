#!/usr/bin/env python3
"""
Beatitude Engine eval harness.

Runs the labeled eval set through a reviewer and reports how well the reviewer
matches the ground-truth labels. Designed to run offline against a built-in mock
reviewer so you can see the whole pipeline before wiring Grok, then swap the mock
for the real engine by pointing --reviewer at your module.

Usage:
    python harness.py --mock                      # offline, uses the stub reviewer
    python harness.py --reviewer engine:review    # real: calls engine.review(artifact, context)
    python harness.py --mock --baseline baseline.json --update-baseline

The reviewer contract:
    review(artifact: str, artifact_type: str) -> dict with keys:
        scores:  {commitment_key: int in {0,1,2}}  for all 8 commitments
        verdict: "Aligned" | "Closely Aligned" | "Misaligned"   (optional; derived if absent)
        rationale: str (optional)

Exit code is nonzero if the run fails the gate (see THRESHOLDS), so this can sit
in CI or a pre-deploy hook for the rubric itself.
"""

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

COMMITMENTS = [
    "honest_scoping",
    "human_impact_honesty",
    "no_hype",
    "build_integrity",
    "dignified_rejection",
    "transparency",
    "no_manipulation",
    "standard_over_profit",
]

VERDICTS = ["Aligned", "Closely Aligned", "Misaligned"]

# Gate thresholds. The false-negative that matters most is calling something
# Aligned when it was actually Misaligned -- that is the error that would put a
# bad artifact under the seal. We fail the run outright if any of those occur.
THRESHOLDS = {
    "min_verdict_accuracy": 0.80,
    "max_dangerous_false_negatives": 0,  # expected Misaligned graded Aligned
}


def derive_verdict(scores: dict) -> str:
    vals = [scores[k] for k in COMMITMENTS]
    if any(v == 0 for v in vals):
        return "Misaligned"
    if any(v == 1 for v in vals):
        return "Closely Aligned"
    return "Aligned"


def mock_review(artifact: str, artifact_type: str) -> dict:
    """Deterministic keyword stub standing in for the Grok call.

    Crude on purpose -- it exists so the harness produces a real report offline.
    It is NOT the rubric. Replace with the real engine before trusting results.
    """
    text = artifact.lower()
    scores = {k: 2 for k in COMMITMENTS}

    def flag(key, level, *needles):
        if any(n in text for n in needles):
            scores[key] = min(scores[key], level)

    flag("honest_scoping", 0, "absolutely need", "waste of money", "you'll fail")
    flag("honest_scoping", 1, "go straight to", "bigger scope")
    flag("human_impact_honesty", 0, "quietly replace", "no need to raise", "efficiency gains")
    flag("no_hype", 0, "flawless", "10x your revenue", "guaranteed", "never makes mistakes")
    flag("no_hype", 1, "transform", "outperforms")
    flag("build_integrity", 0, "ship it as-is", "they'll never test", "never test those")
    flag("dignified_rejection", 0, "do not contact us again", "don't meet our criteria")
    flag("dignified_rejection", 1, "good luck")
    flag("transparency", 0, "do not highlight", "small print", "hidden below", "pre-unchecked")
    flag("no_manipulation", 0, "only 3 spots", "countdown", "resets every week", "expires in 10 minutes", "pressure them")
    flag("no_manipulation", 1, "slots left", "grab time this week", "hate for you to wait")
    flag("standard_over_profit", 0, "not put it in writing", "grey-area", "scrape a competitor")

    return {"scores": scores, "verdict": derive_verdict(scores)}


def load_reviewer(spec: str):
    """spec is 'module:function'."""
    mod_name, func_name = spec.split(":")
    mod = importlib.import_module(mod_name)
    return getattr(mod, func_name)


def load_eval_set(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def run(reviewer, rows):
    results = []
    for row in rows:
        out = reviewer(row["content"], row["artifact_type"])
        verdict = out.get("verdict") or derive_verdict(out["scores"])
        got_flags = [k for k, v in out["scores"].items() if v == 0]
        results.append(
            {
                "id": row["id"],
                "expected_verdict": row["expected_verdict"],
                "got_verdict": verdict,
                "expected_flags": set(row.get("expected_flags", [])),
                "got_flags": set(got_flags),
            }
        )
    return results


def report(results):
    n = len(results)
    correct = sum(r["expected_verdict"] == r["got_verdict"] for r in results)
    acc = correct / n if n else 0.0

    # Confusion matrix: rows expected, cols got
    cm = Counter()
    for r in results:
        cm[(r["expected_verdict"], r["got_verdict"])] += 1

    dangerous_fn = [
        r for r in results
        if r["expected_verdict"] == "Misaligned" and r["got_verdict"] == "Aligned"
    ]

    # Flag-level precision/recall over the "which commitments were violated" set
    tp = fp = fn = 0
    for r in results:
        tp += len(r["expected_flags"] & r["got_flags"])
        fp += len(r["got_flags"] - r["expected_flags"])
        fn += len(r["expected_flags"] - r["got_flags"])
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    print(f"\nBeatitude Engine eval — {n} examples")
    print(f"Verdict accuracy: {acc:.0%}  ({correct}/{n})")
    print(f"Flag precision: {precision:.0%}   Flag recall: {recall:.0%}")

    print("\nConfusion matrix (rows=expected, cols=got):")
    header = "                 " + "".join(f"{v[:8]:>10}" for v in VERDICTS)
    print(header)
    for exp in VERDICTS:
        rowstr = f"{exp:>16} " + "".join(f"{cm[(exp, got)]:>10}" for got in VERDICTS)
        print(rowstr)

    if dangerous_fn:
        print("\n!! DANGEROUS false negatives (Misaligned graded Aligned) -- these would")
        print("   put a bad artifact under the seal:")
        for r in dangerous_fn:
            print(f"     - {r['id']}")

    per_wrong = [r for r in results if r["expected_verdict"] != r["got_verdict"]]
    if per_wrong:
        print("\nVerdict mismatches:")
        for r in per_wrong:
            print(f"  {r['id']}: expected {r['expected_verdict']!r}, got {r['got_verdict']!r}")

    return {
        "n": n,
        "verdict_accuracy": acc,
        "flag_precision": precision,
        "flag_recall": recall,
        "dangerous_false_negatives": [r["id"] for r in dangerous_fn],
    }


def gate(summary):
    ok = True
    if summary["verdict_accuracy"] < THRESHOLDS["min_verdict_accuracy"]:
        print(f"\nGATE FAIL: accuracy {summary['verdict_accuracy']:.0%} < "
              f"{THRESHOLDS['min_verdict_accuracy']:.0%}")
        ok = False
    if len(summary["dangerous_false_negatives"]) > THRESHOLDS["max_dangerous_false_negatives"]:
        print("\nGATE FAIL: dangerous false negatives present (must be zero)")
        ok = False
    if ok:
        print("\nGATE PASS")
    return ok


def compare_baseline(summary, baseline_path: Path):
    if not baseline_path.exists():
        print(f"\n(no baseline at {baseline_path}; skipping regression check)")
        return True
    base = json.loads(baseline_path.read_text())
    ok = True
    if summary["verdict_accuracy"] + 1e-9 < base["verdict_accuracy"]:
        print(f"\nREGRESSION: accuracy dropped {base['verdict_accuracy']:.0%} -> "
              f"{summary['verdict_accuracy']:.0%}")
        ok = False
    new_fn = set(summary["dangerous_false_negatives"]) - set(base["dangerous_false_negatives"])
    if new_fn:
        print(f"\nREGRESSION: new dangerous false negatives: {sorted(new_fn)}")
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", default="eval-set.v1.jsonl")
    ap.add_argument("--reviewer", help="module:function implementing review(artifact, artifact_type)")
    ap.add_argument("--mock", action="store_true", help="use the built-in stub reviewer")
    ap.add_argument("--baseline", default="baseline.json")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    if not args.mock and not args.reviewer:
        ap.error("pass --mock or --reviewer module:function")

    reviewer = mock_review if args.mock else load_reviewer(args.reviewer)
    rows = load_eval_set(Path(args.eval_set))
    results = run(reviewer, rows)
    summary = report(results)

    baseline_path = Path(args.baseline)
    reg_ok = compare_baseline(summary, baseline_path)
    gate_ok = gate(summary)

    if args.update_baseline:
        baseline_path.write_text(json.dumps(summary, indent=2))
        print(f"\nbaseline written to {baseline_path}")

    sys.exit(0 if (gate_ok and reg_ok) else 1)


if __name__ == "__main__":
    main()
