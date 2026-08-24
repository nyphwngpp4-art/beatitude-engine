"""Supabase persistence via PostgREST.

Uses plain HTTPS against the project's REST endpoint with the service-role key
(server-side only — never ship that key to a browser). Kept dependency-light on
purpose: httpx instead of the supabase client library.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import env
from .errors import ConfigError, StoreError

_TIMEOUT = 30.0


class SupabaseStore:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or env("SUPABASE_URL") or "").rstrip("/")
        self.key = key or env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_KEY")
        if not self.url or not self.key:
            raise ConfigError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY (Project Settings → API Keys)."
            )

    @staticmethod
    def configured() -> bool:
        return bool(env("SUPABASE_URL") and (env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_KEY")))

    def _headers(self) -> dict:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _request(self, method: str, table: str, *, params: dict | None = None, json_body: Any = None) -> list:
        try:
            response = httpx.request(
                method,
                f"{self.url}/rest/v1/{table}",
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise StoreError(f"Supabase request to '{table}' failed: {exc}") from exc
        if response.status_code >= 400:
            raise StoreError(
                f"Supabase {method} {table} returned {response.status_code}: {response.text[:500]}"
            )
        return response.json() if response.text else []

    # -- verdicts ---------------------------------------------------------

    def insert_verdict(self, row: dict) -> dict:
        return self._request("POST", "verdicts", json_body=row)[0]

    def get_verdict(self, verdict_id: str) -> dict | None:
        rows = self._request("GET", "verdicts", params={"verdict_id": f"eq.{verdict_id}"})
        return rows[0] if rows else None

    # -- signoffs ---------------------------------------------------------

    def record_signoff(self, verdict_id: str, approver: str, decision: str, note: str = "") -> dict:
        if decision not in ("approve", "reject"):
            raise StoreError("Sign-off decision must be 'approve' or 'reject'.")
        return self._request(
            "POST",
            "signoffs",
            json_body={
                "verdict_id": verdict_id,
                "approver": approver,
                "decision": decision,
                "note": note,
            },
        )[0]

    def get_approving_signoffs(self, verdict_id: str) -> list:
        return self._request(
            "GET",
            "signoffs",
            params={
                "verdict_id": f"eq.{verdict_id}",
                "decision": "eq.approve",
                "order": "created_at.desc",
            },
        )

    # -- seals ------------------------------------------------------------

    def insert_seal(self, row: dict) -> dict:
        return self._request("POST", "seals", json_body=row)[0]

    def get_seal(self, verdict_id: str) -> dict | None:
        rows = self._request("GET", "seals", params={"verdict_id": f"eq.{verdict_id}"})
        return rows[0] if rows else None
