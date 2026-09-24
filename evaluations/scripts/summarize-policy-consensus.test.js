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
  ticketId,
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
      ticket: { ticket_id: ticketId },
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
          ticketId: "ticket-a",
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
          ticketId: "ticket-b",
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
          ticketId: "ticket-a",
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
          ticketId: "ticket-b",
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
          ticketId: "ticket-a",
          sampleCount: 5,
          consensusStatus: "agreement",
          actualDecision: "deny",
          expectedDecision: "allow",
          actualEscalation: true,
          expectedEscalation: false,
          latencyMs: 400,
          inputTokens: 500,
          outputTokens: 50,
        }),
        evaluationResult({
          ticketId: "ticket-b",
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
  assert.equal(oneSample.tokens.averagePerCompletedTrial, 165);
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
  assert.deepEqual(summary.recommendation, {
    sampleCount: 3,
    reason:
      "Sample count 3 produced the strongest measured accuracy improvement without regressing either accuracy metric.",
    classificationCounts: {
      recovered_by_consensus: 1,
      unchanged: 1,
      regressed: 1,
      tie: 1,
    },
  });
  assert.equal(
    summary.caseComparisons[0].sampleCounts[2].classification,
    "regressed",
  );
  assert.equal(
    summary.caseComparisons[1].sampleCounts[1].classification,
    "recovered_by_consensus",
  );
  assert.equal(summary.caseComparisons[1].sampleCounts[2].classification, "tie");
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

test("summarizeReport recommends one sample when consensus adds no accuracy", () => {
  const report = reportFixture();
  for (const result of report.results.results) {
    const response = JSON.parse(result.response.output);
    response.policy.outcome.decision = result.vars.expected.policy_decision;
    response.requires_escalation = result.vars.expected.requires_escalation;
    result.response.output = JSON.stringify(response);
  }

  const summary = summarizeReport(report, PRICING);

  assert.equal(summary.recommendation.sampleCount, 1);
  assert.match(summary.recommendation.reason, /No higher sample count improved/);
});

test("summarizeReport counts workflow errors without discarding the experiment", () => {
  const report = reportFixture();
  report.results.results[0].response = null;
  report.results.results[0].error =
    'HTTP 502: {"detail":{"code":"review_output_invalid"}}';

  const summary = summarizeReport(report, PRICING);
  const oneSample = summary.bySampleCount[0];

  assert.equal(oneSample.workflowSuccess.rate, 0.5);
  assert.deepEqual(oneSample.workflowSuccess.errorCodes, {
    review_output_invalid: 1,
  });
  assert.equal(oneSample.policyAccuracy.rate, 0);
  assert.equal(oneSample.consensus.unavailable.rate, 0.5);
  assert.equal(oneSample.tokens.observedTrials, 1);
  assert.equal(oneSample.tokens.complete, false);
  assert.equal(oneSample.estimatedCostUsd.complete, false);
  assert.match(renderMarkdown(summary), /observed lower bounds/);
});

test("renderMarkdown creates comparison and pricing tables", () => {
  const markdown = renderMarkdown(summarizeReport(reportFixture(), PRICING));

  assert.match(markdown, /Policy self-consistency summary/);
  assert.match(markdown, /\| 3 \| 2 \| 2 \| 100\.00% \| 100\.00%/);
  assert.match(markdown, /\| 3 \| 50\.00 pp \| 50\.00 pp \| 2\.00x/);
  assert.match(markdown, /ticket-b \| 3 \| 1 \| 100\.00% \| 100\.00% \| 100\.00% \| recovered_by_consensus/);
  assert.match(markdown, /Use policy sample count \*\*3\*\*/);
  assert.match(markdown, /\$0\.75\/1M input tokens/);
});
