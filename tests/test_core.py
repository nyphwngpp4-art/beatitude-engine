"""review() pipeline behavior with stubbed reviewers and store."""

import pytest

import beatitude_engine.core as core
from beatitude_engine.errors import ConfigError, StoreError
from beatitude_engine.reviewers import ReviewerResult


def _scores(keys, **overrides):
    scores = {k: 2 for k in keys}
    scores.update(overrides)
    return scores


def _stub_result(model, scores, rationale="stub rationale", fixes=None):
    return ReviewerResult(
        model=model,
        scores=scores,
        rationale=rationale,
        suggested_fixes=fixes or {},
        raw_response={"stub": model},
    )


class FakeStore:
    def __init__(self):
        self.inserted = []

    def insert_verdict(self, row):
        self.inserted.append(row)
        return row


@pytest.fixture
def wired(monkeypatch, commitment_keys):
    """Wire stub reviewers + fake store into core; returns a config dict tests mutate."""
    cfg = {
        "grok": _stub_result("stub-grok", _scores(commitment_keys)),
        "claude": _stub_result("stub-claude", _scores(commitment_keys)),
        "gpt": _stub_result("stub-gpt", _scores(commitment_keys)),
        "council_called": [],
        "store": FakeStore(),
    }

    monkeypatch.setattr(core, "grok_review", lambda *a, **k: cfg["grok"])

    def _claude(*a, **k):
        cfg["council_called"].append("claude")
        return cfg["claude"]

    def _gpt(*a, **k):
        cfg["council_called"].append("gpt")
        return cfg["gpt"]

    monkeypatch.setattr(core, "claude_review", _claude)
    monkeypatch.setattr(core, "gpt_review", _gpt)
    monkeypatch.setattr(core, "_get_store", lambda: cfg["store"])
    monkeypatch.setattr(core.SupabaseStore, "configured", staticmethod(lambda: True))
    monkeypatch.delenv("BEATITUDE_PERSIST", raising=False)
    return cfg


def test_aligned_verdict_no_council(wired, commitment_keys):
    record = core.review("A clean artifact.", "website_copy")
    assert record["verdict"] == "Aligned"
    assert wired["council_called"] == []
    assert record["models_used"] == ["stub-grok (reviewer)"]
    assert record["scores"] == {k: 2 for k in commitment_keys}
    assert record["suggested_fixes"] == {}


def test_misaligned_verdict_no_council(wired, commitment_keys):
    wired["grok"] = _stub_result("stub-grok", _scores(commitment_keys, no_hype=0))
    record = core.review("Guaranteed 10x!", "website_copy")
    assert record["verdict"] == "Misaligned"
    assert wired["council_called"] == []


def test_closely_aligned_escalates_and_council_min_replaces_scores(wired, commitment_keys):
    wired["grok"] = _stub_result("stub-grok", _scores(commitment_keys, no_hype=1))
    wired["claude"] = _stub_result(
        "stub-claude",
        _scores(commitment_keys, no_manipulation=0),
        fixes={"no_manipulation": "Drop the countdown timer."},
    )
    wired["gpt"] = _stub_result("stub-gpt", _scores(commitment_keys, transparency=1))

    record = core.review("Borderline artifact.", "proposal_line")

    assert sorted(wired["council_called"]) == ["claude", "gpt"]
    # Council minimum per commitment replaced the single-reviewer scores...
    assert record["scores"]["no_manipulation"] == 0
    assert record["scores"]["transparency"] == 1
    # ...including the council's own Grok pass (stubbed here to no_hype=1).
    assert record["scores"]["no_hype"] == 1
    # Verdict re-derived from council scores: the council found a violation.
    assert record["verdict"] == "Misaligned"
    # Both the initial reviewer and all council members are retained.
    assert record["models_used"] == [
        "stub-grok (reviewer)",
        "stub-claude (council)",
        "stub-gpt (council)",
        "stub-grok (council)",
    ]
    assert record["suggested_fixes"]["no_manipulation"] == "Drop the countdown timer."


def test_verdict_persisted_before_return(wired):
    record = core.review("A clean artifact.", "website_copy", context={"client": "TX Mulching"})
    assert len(wired["store"].inserted) == 1
    row = wired["store"].inserted[0]
    assert row["verdict_id"] == record["verdict_id"]
    assert row["artifact"] == "A clean artifact."
    assert row["context"] == {"client": "TX Mulching"}
    assert row["rubric_version"] == "1.0"
    assert row["raw_responses"] == [{"stub": "stub-grok"}]


def test_store_failure_propagates(wired):
    def _boom(row):
        raise StoreError("insert failed")

    wired["store"].insert_verdict = _boom
    with pytest.raises(StoreError):
        core.review("A clean artifact.", "website_copy")


def test_persist_off_skips_store(wired, monkeypatch):
    monkeypatch.setenv("BEATITUDE_PERSIST", "off")
    with pytest.warns(UserWarning, match="NOT written"):
        record = core.review("A clean artifact.", "website_copy")
    assert record["verdict"] == "Aligned"
    assert wired["store"].inserted == []


def test_unconfigured_store_raises(wired, monkeypatch):
    monkeypatch.setattr(core.SupabaseStore, "configured", staticmethod(lambda: False))
    with pytest.raises(ConfigError, match="Supabase is not configured"):
        core.review("A clean artifact.", "website_copy")


def test_empty_artifact_rejected(wired):
    with pytest.raises(ValueError):
        core.review("   ", "website_copy")
    with pytest.raises(ValueError):
        core.review("artifact", "")
