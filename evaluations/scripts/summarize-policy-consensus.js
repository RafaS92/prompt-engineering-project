"use strict";

const fs = require("node:fs");
const path = require("node:path");

const CONSENSUS_STATUSES = ["agreement", "disagreement", "tie"];
const STAGE_NAMES = ["triage", "policy", "draft", "review"];

function round(value, digits = 4) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function average(values) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function percentile(values, percentileValue) {
  const ordered = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.ceil(percentileValue * ordered.length) - 1);
  return ordered[index];
}

function ratio(value, baseline) {
  return baseline === 0 ? null : round(value / baseline);
}

function parseWorkflowResponse(result) {
  const output = result?.response?.output;
  const response = typeof output === "string" ? JSON.parse(output) : output;
  if (response === null || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("evaluation result does not contain a workflow response object");
  }
  return response;
}

function collectUsage(response) {
  const byModel = {};
  let inputTokens = 0;
  let outputTokens = 0;

  for (const stageName of STAGE_NAMES) {
    const stage = response[stageName];
    if (stage === null || stage === undefined) {
      continue;
    }
    const model = stage?.metadata?.model;
    const usage = stage?.metadata?.usage;
    if (
      typeof model !== "string" ||
      model.length === 0 ||
      !Number.isInteger(usage?.input_tokens) ||
      usage.input_tokens < 0 ||
      !Number.isInteger(usage?.output_tokens) ||
      usage.output_tokens < 0
    ) {
      throw new Error(`${stageName} stage has invalid model usage metadata`);
    }

    inputTokens += usage.input_tokens;
    outputTokens += usage.output_tokens;
    byModel[model] ??= { inputTokens: 0, outputTokens: 0 };
    byModel[model].inputTokens += usage.input_tokens;
    byModel[model].outputTokens += usage.output_tokens;
  }

  return {
    inputTokens,
    outputTokens,
    totalTokens: inputTokens + outputTokens,
    byModel,
  };
}

function estimateUsageCost(usage, pricing) {
  let totalUsd = 0;
  const unpricedModels = [];

  for (const [model, modelUsage] of Object.entries(usage.byModel)) {
    const rates = pricing.models?.[model];
    if (
      rates === undefined ||
      typeof rates.inputUsdPerMillionTokens !== "number" ||
      typeof rates.outputUsdPerMillionTokens !== "number"
    ) {
      unpricedModels.push(model);
      continue;
    }
    totalUsd +=
      (modelUsage.inputTokens * rates.inputUsdPerMillionTokens) / 1_000_000 +
      (modelUsage.outputTokens * rates.outputUsdPerMillionTokens) / 1_000_000;
  }

  return {
    costUsd: unpricedModels.length === 0 ? totalUsd : null,
    unpricedModels,
  };
}

function summarizeGroup(group, pricing) {
  const cases = group.results.length;
  const policyCorrect = group.results.filter((result) => result.policyCorrect).length;
  const escalationCorrect = group.results.filter(
    (result) => result.escalationCorrect,
  ).length;
  const consensusCounts = Object.fromEntries(
    CONSENSUS_STATUSES.map((status) => [
      status,
      group.results.filter((result) => result.consensusStatus === status).length,
    ]),
  );
  const inputTokens = group.results.reduce(
    (total, result) => total + result.usage.inputTokens,
    0,
  );
  const outputTokens = group.results.reduce(
    (total, result) => total + result.usage.outputTokens,
    0,
  );
  const costs = group.results.map((result) => estimateUsageCost(result.usage, pricing));
  const unpricedModels = [...new Set(costs.flatMap((cost) => cost.unpricedModels))].sort();
  const totalCost = costs.reduce(
    (total, cost) => total + (cost.costUsd === null ? 0 : cost.costUsd),
    0,
  );
  const latencies = group.results.map((result) => result.latencyMs);

  return {
    sampleCount: group.sampleCount,
    providerLabels: [...group.providerLabels].sort(),
    cases,
    policyAccuracy: {
      correct: policyCorrect,
      total: cases,
      rate: round(policyCorrect / cases),
    },
    escalationAccuracy: {
      correct: escalationCorrect,
      total: cases,
      rate: round(escalationCorrect / cases),
    },
    consensus: Object.fromEntries(
      CONSENSUS_STATUSES.map((status) => [
        status,
        {
          count: consensusCounts[status],
          rate: round(consensusCounts[status] / cases),
        },
      ]),
    ),
    latencyMs: {
      average: round(average(latencies), 2),
      p50: percentile(latencies, 0.5),
      p95: percentile(latencies, 0.95),
      minimum: Math.min(...latencies),
      maximum: Math.max(...latencies),
    },
    tokens: {
      input: inputTokens,
      output: outputTokens,
      total: inputTokens + outputTokens,
      averagePerCase: round((inputTokens + outputTokens) / cases, 2),
    },
    estimatedCostUsd:
      unpricedModels.length === 0
        ? {
            total: round(totalCost, 6),
            averagePerCase: round(totalCost / cases, 6),
          }
        : null,
    unpricedModels,
  };
}

function summarizeReport(report, pricing) {
  const rawResults = report?.results?.results;
  if (!Array.isArray(rawResults) || rawResults.length === 0) {
    throw new Error("Promptfoo report contains no evaluation results");
  }
  if (pricing === null || typeof pricing !== "object" || Array.isArray(pricing)) {
    throw new Error("pricing configuration must be an object");
  }

  const groups = new Map();
  const usedModels = new Set();
  for (const result of rawResults) {
    const response = parseWorkflowResponse(result);
    const consensus = response?.policy?.consensus;
    const expected = result?.vars?.expected;
    const sampleCount = consensus?.sample_count;
    const consensusStatus = consensus?.status;
    if (!Number.isInteger(sampleCount) || sampleCount < 1) {
      throw new Error("policy consensus sample count is missing or invalid");
    }
    if (!CONSENSUS_STATUSES.includes(consensusStatus)) {
      throw new Error("policy consensus status is missing or invalid");
    }
    if (expected === null || typeof expected !== "object") {
      throw new Error("evaluation result is missing expected policy labels");
    }
    if (typeof result.latencyMs !== "number" || result.latencyMs < 0) {
      throw new Error("evaluation result latency is missing or invalid");
    }

    if (!groups.has(sampleCount)) {
      groups.set(sampleCount, {
        sampleCount,
        providerLabels: new Set(),
        results: [],
      });
    }
    const group = groups.get(sampleCount);
    group.providerLabels.add(result.provider?.label ?? result.provider?.id ?? "unknown");
    const usage = collectUsage(response);
    for (const model of Object.keys(usage.byModel)) {
      usedModels.add(model);
    }
    group.results.push({
      policyCorrect: response.policy?.outcome?.decision === expected.policy_decision,
      escalationCorrect:
        response.requires_escalation === expected.requires_escalation,
      consensusStatus,
      latencyMs: result.latencyMs,
      usage,
    });
  }

  const sampleCounts = [...groups.keys()].sort((left, right) => left - right);
  const summaries = sampleCounts.map((sampleCount) =>
    summarizeGroup(groups.get(sampleCount), pricing),
  );
  const baseline = summaries.find((summary) => summary.sampleCount === 1) ?? summaries[0];
  const comparisons = summaries.map((summary) => ({
    sampleCount: summary.sampleCount,
    policyAccuracyDeltaPercentagePoints: round(
      (summary.policyAccuracy.rate - baseline.policyAccuracy.rate) * 100,
      2,
    ),
    escalationAccuracyDeltaPercentagePoints: round(
      (summary.escalationAccuracy.rate - baseline.escalationAccuracy.rate) * 100,
      2,
    ),
    averageLatencyMultiplier: ratio(
      summary.latencyMs.average,
      baseline.latencyMs.average,
    ),
    averageTokenMultiplier: ratio(
      summary.tokens.averagePerCase,
      baseline.tokens.averagePerCase,
    ),
    averageCostMultiplier:
      summary.estimatedCostUsd === null || baseline.estimatedCostUsd === null
        ? null
        : ratio(
            summary.estimatedCostUsd.averagePerCase,
            baseline.estimatedCostUsd.averagePerCase,
          ),
  }));

  const orderedUsedModels = [...usedModels].sort();

  return {
    sourceEvalId: report.evalId ?? null,
    resultCount: rawResults.length,
    pricing: {
      models: Object.fromEntries(
        orderedUsedModels
          .filter((model) => pricing.models?.[model] !== undefined)
          .map((model) => [model, pricing.models[model]]),
      ),
      assumption: "All reported input tokens are estimated at the uncached input rate.",
    },
    bySampleCount: summaries,
    comparisonToBaseline: {
      baselineSampleCount: baseline.sampleCount,
      values: comparisons,
    },
  };
}

function percentage(rate) {
  return `${round(rate * 100, 2).toFixed(2)}%`;
}

function currency(cost) {
  return cost === null ? "unavailable" : `$${cost.toFixed(6)}`;
}

function multiplier(value) {
  return value === null ? "unavailable" : `${value.toFixed(2)}x`;
}

function renderMarkdown(summary) {
  const lines = [
    "# Policy self-consistency summary",
    "",
    `Promptfoo evaluation: \`${summary.sourceEvalId ?? "unknown"}\``,
    "",
    "## Results by sample count",
    "",
    "| Samples | Cases | Policy accuracy | Escalation accuracy | Agreement | Disagreement | Tie | Avg latency | p95 latency | Total tokens | Estimated cost |",
    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
  ];

  for (const result of summary.bySampleCount) {
    lines.push(
      `| ${result.sampleCount} | ${result.cases} | ${percentage(result.policyAccuracy.rate)} | ${percentage(result.escalationAccuracy.rate)} | ${percentage(result.consensus.agreement.rate)} | ${percentage(result.consensus.disagreement.rate)} | ${percentage(result.consensus.tie.rate)} | ${result.latencyMs.average.toFixed(2)} ms | ${result.latencyMs.p95} ms | ${result.tokens.total} | ${currency(result.estimatedCostUsd?.total ?? null)} |`,
    );
  }

  lines.push(
    "",
    `## Comparison with sample count ${summary.comparisonToBaseline.baselineSampleCount}`,
    "",
    "| Samples | Policy accuracy delta | Escalation accuracy delta | Avg latency | Avg tokens | Avg cost |",
    "| ---: | ---: | ---: | ---: | ---: | ---: |",
  );
  for (const comparison of summary.comparisonToBaseline.values) {
    lines.push(
      `| ${comparison.sampleCount} | ${comparison.policyAccuracyDeltaPercentagePoints.toFixed(2)} pp | ${comparison.escalationAccuracyDeltaPercentagePoints.toFixed(2)} pp | ${multiplier(comparison.averageLatencyMultiplier)} | ${multiplier(comparison.averageTokenMultiplier)} | ${multiplier(comparison.averageCostMultiplier)} |`,
    );
  }

  const unpricedModels = [
    ...new Set(summary.bySampleCount.flatMap((result) => result.unpricedModels)),
  ];
  lines.push("", "## Pricing", "");
  if (unpricedModels.length > 0) {
    lines.push(`No configured rates were found for: ${unpricedModels.join(", ")}.`);
  } else {
    for (const [model, rates] of Object.entries(summary.pricing.models)) {
      lines.push(
        `- \`${model}\`: $${rates.inputUsdPerMillionTokens}/1M input tokens and $${rates.outputUsdPerMillionTokens}/1M output tokens (verified ${rates.verifiedOn}; ${rates.source}).`,
      );
    }
  }
  lines.push("", summary.pricing.assumption, "");
  return lines.join("\n");
}

function main() {
  const projectRoot = path.resolve(__dirname, "../..");
  const reportPath = path.resolve(
    process.argv[2] ?? path.join(projectRoot, "evaluations/reports/policy-self-consistency.json"),
  );
  const jsonOutputPath = path.resolve(
    process.argv[3] ??
      path.join(projectRoot, "evaluations/reports/policy-self-consistency-summary.json"),
  );
  const markdownOutputPath = path.resolve(
    process.argv[4] ??
      path.join(projectRoot, "evaluations/reports/policy-self-consistency-summary.md"),
  );
  const pricingPath = path.resolve(
    process.argv[5] ?? path.join(projectRoot, "evaluations/pricing/model-pricing.json"),
  );

  const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
  const pricing = JSON.parse(fs.readFileSync(pricingPath, "utf8"));
  const summary = summarizeReport(report, pricing);
  fs.mkdirSync(path.dirname(jsonOutputPath), { recursive: true });
  fs.mkdirSync(path.dirname(markdownOutputPath), { recursive: true });
  fs.writeFileSync(jsonOutputPath, `${JSON.stringify(summary, null, 2)}\n`);
  fs.writeFileSync(markdownOutputPath, renderMarkdown(summary));
  process.stdout.write(`Wrote ${jsonOutputPath}\nWrote ${markdownOutputPath}\n`);
}

if (require.main === module) {
  main();
}

module.exports = {
  collectUsage,
  estimateUsageCost,
  renderMarkdown,
  summarizeReport,
};
