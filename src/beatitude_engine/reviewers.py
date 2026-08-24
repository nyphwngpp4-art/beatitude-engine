"""Model reviewer clients.

Every reviewer receives the identical prompt (the rubric verbatim plus the
artifact) and must return typed JSON matching the schema built from the rubric's
commitment keys — structured-output / function-calling mode, never prose parsing.

- Grok (xAI) is the default single reviewer; OpenAI-compatible API with a strict
  JSON-schema response_format.
- Claude and GPT join Grok on the council for "Closely Aligned" escalations.
  Claude uses the Anthropic SDK's output_config JSON-schema constraint. No
  silent model fallback is enabled anywhere: a values verdict must come from
  the model recorded in models_used, so failures raise instead of substituting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import (
    ANTHROPIC_MODEL_DEFAULT,
    GROK_MODEL_DEFAULT,
    OPENAI_MODEL_DEFAULT,
    XAI_BASE_URL_DEFAULT,
    env,
    require_env,
)
from .errors import ReviewerError
from .rubric import VALID_SCORES, Rubric

SYSTEM_PROMPT = """You are the reviewer inside the Beatitude Engine, Agavi AI's \
values-review service. You score one artifact against the rubric below. The \
rubric is the entire scoring contract: apply it exactly as written, commitment \
by commitment.

Rules:
- Score every commitment with an integer 0, 1, or 2 as defined in the rubric.
- Judge only what the artifact itself says or does. Do not invent context.
- Be conservative: if an artifact plainly does what a commitment forbids, that
  commitment scores 0 even if the rest of the artifact is excellent.
- Do not compute or output an overall verdict; verdicts are derived from your
  scores by the engine, not judged by you.
- rationale: 2-5 sentences naming the specific language that drove any score
  below 2 (or confirming a clean pass).
- suggested_fixes: for each commitment scoring below 2, one concrete rewrite or
  change that would raise it; use an empty string for commitments scoring 2.

THE RUBRIC (verbatim):

"""


def build_score_schema(keys: tuple[str, ...]) -> dict:
    """JSON schema for reviewer output, built from the rubric's commitment keys.

    Kept strict-mode compatible for every provider: all properties required,
    additionalProperties false, no type unions (empty string means "no fix").
    """
    score_props = {k: {"type": "integer", "enum": list(VALID_SCORES)} for k in keys}
    fix_props = {k: {"type": "string"} for k in keys}
    return {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": score_props,
                "required": list(keys),
                "additionalProperties": False,
            },
            "rationale": {"type": "string"},
            "suggested_fixes": {
                "type": "object",
                "properties": fix_props,
                "required": list(keys),
                "additionalProperties": False,
            },
        },
        "required": ["scores", "rationale", "suggested_fixes"],
        "additionalProperties": False,
    }


def build_user_payload(artifact: str, artifact_type: str, context: dict | None) -> str:
    return json.dumps(
        {
            "artifact_type": artifact_type,
            "context": context or {},
            "artifact": artifact,
        },
        ensure_ascii=False,
        indent=2,
    )


@dataclass
class ReviewerResult:
    model: str
    scores: dict
    rationale: str
    suggested_fixes: dict
    raw_response: Any


def _validate_output(data: dict, rubric: Rubric, model: str) -> None:
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise ReviewerError(f"{model} returned no 'scores' object.")
    missing = [k for k in rubric.keys if k not in scores]
    if missing:
        raise ReviewerError(f"{model} scores missing commitments: {missing}")
    bad = {k: v for k, v in scores.items() if v not in VALID_SCORES}
    if bad:
        raise ReviewerError(f"{model} returned out-of-range scores: {bad}")


def _result(data: dict, rubric: Rubric, model: str, raw: Any) -> ReviewerResult:
    _validate_output(data, rubric, model)
    fixes = data.get("suggested_fixes") or {}
    return ReviewerResult(
        model=model,
        scores={k: int(data["scores"][k]) for k in rubric.keys},
        rationale=str(data.get("rationale", "")),
        suggested_fixes={k: v for k, v in fixes.items() if isinstance(v, str) and v.strip()},
        raw_response=raw,
    )


def _openai_compatible_review(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    rubric: Rubric,
    artifact: str,
    artifact_type: str,
    context: dict | None,
) -> ReviewerResult:
    """Shared path for xAI (Grok) and OpenAI (GPT): strict JSON-schema output."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + rubric.text},
                {"role": "user", "content": build_user_payload(artifact, artifact_type, context)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "beatitude_review",
                    "strict": True,
                    "schema": build_score_schema(rubric.keys),
                },
            },
        )
    except Exception as exc:  # surface provider errors with the model name attached
        raise ReviewerError(f"{model} call failed: {exc}") from exc
    content = response.choices[0].message.content
    if not content:
        raise ReviewerError(f"{model} returned an empty response.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ReviewerError(f"{model} returned non-JSON output despite schema mode.") from exc
    return _result(data, rubric, model, response.model_dump())


def grok_review(rubric: Rubric, artifact: str, artifact_type: str, context: dict | None) -> ReviewerResult:
    return _openai_compatible_review(
        api_key=require_env("XAI_API_KEY", "Set it to your xAI (Grok) API key."),
        base_url=env("XAI_BASE_URL", XAI_BASE_URL_DEFAULT),
        model=env("GROK_MODEL", GROK_MODEL_DEFAULT),
        rubric=rubric,
        artifact=artifact,
        artifact_type=artifact_type,
        context=context,
    )


def gpt_review(rubric: Rubric, artifact: str, artifact_type: str, context: dict | None) -> ReviewerResult:
    return _openai_compatible_review(
        api_key=require_env("OPENAI_API_KEY", "Set it to your OpenAI API key."),
        base_url=env("OPENAI_BASE_URL"),
        model=env("OPENAI_MODEL", OPENAI_MODEL_DEFAULT),
        rubric=rubric,
        artifact=artifact,
        artifact_type=artifact_type,
        context=context,
    )


def claude_review(rubric: Rubric, artifact: str, artifact_type: str, context: dict | None) -> ReviewerResult:
    import anthropic

    model = env("ANTHROPIC_MODEL", ANTHROPIC_MODEL_DEFAULT)
    client = anthropic.Anthropic(
        api_key=require_env("ANTHROPIC_API_KEY", "Set it to your Anthropic API key.")
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT + rubric.text,
            messages=[
                {"role": "user", "content": build_user_payload(artifact, artifact_type, context)}
            ],
            output_config={
                "format": {"type": "json_schema", "schema": build_score_schema(rubric.keys)}
            },
        )
    except Exception as exc:
        raise ReviewerError(f"{model} call failed: {exc}") from exc
    if response.stop_reason == "refusal":
        raise ReviewerError(
            f"{model} declined to review this artifact (stop_reason=refusal). "
            "A human should review it directly."
        )
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise ReviewerError(f"{model} returned no text content.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewerError(f"{model} returned non-JSON output despite schema mode.") from exc
    return _result(data, rubric, model, response.model_dump())
