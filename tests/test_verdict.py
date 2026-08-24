"""Verdict derivation and council aggregation against the golden fixtures.

The same fixtures run against the Cloudflare Worker port (worker/test/), so the
two implementations cannot drift.
"""

import pytest

from beatitude_engine.rubric import aggregate_min, derive_verdict


def test_derive_cases(golden, commitment_keys):
    for case in golden["derive_cases"]:
        assert derive_verdict(case["scores"], commitment_keys) == case["expected"], case["name"]


def test_aggregate_cases(golden, commitment_keys):
    for case in golden["aggregate_cases"]:
        result = aggregate_min(case["inputs"], commitment_keys)
        assert result == case["expected"], case["name"]
        assert derive_verdict(result, commitment_keys) == case["expected_verdict"], case["name"]


def test_missing_commitment_rejected(commitment_keys):
    scores = {k: 2 for k in commitment_keys[:-1]}
    with pytest.raises(ValueError, match="missing"):
        derive_verdict(scores, commitment_keys)


def test_out_of_range_score_rejected(commitment_keys):
    scores = {k: 2 for k in commitment_keys}
    scores[commitment_keys[0]] = 3
    with pytest.raises(ValueError, match="0, 1, or 2"):
        derive_verdict(scores, commitment_keys)


def test_aggregate_min_requires_input(commitment_keys):
    with pytest.raises(ValueError):
        aggregate_min([], commitment_keys)
