"""review(): the one stateless entry point of the Beatitude Engine.

Path (per rubric v1):
  1. Grok reviews the artifact against the rubric (structured output).
  2. The verdict is DERIVED from scores — any 0 → Misaligned, else any 1 →
     Closely Aligned, else Aligned. Models never judge the verdict.
  3. "Closely Aligned" escalates to a council (Claude, GPT, Grok, independent);
     the minimum score per commitment across council members replaces the
     single-reviewer scores. Aligned and Misaligned do not escalate.
  4. The verdict is written to the Supabase `verdicts` audit table BEFORE the
     record is returned.

Advise-only: this function never blocks anything and never issues a seal. It
returns and logs — that is all it does to the caller's flow.
"""

from __future__ import annotations

import uuid
import warnings
from datetime import datetime, timezone

from .config import env
from .errors import ConfigError
from .reviewers import ReviewerResult, claude_review, gpt_review, grok_review
from .rubric import VERDICT_CLOSELY, aggregate_min, derive_verdict, load_rubric
from .store import SupabaseStore


def _merge_fixes(keys: tuple[str, ...], scores: dict, results: list[ReviewerResult]) -> dict:
    """One suggested fix per commitment that scored below 2, if any model offered one."""
    fixes = {}
    for key in keys:
        if scores[key] == 2:
            continue
        for result in results:
            fix = result.suggested_fixes.get(key, "").strip()
            if fix:
                fixes[key] = fix
                break
    return fixes


def _get_store() -> SupabaseStore:
    return SupabaseStore()


def review(artifact: str, artifact_type: str, context: dict | None = None) -> dict:
    """Review one artifact. Returns the verdict record; never blocks, never seals.

    The record is persisted to the Supabase `verdicts` table before returning
    (set BEATITUDE_PERSIST=off explicitly to skip persistence in local/eval runs).
    """
    if not artifact or not artifact.strip():
        raise ValueError("artifact must be a non-empty string")
    if not artifact_type or not artifact_type.strip():
        raise ValueError("artifact_type must be a non-empty string")

    rubric = load_rubric()

    initial = grok_review(rubric, artifact, artifact_type, context)
    verdict = derive_verdict(initial.scores, rubric.keys)

    all_results = [initial]
    models_used = [f"{initial.model} (reviewer)"]
    scores = initial.scores
    rationale = initial.rationale

    if verdict == VERDICT_CLOSELY:
        council = [
            claude_review(rubric, artifact, artifact_type, context),
            gpt_review(rubric, artifact, artifact_type, context),
            grok_review(rubric, artifact, artifact_type, context),
        ]
        scores = aggregate_min([m.scores for m in council], rubric.keys)
        verdict = derive_verdict(scores, rubric.keys)
        models_used += [f"{m.model} (council)" for m in council]
        council_notes = "\n".join(f"[council:{m.model}] {m.rationale}" for m in council)
        rationale = f"[reviewer:{initial.model}] {initial.rationale}\n{council_notes}"
        # Council results take precedence for fixes; the initial reviewer backfills.
        all_results = council + [initial]

    record = {
        "verdict_id": str(uuid.uuid4()),
        "artifact_type": artifact_type,
        "scores": scores,
        "verdict": verdict,
        "rationale": rationale,
        "suggested_fixes": _merge_fixes(rubric.keys, scores, all_results),
        "models_used": models_used,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    persist = (env("BEATITUDE_PERSIST", "on") or "on").lower()
    if persist == "off":
        warnings.warn(
            "BEATITUDE_PERSIST=off — verdict NOT written to Supabase. "
            "Only use this for local/eval runs.",
            stacklevel=2,
        )
    else:
        if not SupabaseStore.configured():
            raise ConfigError(
                "Supabase is not configured, so the verdict cannot be logged. Set "
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or set "
                "BEATITUDE_PERSIST=off to explicitly skip persistence in local runs."
            )
        _get_store().insert_verdict(
            {
                **record,
                "artifact": artifact,
                "context": context or {},
                "rubric_version": rubric.version,
                "raw_responses": [r.raw_response for r in all_results],
            }
        )

    return record
