#!/usr/bin/env python3
"""Beatitude Engine MCP server.

The primary consumption path for Claude Code, Cowork, OpenClaw, and Grok Build.
Exposes two tools over stdio:

    beatitude_review  — run the values review on one artifact (writes the
                        verdict to the Supabase audit trail, advise-only)
    get_verdict       — read back a stored verdict by id (read-only)

Run:
    python mcp_server/server.py

Client registration (Claude Code):
    claude mcp add beatitude -- python /path/to/mcp_server/server.py

Requires the same environment as the core library (XAI_API_KEY, SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY; ANTHROPIC_API_KEY + OPENAI_API_KEY for council
escalations). Secrets come from the environment only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

# Make the core library importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:  # MCP Python SDK >= 2.0
    from mcp.server.mcpserver import MCPServer
except ImportError:  # MCP Python SDK 1.x (FastMCP)
    from mcp.server.fastmcp import FastMCP as MCPServer

from beatitude_engine import BeatitudeError, review
from beatitude_engine.store import SupabaseStore

mcp = MCPServer("beatitude_mcp")


def _error(exc: Exception) -> str:
    return f"Error: {exc}"


@mcp.tool(
    name="beatitude_review",
    annotations={
        "title": "Beatitude Engine Review",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def beatitude_review(
    artifact: Annotated[str, Field(description=(
        "The full text of the artifact to review (e.g. an outreach email, "
        "website copy, a proposal line, a workflow's customer-facing output)."
    ), min_length=1)],
    artifact_type: Annotated[str, Field(description=(
        "What kind of artifact this is, e.g. 'outreach_email', 'website_copy', "
        "'proposal_line', 'workflow_output', 'internal_note'."
    ), min_length=1)],
    context: Annotated[dict[str, Any] | None, Field(description=(
        "Optional context for the audit trail (e.g. {'client': 'TX Mulching', "
        "'campaign': 'august-follow-up'}). Not scored; stored with the verdict."
    ))] = None,
) -> str:
    """Review one artifact against the Beatitude rubric (advise-only).

    Grok scores the artifact against rubric v1 (eight commitments, 0/1/2 each);
    the verdict is derived from the scores (any 0 -> "Misaligned", any 1 ->
    "Closely Aligned", else "Aligned"). "Closely Aligned" verdicts escalate to a
    Claude/GPT/Grok council whose per-commitment minimum replaces the single
    reviewer's scores. The verdict is written to the Supabase audit trail before
    this tool returns.

    This tool NEVER blocks anything and NEVER issues a seal — sealing requires a
    recorded human sign-off and is a separate step.

    Returns:
        str: JSON verdict record:
        {
            "verdict_id": str,        # UUID — use with get_verdict / sign-off
            "artifact_type": str,
            "scores": {<commitment>: 0|1|2, ... (8 keys)},
            "verdict": "Aligned" | "Closely Aligned" | "Misaligned",
            "rationale": str,
            "suggested_fixes": {<commitment>: str, ...},  # only commitments < 2
            "models_used": [str, ...],  # reviewer + council, if escalated
            "created_at": str           # ISO 8601 UTC
        }
        On failure: "Error: <what went wrong and how to fix it>".
    """
    try:
        record = review(artifact, artifact_type, context)
        return json.dumps(record, indent=2)
    except (BeatitudeError, ValueError) as exc:
        return _error(exc)


@mcp.tool(
    name="get_verdict",
    annotations={
        "title": "Get Beatitude Verdict",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def get_verdict(
    verdict_id: Annotated[str, Field(description=(
        "The verdict UUID returned by beatitude_review."
    ), min_length=1)],
) -> str:
    """Fetch a stored verdict record from the Supabase audit trail (read-only).

    Returns:
        str: JSON of the stored row — the fields returned by beatitude_review
        plus artifact, context, rubric_version, and raw model responses.
        "Error: no verdict found ..." if the id is unknown.
    """
    try:
        row = SupabaseStore().get_verdict(verdict_id)
    except BeatitudeError as exc:
        return _error(exc)
    if row is None:
        return (
            f"Error: no verdict found for verdict_id {verdict_id!r}. "
            "Check the id returned by beatitude_review."
        )
    return json.dumps(row, indent=2)


if __name__ == "__main__":
    mcp.run()
