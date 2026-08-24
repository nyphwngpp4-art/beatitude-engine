// Pure logic for the Beatitude Engine Worker — a faithful port of the Python
// core (src/beatitude_engine/). The Python implementation is the harness-gated
// source of truth; tests/fixtures/golden.json is run against BOTH
// implementations (pytest and node --test) so they cannot drift.

export const VERDICT_ALIGNED = "Aligned";
export const VERDICT_CLOSELY = "Closely Aligned";
export const VERDICT_MISALIGNED = "Misaligned";
export const VALID_SCORES = [0, 1, 2];

const COMMITMENT_HEADING = /^###\s+\d+\.\s+([a-z0-9_]+)\b/gm;
const VERSION_LINE = /^Version:\s*(\S+)/m;

export function parseCommitmentKeys(rubricText) {
  const keys = [...rubricText.matchAll(COMMITMENT_HEADING)].map((m) => m[1]);
  if (keys.length === 0) {
    throw new Error("No commitment headings ('### N. key — ...') found in rubric.");
  }
  if (new Set(keys).size !== keys.length) {
    throw new Error("Duplicate commitment keys in rubric.");
  }
  return keys;
}

export function parseRubricVersion(rubricText) {
  const m = rubricText.match(VERSION_LINE);
  return m ? m[1] : "unknown";
}

// Verdict is DERIVED from scores per rubric v1 — never judged by a model.
export function deriveVerdict(scores, keys) {
  const missing = keys.filter((k) => !(k in scores));
  if (missing.length) throw new Error(`Scores missing commitments: ${missing.join(", ")}`);
  const vals = keys.map((k) => scores[k]);
  const bad = vals.filter((v) => !VALID_SCORES.includes(v));
  if (bad.length) throw new Error(`Scores must be 0, 1, or 2; got ${bad.join(", ")}`);
  if (vals.some((v) => v === 0)) return VERDICT_MISALIGNED;
  if (vals.some((v) => v === 1)) return VERDICT_CLOSELY;
  return VERDICT_ALIGNED;
}

// Council aggregation: minimum score per commitment (conservative).
export function aggregateMin(scoreSets, keys) {
  if (!scoreSets.length) throw new Error("aggregateMin needs at least one score set");
  const out = {};
  for (const k of keys) out[k] = Math.min(...scoreSets.map((s) => s[k]));
  return out;
}

// Strict-mode-compatible schema built from the rubric's commitment keys.
export function buildScoreSchema(keys) {
  const scoreProps = {};
  const fixProps = {};
  for (const k of keys) {
    scoreProps[k] = { type: "integer", enum: VALID_SCORES };
    fixProps[k] = { type: "string" };
  }
  return {
    type: "object",
    properties: {
      scores: {
        type: "object",
        properties: scoreProps,
        required: [...keys],
        additionalProperties: false,
      },
      rationale: { type: "string" },
      suggested_fixes: {
        type: "object",
        properties: fixProps,
        required: [...keys],
        additionalProperties: false,
      },
    },
    required: ["scores", "rationale", "suggested_fixes"],
    additionalProperties: false,
  };
}

// Mirrors SYSTEM_PROMPT in src/beatitude_engine/reviewers.py.
export const SYSTEM_PROMPT = `You are the reviewer inside the Beatitude Engine, Agavi AI's values-review service. You score one artifact against the rubric below. The rubric is the entire scoring contract: apply it exactly as written, commitment by commitment.

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

`;

export function buildUserPayload(artifact, artifactType, context) {
  return JSON.stringify(
    { artifact_type: artifactType, context: context ?? {}, artifact },
    null,
    2,
  );
}

export function validateReviewerOutput(data, keys, model) {
  const scores = data?.scores;
  if (typeof scores !== "object" || scores === null) {
    throw new Error(`${model} returned no 'scores' object.`);
  }
  const missing = keys.filter((k) => !(k in scores));
  if (missing.length) throw new Error(`${model} scores missing commitments: ${missing.join(", ")}`);
  for (const k of keys) {
    if (!VALID_SCORES.includes(scores[k])) {
      throw new Error(`${model} returned out-of-range score for ${k}: ${scores[k]}`);
    }
  }
}

// One suggested fix per commitment scoring below 2, if any model offered one.
export function mergeFixes(keys, scores, results) {
  const fixes = {};
  for (const k of keys) {
    if (scores[k] === 2) continue;
    for (const r of results) {
      const fix = (r.suggested_fixes?.[k] ?? "").trim();
      if (fix) {
        fixes[k] = fix;
        break;
      }
    }
  }
  return fixes;
}

// Constant-time string comparison for bearer-token auth.
export function timingSafeEqual(a, b) {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
