"""issue_seal(): the only way a "Beatitude Reviewed" seal comes into existence.

Separate from review() on purpose. The rule this enforces in code:
NO VERDICT → NO SEAL. NO HUMAN SIGN-OFF → NO SEAL.

A seal is only issued when the `signoffs` table holds a human 'approve' row for
the verdict_id, and each verdict can carry at most one seal (also enforced by a
UNIQUE constraint in the database).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .errors import SealRefused
from .store import SupabaseStore


def _get_store() -> SupabaseStore:
    return SupabaseStore()


def issue_seal(verdict_id: str, approver: str) -> dict:
    """Issue the seal for a verdict. Refuses unless a human sign-off exists."""
    if not verdict_id or not str(verdict_id).strip():
        raise SealRefused("Refused: no verdict_id given. No verdict, no seal.")
    if not approver or not approver.strip():
        raise SealRefused("Refused: an approver identity is required to issue a seal.")

    store = _get_store()

    verdict = store.get_verdict(verdict_id)
    if verdict is None:
        raise SealRefused(
            f"Refused: no verdict record exists for verdict_id {verdict_id!r}. "
            "No verdict, no seal."
        )

    approvals = store.get_approving_signoffs(verdict_id)
    if not approvals:
        raise SealRefused(
            f"Refused: no human sign-off row (decision='approve') exists in "
            f"`signoffs` for verdict_id {verdict_id!r}. No sign-off, no seal. "
            "Record the human decision first (signoffs: verdict_id, approver, "
            "decision, note)."
        )

    existing = store.get_seal(verdict_id)
    if existing is not None:
        raise SealRefused(
            f"Refused: verdict {verdict_id!r} already carries seal "
            f"{existing.get('seal_id')!r}; a verdict is sealed at most once."
        )

    seal_record = {
        "seal_id": str(uuid.uuid4()),
        "verdict_id": verdict_id,
        "signoff_id": approvals[0]["id"],
        "approver": approver,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.insert_seal(seal_record)
    return seal_record
