"""Beatitude Engine — values-review service for Agavi AI.

Core surface:
    review(artifact, artifact_type, context=None) -> verdict_record
    issue_seal(verdict_id, approver) -> seal_record
"""

from .core import review
from .errors import BeatitudeError, ConfigError, ReviewerError, SealRefused, StoreError
from .rubric import derive_verdict, load_rubric
from .seal import issue_seal

__all__ = [
    "review",
    "issue_seal",
    "load_rubric",
    "derive_verdict",
    "BeatitudeError",
    "ConfigError",
    "ReviewerError",
    "SealRefused",
    "StoreError",
]
