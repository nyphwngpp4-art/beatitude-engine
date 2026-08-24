import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def golden():
    return json.loads((REPO_ROOT / "tests" / "fixtures" / "golden.json").read_text())


@pytest.fixture(scope="session")
def commitment_keys(golden):
    return tuple(golden["keys"])
