# Beatitude Engine — Eval Harness

This is the prerequisite for everything else. Before the engine gates anything or
issues a seal, you need to know it agrees with your judgment. This package lets
you measure that and catch regressions whenever you change the rubric or the model.

## Files

- `rubric.v1.md`   — the scoring contract. The eight public commitments, scored
                     0/1/2 each, with verdict thresholds and the council-escalation
                     band. Versioned; treat it like code.
- `eval-set.v1.jsonl` — 21 synthetic labeled examples (aligned, misaligned,
                     borderline) across Agavi artifact types. Generated for you to
                     review and correct. This is the ground truth the engine is
                     measured against.
- `harness.py`     — the runner. Sends the eval set through a reviewer, compares to
                     labels, prints accuracy + a confusion matrix + flag
                     precision/recall, and gates on the one error that matters most:
                     an artifact that was Misaligned getting graded Aligned (a bad
                     artifact slipping under the seal).
- `baseline.json`  — written by `--update-baseline`; the harness fails if a later
                     run regresses against it.

## Run it

Offline, against the built-in stub reviewer (no API needed):

    python3 harness.py --mock

The stub is deliberately crude keyword matching — it exists to prove the pipeline
end to end. Its 100% score means nothing about the real engine; it means the
harness works. Replace it.

Against the real engine, once you've built it:

    python3 harness.py --reviewer engine:review

where `engine.review(artifact, artifact_type)` calls Grok with `rubric.v1.md` and
returns `{scores, verdict, rationale}`. Set and freeze a baseline:

    python3 harness.py --reviewer engine:review --update-baseline

Then every rubric edit or model swap re-runs against that baseline and fails on
regression. That failure is the thing standing between you and a public seal that
lies.

## First job: review the synthetic set

You asked for synthetic examples to review. Do that before trusting any number:

1. Read `eval-set.v1.jsonl`. For each row, decide whether YOU agree with
   `expected_verdict` and `expected_flags`. Where you disagree, the label is wrong,
   not you — fix it.
2. Add any real misalignment you've seen in the wild that isn't represented.
3. As real Agavi outputs accumulate, replace synthetic rows with real ones. The
   file format is stable; the harness doesn't care about the source. Bump to
   `eval-set.v2.jsonl` when the set changes materially and keep the old one.

Borderline examples (`border-*`) are the most valuable and the hardest to label.
They are what exercises the council-escalation band. Spend your review time there.

## The rule the whole thing exists to enforce

The engine returns a verdict. A verdict plus a recorded human sign-off authorizes
the "Beatitude Reviewed" seal for one artifact. No verdict, no seal. No sign-off,
no seal. The seal is a claim about a specific artifact having passed, backed by a
timestamped record you can produce on demand. That record is what makes the public
claim honest instead of decorative.
