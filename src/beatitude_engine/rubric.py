"""Runtime loading of the rubric.

The rubric file (rubric/rubric.v1.md) is the scoring contract. It is loaded and
sent to reviewers verbatim at call time — the code never paraphrases it. The
commitment keys are parsed out of the rubric headings, so a rubric revision
propagates without code changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT, env
from .errors import ConfigError

DEFAULT_RUBRIC_PATH = REPO_ROOT / "rubric" / "rubric.v1.md"

# Matches commitment headings like: "### 1. honest_scoping  — ..."
_COMMITMENT_HEADING = re.compile(r"^###\s+\d+\.\s+([a-z0-9_]+)\b", re.MULTILINE)
_VERSION_LINE = re.compile(r"^Version:\s*(\S+)", re.MULTILINE)

VERDICT_ALIGNED = "Aligned"
VERDICT_CLOSELY = "Closely Aligned"
VERDICT_MISALIGNED = "Misaligned"
VALID_SCORES = (0, 1, 2)


@dataclass(frozen=True)
class Rubric:
    text: str
    keys: tuple[str, ...]
    version: str
    path: str


def rubric_path() -> Path:
    override = env("BEATITUDE_RUBRIC_PATH")
    return Path(override) if override else DEFAULT_RUBRIC_PATH


def load_rubric(path: Path | None = None) -> Rubric:
    path = path or rubric_path()
    if not path.exists():
        raise ConfigError(
            f"Rubric not found at {path}. Set BEATITUDE_RUBRIC_PATH or place the "
            "rubric at rubric/rubric.v1.md."
        )
    text = path.read_text()
    keys = tuple(_COMMITMENT_HEADING.findall(text))
    if not keys:
        raise ConfigError(
            f"No commitment headings ('### N. key — ...') found in rubric at {path}; "
            "cannot build the scoring schema."
        )
    if len(keys) != len(set(keys)):
        raise ConfigError(f"Duplicate commitment keys in rubric at {path}.")
    version_match = _VERSION_LINE.search(text)
    version = version_match.group(1) if version_match else "unknown"
    return Rubric(text=text, keys=keys, version=version, path=str(path))


def derive_verdict(scores: dict, keys: tuple[str, ...]) -> str:
    """Derive the verdict from per-commitment scores per the rubric.

    The verdict is never judged separately by a model — any model-claimed
    verdict is discarded and this derivation is authoritative.
    """
    missing = [k for k in keys if k not in scores]
    if missing:
        raise ValueError(f"Scores missing commitments: {missing}")
    vals = [scores[k] for k in keys]
    bad = [v for v in vals if v not in VALID_SCORES]
    if bad:
        raise ValueError(f"Scores must be 0, 1, or 2; got {bad}")
    if any(v == 0 for v in vals):
        return VERDICT_MISALIGNED
    if any(v == 1 for v in vals):
        return VERDICT_CLOSELY
    return VERDICT_ALIGNED


def aggregate_min(score_sets: list[dict], keys: tuple[str, ...]) -> dict:
    """Council aggregation: minimum score per commitment (conservative)."""
    if not score_sets:
        raise ValueError("aggregate_min needs at least one score set")
    return {k: min(s[k] for s in score_sets) for k in keys}
