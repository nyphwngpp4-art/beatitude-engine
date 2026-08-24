"""issue_seal() enforcement: no verdict -> no seal; no sign-off -> no seal.

This is the rule the whole service exists to keep honest, enforced in code (and
again by FK/UNIQUE constraints in the database).
"""

import pytest

import beatitude_engine.seal as seal_module
from beatitude_engine.errors import SealRefused
from beatitude_engine.seal import issue_seal


class FakeStore:
    def __init__(self):
        self.verdicts = {}
        self.signoffs = []
        self.seals = {}

    def get_verdict(self, verdict_id):
        return self.verdicts.get(verdict_id)

    def get_approving_signoffs(self, verdict_id):
        return [
            s for s in self.signoffs
            if s["verdict_id"] == verdict_id and s["decision"] == "approve"
        ]

    def get_seal(self, verdict_id):
        return self.seals.get(verdict_id)

    def insert_seal(self, row):
        self.seals[row["verdict_id"]] = row
        return row


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(seal_module, "_get_store", lambda: fake)
    return fake


def test_refuses_when_no_verdict_exists(store):
    with pytest.raises(SealRefused, match="No verdict, no seal"):
        issue_seal("v-does-not-exist", "Al Messamore")
    assert store.seals == {}


def test_refuses_verdict_with_no_signoff_row(store):
    """The required test: a verdict alone must NOT be sealable."""
    store.verdicts["v-1"] = {"verdict_id": "v-1", "verdict": "Aligned"}
    with pytest.raises(SealRefused, match="No sign-off, no seal"):
        issue_seal("v-1", "Al Messamore")
    assert store.seals == {}


def test_refuses_when_only_signoff_is_a_rejection(store):
    store.verdicts["v-2"] = {"verdict_id": "v-2", "verdict": "Closely Aligned"}
    store.signoffs.append(
        {"id": "s-1", "verdict_id": "v-2", "approver": "Al", "decision": "reject"}
    )
    with pytest.raises(SealRefused, match="No sign-off, no seal"):
        issue_seal("v-2", "Al Messamore")


def test_issues_seal_with_verdict_and_approval(store):
    store.verdicts["v-3"] = {"verdict_id": "v-3", "verdict": "Aligned"}
    store.signoffs.append(
        {"id": "s-2", "verdict_id": "v-3", "approver": "Al", "decision": "approve"}
    )
    seal = issue_seal("v-3", "Al Messamore")
    # The seal record points back at its verdict and the human sign-off.
    assert seal["verdict_id"] == "v-3"
    assert seal["signoff_id"] == "s-2"
    assert seal["approver"] == "Al Messamore"
    assert store.seals["v-3"] == seal


def test_refuses_second_seal_for_same_verdict(store):
    store.verdicts["v-4"] = {"verdict_id": "v-4", "verdict": "Aligned"}
    store.signoffs.append(
        {"id": "s-3", "verdict_id": "v-4", "approver": "Al", "decision": "approve"}
    )
    issue_seal("v-4", "Al Messamore")
    with pytest.raises(SealRefused, match="already carries seal"):
        issue_seal("v-4", "Al Messamore")


def test_refuses_blank_inputs(store):
    with pytest.raises(SealRefused):
        issue_seal("", "Al Messamore")
    with pytest.raises(SealRefused):
        issue_seal("v-5", "  ")
