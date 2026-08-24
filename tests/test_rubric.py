"""The rubric file is the contract: loader output must match the harness."""

import importlib.util

from conftest import REPO_ROOT

from beatitude_engine.rubric import load_rubric
from beatitude_engine.reviewers import SYSTEM_PROMPT, build_score_schema


def _load_harness_module():
    spec = importlib.util.spec_from_file_location("harness", REPO_ROOT / "eval" / "harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rubric_keys_match_harness_commitments():
    rubric = load_rubric()
    harness = _load_harness_module()
    assert list(rubric.keys) == harness.COMMITMENTS


def test_rubric_loaded_verbatim_into_prompt():
    rubric = load_rubric()
    prompt = SYSTEM_PROMPT + rubric.text
    # The full rubric text ships to the reviewer unmodified — no paraphrase.
    assert rubric.text in prompt
    assert "### 1. honest_scoping" in prompt


def test_rubric_version_parsed():
    assert load_rubric().version == "1.0"


def test_score_schema_covers_every_commitment():
    rubric = load_rubric()
    schema = build_score_schema(rubric.keys)
    scores = schema["properties"]["scores"]
    assert set(scores["properties"]) == set(rubric.keys)
    assert set(scores["required"]) == set(rubric.keys)
    assert scores["additionalProperties"] is False
    for prop in scores["properties"].values():
        assert prop["enum"] == [0, 1, 2]
