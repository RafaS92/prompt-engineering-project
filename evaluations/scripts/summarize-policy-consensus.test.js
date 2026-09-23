"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  collectUsage,
  estimateUsageCost,
  renderMarkdown,
  summarizeReport,
} = require("./summarize-policy-consensus.js");

const MODEL = "test-model";
const PRICING = {
  models: {
    [MODEL]: {
      inputUsdPerMillionTokens: 0.75,
      outputUsdPerMillionTokens: 4.5,
      source: "https://example.test/pricing",
      verifiedOn: "2026-09-23",
    },
  },
};

function stage(inputTokens, outputTokens) {
  return {
    outcome: {},
    metadata: {
      model: MODEL,
      usage: {
        input_tokens: inputTokens,
        output_tokens: outputTokens,
      },
    },
  };
}

function evaluationResult({
  sampleCount,
  consensusStatus,
  actualDecision,
  expectedDecision,
  actualEscalation,
  expectedEscalation,
  latencyMs,
  inputTokens,
  outputTokens,
}) {
  const response = {
    requires_escalation: actualEscalation,
    triage: stage(0, 0),
    policy: {
      ...stage(inputTokens, outputTokens),
      outcome: { decision: actualDecision },
      consensus: {
        status: consensusStatus,
        sample_count: sampleCount,
      },
    },
    draft: null,
    review: null,
  };
  return {
    provider: { label: `policy-samples-${sampleCount}` },
    latencyMs,
    vars: {
      expected: {
        policy_decision: expectedDecision,
        requires_escalation: expectedEscalation,
      },
    },
    response: { output: JSON.stringify(response) },
  };
}

function reportFixture() {
  return {
    evalId: "eval-test",
    results: {
      results: [
        evaluationResult({
          sampleCount: 1,
          consensusStatus: "agreement",
          actualDecision: "allow",
          expectedDecision: "allow",
          actualEscalation: false,
          expectedEscalation: false,
          latencyMs: 100,
          inputTokens: 100,
          outputTokens: 10,
        }),
        evaluationResult({
          sampleCount: 1,
          consensusStatus: "agreement",
          actualDecision: "deny",
          expectedDecision: "allow",
          actualEscalation: true,
          expectedEscalation: false,
          latencyMs: 200,
          inputTokens: 200,
          outputTokens: 20,
        }),
        evaluationResult({
          sampleCount: 3,
          consensusStatus: "agreement",
          actualDecision: "allow",
          expectedDecision: "allow",
          actualEscalation: false,
          expectedEscalation: false,
          latencyMs: 200,
          inputTokens: 300,
          outputTokens: 30,
        }),
        evaluationResult({
          sampleCount: 3,
          consensusStatus: "disagreement",
          actualDecision: "escalate",
          expectedDecision: "escalate",
          actualEscalation: true,
          expectedEscalation: true,
          latencyMs: 400,
          inputTokens: 300,
          outputTokens: 30,
        }),
        evaluationResult({
          sampleCount: 5,
          consensusStatus: "agreement",
          actualDecision: "allow",
          expectedDecision: "allow",
          actualEscalation: false,
          expectedEscalation: false,
          latencyMs: 400,
          inputTokens: 500,
          outputTokens: 50,
        }),
        evaluationResult({
          sampleCount: 5,
          consensusStatus: "tie",
          actualDecision: "escalate",
          expectedDecision: "escalate",
          actualEscalation: true,
          expectedEscalation: true,
          latencyMs: 500,
          inputTokens: 500,
          outputTokens: 50,
        }),
      ],
    },
  };
}

test("collectUsage sums executed stages and groups tokens by model", () => {
  const usage = collectUsage({
    triage: stage(100, 10),
    policy: stage(200, 20),
    draft: null,
    review: stage(50, 5),
  });

  assert.deepEqual(usage, {
    inputTokens: 350,
    outputTokens: 35,
    totalTokens: 385,
    byModel: {
      [MODEL]: { inputTokens: 350, outputTokens: 35 },
    },
  });
});

test("estimateUsageCost uses configured per-million-token rates", () => {
  const estimate = estimateUsageCost(
    {
      byModel: {
        [MODEL]: { inputTokens: 1_000_000, outputTokens: 1_000_000 },
      },
    },
    PRICING,
  );

  assert.equal(estimate.costUsd, 5.25);
  assert.deepEqual(estimate.unpricedModels, []);
});

test("summarizeReport compares quality, consensus, latency, tokens, and cost", () => {
  const summary = summarizeReport(reportFixture(), PRICING);
  const oneSample = summary.bySampleCount[0];
  const threeSamples = summary.bySampleCount[1];
  const fiveSamples = summary.bySampleCount[2];

  assert.equal(summary.resultCount, 6);
  assert.deepEqual(
    summary.bySampleCount.map((result) => result.sampleCount),
    [1, 3, 5],
  );
  assert.equal(oneSample.policyAccuracy.rate, 0.5);
  assert.equal(oneSample.escalationAccuracy.rate, 0.5);
  assert.equal(oneSample.latencyMs.average, 150);
  assert.equal(oneSample.latencyMs.p95, 200);
  assert.equal(oneSample.tokens.total, 330);
  assert.equal(oneSample.estimatedCostUsd.total, 0.00036);
  assert.equal(threeSamples.policyAccuracy.rate, 1);
  assert.equal(threeSamples.consensus.disagreement.rate, 0.5);
  assert.equal(fiveSamples.consensus.tie.rate, 0.5);
  assert.deepEqual(summary.comparisonToBaseline.values[1], {
    sampleCount: 3,
    policyAccuracyDeltaPercentagePoints: 50,
    escalationAccuracyDeltaPercentagePoints: 50,
    averageLatencyMultiplier: 2,
    averageTokenMultiplier: 2,
    averageCostMultiplier: 2,
  });
});

test("summarizeReport identifies models without pricing instead of estimating zero", () => {
  const summary = summarizeReport(reportFixture(), { models: {} });

  assert.equal(summary.bySampleCount[0].estimatedCostUsd, null);
  assert.deepEqual(summary.bySampleCount[0].unpricedModels, [MODEL]);
  assert.equal(
    summary.comparisonToBaseline.values[1].averageCostMultiplier,
    null,
  );
});

test("renderMarkdown creates comparison and pricing tables", () => {
  const markdown = renderMarkdown(summarizeReport(reportFixture(), PRICING));

  assert.match(markdown, /Policy self-consistency summary/);
  assert.match(markdown, /\| 3 \| 2 \| 100\.00%/);
  assert.match(markdown, /\| 3 \| 50\.00 pp \| 50\.00 pp \| 2\.00x/);
  assert.match(markdown, /\$0\.75\/1M input tokens/);
});
