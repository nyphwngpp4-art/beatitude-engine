"""Adapter wiring the real engine into harness.py.

Run from this directory (or anywhere — the harness puts this file's directory on
sys.path automatically):

    python3 harness.py --reviewer engine:review

review(artifact, artifact_type) calls beatitude_engine.review(), which loads
rubric/rubric.v1.md at runtime, calls Grok in structured-output mode, escalates
"Closely Aligned" verdicts to the Claude/GPT/Grok council, and returns the
verdict record the harness scores. Set BEATITUDE_PERSIST=off to run the eval
without writing 21 eval verdicts into the production audit table.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from beatitude_engine import review  # noqa: E402  (re-exported for --reviewer engine:review)

__all__ = ["review"]
