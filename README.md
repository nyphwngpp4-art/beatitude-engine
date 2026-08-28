# Beatitude Engine

Callable values-review service for Agavi AI. One stateless function reviews an
artifact against the eight public Beatitude Standard commitments and logs every
verdict to an audit trail; a separate, human-gated function issues the
"Beatitude Reviewed" seal.

```
review(artifact, artifact_type, context) -> verdict_record   # advise-only, always logged
issue_seal(verdict_id, approver)         -> seal_record      # refuses without a human sign-off
```

**The contract** lives in [`rubric/rubric.v1.md`](rubric/rubric.v1.md) and is
loaded at runtime, verbatim — never paraphrased into code. Scores are 0/1/2 per
commitment; the verdict is **derived** (any 0 → Misaligned; else any 1 →
Closely Aligned; else Aligned), never judged by a model. Grok is the default
reviewer (structured output). A "Closely Aligned" verdict escalates to a
council — Claude, GPT, and Grok independently — aggregated by **minimum score
per commitment**; council scores replace the single reviewer's and both appear
in `models_used`. Aligned and Misaligned never escalate.

**Policy:** the engine never blocks a pipeline and never auto-issues the seal.
Every verdict is written to Supabase **before** `review()` returns when persist
is on (`BEATITUDE_PERSIST` defaults to on; `off` is the explicit local/eval
skip). The seal exists only via `issue_seal()`, which refuses unless a human
`approve` row exists in `signoffs` for that verdict — no verdict, no seal; no
sign-off, no seal (enforced in code and by FK/UNIQUE constraints).

## Layout

```
rubric/rubric.v1.md          the scoring contract (source of truth, versioned)
eval/                        harness.py, eval-set.v1.jsonl, engine.py adapter (see eval/README.md)
src/beatitude_engine/        core library: review(), issue_seal(), reviewers, store
mcp_server/server.py         MCP server (stdio): beatitude_review, get_verdict
worker/                      Cloudflare Worker: authenticated POST /review
supabase/migrations/         SQL for verdicts / signoffs / seals
tests/                       pytest suite + golden fixtures shared with the Worker
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env         # fill in keys; see comments in that file
```

Secrets are environment-only: `XAI_API_KEY` (required), `ANTHROPIC_API_KEY` +
`OPENAI_API_KEY` (council), `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
(audit trail — Supabase project `beatitude-engine` / `krzagogtzyuoeyhcpuqo`).

## Running each surface

**Core library**

```python
from beatitude_engine import review, issue_seal
record = review("artifact text", "outreach_email", {"client": "TX Mulching"})
seal = issue_seal(record["verdict_id"], "Al Messamore")  # only after a human sign-off row exists
```

Record a sign-off (the human step) with
`beatitude_engine.store.SupabaseStore().record_signoff(verdict_id, approver, "approve", note)`.

**Eval harness** (the correctness gate — see `eval/README.md`)

```bash
cd eval
python3 harness.py --mock                                  # offline pipeline check
BEATITUDE_PERSIST=off ../.venv/bin/python harness.py --reviewer engine:review
BEATITUDE_PERSIST=off ../.venv/bin/python harness.py --reviewer engine:review --update-baseline
```

Gate: accuracy ≥ 80% and ZERO Misaligned-graded-Aligned. `BEATITUDE_PERSIST=off`
keeps the 21 eval verdicts out of the production audit table; drop it if you
want them logged.

**MCP server** (primary path for Claude Code / Cowork / OpenClaw / Grok Build)

```bash
claude mcp add beatitude -- /path/to/.venv/bin/python /path/to/mcp_server/server.py
```

Tools: `beatitude_review(artifact, artifact_type, context)` and read-only
`get_verdict(verdict_id)`. The server needs the same env vars as the library.

**Cloudflare Worker** (same account as the agaviai.com site)

```bash
cd worker
npm test                                   # contract tests vs shared golden fixtures
npx wrangler deploy                        # needs a Cloudflare-authenticated shell
npx wrangler secret put BEATITUDE_AUTH_TOKEN   # + XAI/ANTHROPIC/OPENAI keys, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

curl -X POST https://beatitude-engine.<account>.workers.dev/review \
  -H "Authorization: Bearer $BEATITUDE_AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"artifact": "...", "artifact_type": "website_copy", "context": {}}'
```

The Worker is a faithful JS port of `review()` (a Worker can't run the Python
core); it bundles the **same** `rubric/rubric.v1.md`, and
`worker/test/logic.test.mjs` runs the same golden fixtures as pytest so the two
implementations cannot drift. The Python core is the harness-gated source of
truth.

**Supabase** — migrations live in `supabase/migrations/` and were applied to
project `krzagogtzyuoeyhcpuqo` via the Supabase MCP (`apply_migration`), not by
hand-editing prod. RLS is enabled with no policies on all three tables:
only the service-role key can read or write them.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q       # 23 tests, incl. issue_seal refusal + council min
cd worker && npm test                      # 7 cross-language contract tests
cd eval && python3 harness.py --mock       # harness pipeline only; mock accuracy is not engine quality
```

GitHub Actions (`.github/workflows/offline-gates.yml`) runs those three commands
on every pull request. No API keys required.

## Design decisions worth knowing

- **No silent model fallback.** If a reviewer model fails or refuses, the call
  raises rather than substituting another model — `models_used` in the audit
  trail must name the models that actually judged.
- **Commitment keys are parsed from the rubric headings** (`### N. key — ...`),
  so a rubric revision propagates to prompts, schemas, and validation without
  code changes. Rubric edits must re-pass the harness baseline.
- **Dependencies** (minimum versions in `pyproject.toml`, not a lockfile):
  `anthropic`, `openai` (also used for xAI's OpenAI-compatible API), `httpx`
  (Supabase PostgREST), `mcp` (MCP server), `pytest` (dev). The Worker has
  zero runtime dependencies.
