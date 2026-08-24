// Beatitude Engine — Cloudflare Worker endpoint.
//
// Authenticated HTTPS wrapper around review(): POST /review with
// Authorization: Bearer <BEATITUDE_AUTH_TOKEN> and body
//   { "artifact": "...", "artifact_type": "...", "context": { ... } }
// returns the verdict record JSON. Advise-only: it reviews and logs; it never
// blocks a pipeline and never issues a seal.
//
// The rubric is bundled from the same rubric/rubric.v1.md file the Python core
// loads — one contract, two runtimes. Verdict derivation and council
// aggregation are covered by the shared golden fixtures (worker/test/).
//
// Secrets (wrangler secret put ...): BEATITUDE_AUTH_TOKEN, XAI_API_KEY,
// ANTHROPIC_API_KEY, OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
// Optional vars: GROK_MODEL, ANTHROPIC_MODEL, OPENAI_MODEL.

import rubricText from "../../rubric/rubric.v1.md";
import {
  SYSTEM_PROMPT,
  VERDICT_CLOSELY,
  aggregateMin,
  buildScoreSchema,
  buildUserPayload,
  deriveVerdict,
  mergeFixes,
  parseCommitmentKeys,
  parseRubricVersion,
  timingSafeEqual,
  validateReviewerOutput,
} from "./logic.js";

const GROK_MODEL_DEFAULT = "grok-4";
const ANTHROPIC_MODEL_DEFAULT = "claude-opus-5";
const OPENAI_MODEL_DEFAULT = "gpt-5";
const XAI_BASE_URL = "https://api.x.ai/v1";
const OPENAI_BASE_URL = "https://api.openai.com/v1";

class ReviewerError extends Error {}

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function callOpenAICompatible({ baseUrl, apiKey, model, keys, artifact, artifactType, context }) {
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: SYSTEM_PROMPT + rubricText },
        { role: "user", content: buildUserPayload(artifact, artifactType, context) },
      ],
      response_format: {
        type: "json_schema",
        json_schema: { name: "beatitude_review", strict: true, schema: buildScoreSchema(keys) },
      },
    }),
  });
  if (!response.ok) {
    throw new ReviewerError(`${model} call failed: ${response.status} ${(await response.text()).slice(0, 300)}`);
  }
  const raw = await response.json();
  const content = raw.choices?.[0]?.message?.content;
  if (!content) throw new ReviewerError(`${model} returned an empty response.`);
  const data = JSON.parse(content);
  validateReviewerOutput(data, keys, model);
  return {
    model,
    scores: data.scores,
    rationale: data.rationale ?? "",
    suggested_fixes: data.suggested_fixes ?? {},
    raw,
  };
}

async function callClaude({ apiKey, model, keys, artifact, artifactType, context }) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: 16000,
      system: SYSTEM_PROMPT + rubricText,
      messages: [{ role: "user", content: buildUserPayload(artifact, artifactType, context) }],
      output_config: { format: { type: "json_schema", schema: buildScoreSchema(keys) } },
    }),
  });
  if (!response.ok) {
    throw new ReviewerError(`${model} call failed: ${response.status} ${(await response.text()).slice(0, 300)}`);
  }
  const raw = await response.json();
  if (raw.stop_reason === "refusal") {
    throw new ReviewerError(`${model} declined to review this artifact (stop_reason=refusal).`);
  }
  const text = raw.content?.find((b) => b.type === "text")?.text;
  if (!text) throw new ReviewerError(`${model} returned no text content.`);
  const data = JSON.parse(text);
  validateReviewerOutput(data, keys, model);
  return {
    model,
    scores: data.scores,
    rationale: data.rationale ?? "",
    suggested_fixes: data.suggested_fixes ?? {},
    raw,
  };
}

async function supabaseInsertVerdict(env, row) {
  const response = await fetch(`${env.SUPABASE_URL.replace(/\/$/, "")}/rest/v1/verdicts`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
      prefer: "return=minimal",
    },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    throw new Error(`Supabase insert failed: ${response.status} ${(await response.text()).slice(0, 300)}`);
  }
}

async function handleReview(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Request body must be JSON." }, 400);
  }
  const { artifact, artifact_type: artifactType, context } = body ?? {};
  if (typeof artifact !== "string" || !artifact.trim()) {
    return json({ error: "'artifact' must be a non-empty string." }, 400);
  }
  if (typeof artifactType !== "string" || !artifactType.trim()) {
    return json({ error: "'artifact_type' must be a non-empty string." }, 400);
  }

  const keys = parseCommitmentKeys(rubricText);
  const grokArgs = {
    baseUrl: env.XAI_BASE_URL || XAI_BASE_URL,
    apiKey: env.XAI_API_KEY,
    model: env.GROK_MODEL || GROK_MODEL_DEFAULT,
    keys,
    artifact,
    artifactType,
    context,
  };

  let scores, verdict, rationale, modelsUsed, allResults;
  try {
    const initial = await callOpenAICompatible(grokArgs);
    verdict = deriveVerdict(initial.scores, keys);
    scores = initial.scores;
    rationale = initial.rationale;
    modelsUsed = [`${initial.model} (reviewer)`];
    allResults = [initial];

    if (verdict === VERDICT_CLOSELY) {
      // Council: Claude, GPT, Grok — independent passes on the same artifact
      // + rubric; the per-commitment minimum replaces the single reviewer.
      const council = await Promise.all([
        callClaude({
          apiKey: env.ANTHROPIC_API_KEY,
          model: env.ANTHROPIC_MODEL || ANTHROPIC_MODEL_DEFAULT,
          keys,
          artifact,
          artifactType,
          context,
        }),
        callOpenAICompatible({
          baseUrl: env.OPENAI_BASE_URL || OPENAI_BASE_URL,
          apiKey: env.OPENAI_API_KEY,
          model: env.OPENAI_MODEL || OPENAI_MODEL_DEFAULT,
          keys,
          artifact,
          artifactType,
          context,
        }),
        callOpenAICompatible(grokArgs),
      ]);
      scores = aggregateMin(council.map((m) => m.scores), keys);
      verdict = deriveVerdict(scores, keys);
      modelsUsed = modelsUsed.concat(council.map((m) => `${m.model} (council)`));
      rationale =
        `[reviewer:${allResults[0].model}] ${allResults[0].rationale}\n` +
        council.map((m) => `[council:${m.model}] ${m.rationale}`).join("\n");
      allResults = council.concat(allResults);
    }
  } catch (err) {
    if (err instanceof ReviewerError) return json({ error: err.message }, 502);
    throw err;
  }

  const record = {
    verdict_id: crypto.randomUUID(),
    artifact_type: artifactType,
    scores,
    verdict,
    rationale,
    suggested_fixes: mergeFixes(keys, scores, allResults),
    models_used: modelsUsed,
    created_at: new Date().toISOString(),
  };

  // The audit write is part of the contract: log before returning, always.
  try {
    await supabaseInsertVerdict(env, {
      ...record,
      artifact,
      context: context ?? {},
      rubric_version: parseRubricVersion(rubricText),
      raw_responses: allResults.map((r) => r.raw),
    });
  } catch (err) {
    return json({ error: `Verdict computed but could not be logged; not returned unlogged. ${err.message}` }, 500);
  }

  return json(record);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return json({ ok: true });

    const auth = request.headers.get("authorization") ?? "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    if (!env.BEATITUDE_AUTH_TOKEN || !token || !timingSafeEqual(token, env.BEATITUDE_AUTH_TOKEN)) {
      return json({ error: "Unauthorized." }, 401);
    }

    if (url.pathname !== "/review" && url.pathname !== "/") {
      return json({ error: "Not found. POST /review." }, 404);
    }
    if (request.method !== "POST") {
      return json({ error: "Method not allowed. POST /review." }, 405);
    }
    return handleReview(request, env);
  },
};
