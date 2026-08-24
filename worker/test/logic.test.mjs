// Cross-language contract tests: the Worker port must agree with the Python
// core on rubric parsing, verdict derivation, and council aggregation.
// Runs with:  node --test  (no dependencies).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  aggregateMin,
  buildScoreSchema,
  deriveVerdict,
  mergeFixes,
  parseCommitmentKeys,
  parseRubricVersion,
  timingSafeEqual,
} from "../src/logic.js";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const golden = JSON.parse(readFileSync(join(repoRoot, "tests", "fixtures", "golden.json"), "utf8"));
const rubricText = readFileSync(join(repoRoot, "rubric", "rubric.v1.md"), "utf8");
const keys = golden.keys;

test("rubric parsing matches the golden commitment keys", () => {
  assert.deepEqual(parseCommitmentKeys(rubricText), keys);
  assert.equal(parseRubricVersion(rubricText), "1.0");
});

test("verdict derivation matches golden cases", () => {
  for (const c of golden.derive_cases) {
    assert.equal(deriveVerdict(c.scores, keys), c.expected, c.name);
  }
});

test("council min-aggregation matches golden cases", () => {
  for (const c of golden.aggregate_cases) {
    const result = aggregateMin(c.inputs, keys);
    assert.deepEqual(result, c.expected, c.name);
    assert.equal(deriveVerdict(result, keys), c.expected_verdict, c.name);
  }
});

test("invalid scores are rejected", () => {
  const scores = Object.fromEntries(keys.map((k) => [k, 2]));
  scores[keys[0]] = 3;
  assert.throws(() => deriveVerdict(scores, keys), /0, 1, or 2/);
  const partial = Object.fromEntries(keys.slice(1).map((k) => [k, 2]));
  assert.throws(() => deriveVerdict(partial, keys), /missing/);
});

test("score schema covers every commitment strictly", () => {
  const schema = buildScoreSchema(keys);
  assert.deepEqual(Object.keys(schema.properties.scores.properties), keys);
  assert.deepEqual(schema.properties.scores.required, keys);
  assert.equal(schema.properties.scores.additionalProperties, false);
});

test("mergeFixes only surfaces fixes for commitments below 2", () => {
  const scores = Object.fromEntries(keys.map((k) => [k, 2]));
  scores.no_hype = 1;
  const results = [
    { suggested_fixes: { no_hype: "", transparency: "irrelevant (scored 2)" } },
    { suggested_fixes: { no_hype: "Bound the claim to measured results." } },
  ];
  assert.deepEqual(mergeFixes(keys, scores, results), {
    no_hype: "Bound the claim to measured results.",
  });
});

test("timingSafeEqual", () => {
  assert.equal(timingSafeEqual("secret", "secret"), true);
  assert.equal(timingSafeEqual("secret", "secreT"), false);
  assert.equal(timingSafeEqual("short", "longer-token"), false);
  assert.equal(timingSafeEqual("", ""), true);
});
