"use strict";

const fs = require("node:fs");
const path = require("node:path");

const CONSENSUS_STATUSES = ["agreement", "disagreement", "tie"];
const CONSENSUS_OUTCOMES = [...CONSENSUS_STATUSES, "unavailable"];
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
  return typeof value !== "number" || typeof baseline !== "number" || baseline === 0
    ? null
    : round(value / baseline);
}

function parseWorkflowResponse(result) {
  const output = result?.response?.output;
  const response = typeof output === "string" ? JSON.parse(output) : output;
  if (response === null || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("evaluation result does not contain a workflow response object");
  }
  return response;
}

function providerSampleCount(result) {
  const label = result?.provider?.label;
  const match = typeof label === "string" ? /^policy-samples-(\d+)$/.exec(label) : null;
  if (match === null) {
    throw new Error("evaluation result provider does not identify a policy sample count");
  }
  return Number.parseInt(match[1], 10);
}

function workflowErrorCode(result) {
  const message = typeof result?.error === "string" ? result.error : "";
  return /\\?"code\\?":\\?"([^"\\]+)\\?"/.exec(message)?.[1] ?? "unknown";
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
  const trials = group.results.length;
  const trialsByCase = Object.groupBy(group.results, (result) => result.ticketId);
  const trialCounts = Object.values(trialsByCase).map((results) => results.length);
  const cases = trialCounts.length;
  const completedResults = group.results.filter((result) => result.workflowSucceeded);
  const completedTrials = completedResults.length;
  const policyCorrect = group.results.filter((result) => result.policyCorrect).length;
  const escalationCorrect = group.results.filter(
    (result) => result.escalationCorrect,
  ).length;
  const consensusCounts = Object.fromEntries(
    CONSENSUS_OUTCOMES.map((status) => [
      status,
      group.results.filter((result) => result.consensusStatus === status).length,
    ]),
  );
  const inputTokens = completedResults.reduce(
    (total, result) => total + result.usage.inputTokens,
    0,
  );
  const outputTokens = completedResults.reduce(
    (total, result) => total + result.usage.outputTokens,
    0,
  );
  const costs = completedResults.map((result) => estimateUsageCost(result.usage, pricing));
  const unpricedModels = [...new Set(costs.flatMap((cost) => cost.unpricedModels))].sort();
  const totalCost = costs.reduce(
    (total, cost) => total + (cost.costUsd === null ? 0 : cost.costUsd),
    0,
  );
  const latencies = completedResults.map((result) => result.latencyMs);
  const errorCodes = Object.fromEntries(
    [...new Set(group.results.map((result) => result.errorCode).filter(Boolean))]
      .sort()
      .map((code) => [
        code,
        group.results.filter((result) => result.errorCode === code).length,
      ]),
  );

  return {
    sampleCount: group.sampleCount,
    providerLabels: [...group.providerLabels].sort(),
    cases,
    trials,
    trialsPerCase: {
      minimum: Math.min(...trialCounts),
      maximum: Math.max(...trialCounts),
    },
    workflowSuccess: {
      successful: completedTrials,
      total: trials,
      rate: round(completedTrials / trials),
      errorCodes,
    },
    policyAccuracy: {
      correct: policyCorrect,
      total: trials,
      rate: round(policyCorrect / trials),
    },
    escalationAccuracy: {
      correct: escalationCorrect,
      total: trials,
      rate: round(escalationCorrect / trials),
    },
    consensus: Object.fromEntries(
      CONSENSUS_OUTCOMES.map((status) => [
        status,
        {
          count: consensusCounts[status],
          rate: round(consensusCounts[status] / trials),
        },
      ]),
    ),
    latencyMs: {
      observedTrials: completedTrials,
      average: completedTrials > 0 ? round(average(latencies), 2) : null,
      p50: completedTrials > 0 ? percentile(latencies, 0.5) : null,
      p95: completedTrials > 0 ? percentile(latencies, 0.95) : null,
      minimum: completedTrials > 0 ? Math.min(...latencies) : null,
      maximum: completedTrials > 0 ? Math.max(...latencies) : null,
    },
    tokens: {
      observedTrials: completedTrials,
      input: inputTokens,
      output: outputTokens,
      total: inputTokens + outputTokens,
      averagePerCompletedTrial:
        completedTrials > 0
          ? round((inputTokens + outputTokens) / completedTrials, 2)
          : null,
      complete: completedTrials === trials,
    },
    estimatedCostUsd:
      unpricedModels.length === 0
        ? {
            total: round(totalCost, 6),
            averagePerCompletedTrial:
              completedTrials > 0 ? round(totalCost / completedTrials, 6) : null,
            observedTrials: completedTrials,
            complete: completedTrials === trials,
          }
        : null,
    unpricedModels,
  };
}

function summarizeCaseComparisons(groups, baselineSampleCount) {
  const byTicket = new Map();
  for (const [sampleCount, group] of groups.entries()) {
    for (const result of group.results) {
      if (!byTicket.has(result.ticketId)) {
        byTicket.set(result.ticketId, new Map());
      }
      const bySampleCount = byTicket.get(result.ticketId);
      if (!bySampleCount.has(sampleCount)) {
        bySampleCount.set(sampleCount, []);
      }
      bySampleCount.get(sampleCount).push(result);
    }
  }

  return [...byTicket.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([ticketId, bySampleCount]) => {
      const baselineTrials = bySampleCount.get(baselineSampleCount);
      if (baselineTrials === undefined) {
        throw new Error(`${ticketId} is missing sample-count-${baselineSampleCount} trials`);
      }
      const baselinePolicyRate =
        baselineTrials.filter((result) => result.policyCorrect).length /
        baselineTrials.length;
      const baselineEscalationRate =
        baselineTrials.filter((result) => result.escalationCorrect).length /
        baselineTrials.length;

      const sampleCounts = [...bySampleCount.entries()]
        .sort(([left], [right]) => left - right)
        .map(([sampleCount, results]) => {
          const policyRate =
            results.filter((result) => result.policyCorrect).length / results.length;
          const escalationRate =
            results.filter((result) => result.escalationCorrect).length /
            results.length;
          const consensus = Object.fromEntries(
            CONSENSUS_OUTCOMES.map((status) => [
              status,
              results.filter((result) => result.consensusStatus === status).length,
            ]),
          );

          let classification = "baseline";
          if (sampleCount !== baselineSampleCount) {
            if (
              policyRate < baselinePolicyRate ||
              escalationRate < baselineEscalationRate
            ) {
              classification = "regressed";
            } else if (consensus.tie > 0) {
              classification = "tie";
            } else if (
              policyRate > baselinePolicyRate ||
              escalationRate > baselineEscalationRate
            ) {
              classification = "recovered_by_consensus";
            } else {
              classification = "unchanged";
            }
          }

          return {
            sampleCount,
            trials: results.length,
            workflowSuccess: round(
              results.filter((result) => result.workflowSucceeded).length /
                results.length,
            ),
            policyAccuracy: round(policyRate),
            escalationAccuracy: round(escalationRate),
            consensus,
            classification,
          };
        });

      return { ticketId, sampleCounts };
    });
}

function buildRecommendation(summaries, baseline, caseComparisons) {
  const improved = summaries
    .filter(
      (summary) =>
        summary.sampleCount !== baseline.sampleCount &&
        summary.policyAccuracy.rate >= baseline.policyAccuracy.rate &&
        summary.escalationAccuracy.rate >= baseline.escalationAccuracy.rate &&
        (summary.policyAccuracy.rate > baseline.policyAccuracy.rate ||
          summary.escalationAccuracy.rate > baseline.escalationAccuracy.rate),
    )
    .sort(
      (left, right) =>
        right.policyAccuracy.rate - left.policyAccuracy.rate ||
        right.escalationAccuracy.rate - left.escalationAccuracy.rate ||
        (left.tokens.averagePerCompletedTrial ?? Number.POSITIVE_INFINITY) -
          (right.tokens.averagePerCompletedTrial ?? Number.POSITIVE_INFINITY) ||
        left.sampleCount - right.sampleCount,
    );
  const recommended = improved[0] ?? baseline;
  const classifications = caseComparisons.flatMap((comparison) =>
    comparison.sampleCounts
      .filter((result) => result.sampleCount !== baseline.sampleCount)
      .map((result) => result.classification),
  );
  const classificationCounts = Object.fromEntries(
    ["recovered_by_consensus", "unchanged", "regressed", "tie"].map(
      (classification) => [
        classification,
        classifications.filter((value) => value === classification).length,
      ],
    ),
  );

  return {
    sampleCount: recommended.sampleCount,
    reason:
      improved.length === 0
        ? "No higher sample count improved policy or escalation accuracy; keep the lowest-cost behavior."
        : `Sample count ${recommended.sampleCount} produced the strongest measured accuracy improvement without regressing either accuracy metric.`,
    classificationCounts,
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
    const expected = result?.vars?.expected;
    const ticketId = result?.vars?.ticket?.ticket_id;
    const expectedSampleCount = providerSampleCount(result);
    if (expected === null || typeof expected !== "object") {
      throw new Error("evaluation result is missing expected policy labels");
    }
    if (typeof ticketId !== "string" || ticketId.length === 0) {
      throw new Error("evaluation result ticket identifier is missing or invalid");
    }

    const workflowSucceeded = result?.response?.output !== null && result?.response?.output !== undefined;
    let sampleCount = expectedSampleCount;
    let consensusStatus = "unavailable";
    let policyCorrect = false;
    let escalationCorrect = false;
    let latencyMs = null;
    let usage = null;
    let errorCode = workflowErrorCode(result);

    if (workflowSucceeded) {
      const response = parseWorkflowResponse(result);
      const consensus = response?.policy?.consensus;
      sampleCount = consensus?.sample_count;
      consensusStatus = consensus?.status;
      if (!Number.isInteger(sampleCount) || sampleCount < 1) {
        throw new Error("policy consensus sample count is missing or invalid");
      }
      if (sampleCount !== expectedSampleCount) {
        throw new Error("policy consensus sample count does not match its provider");
      }
      if (!CONSENSUS_STATUSES.includes(consensusStatus)) {
        throw new Error("policy consensus status is missing or invalid");
      }
      if (typeof result.latencyMs !== "number" || result.latencyMs < 0) {
        throw new Error("evaluation result latency is missing or invalid");
      }
      policyCorrect = response.policy?.outcome?.decision === expected.policy_decision;
      escalationCorrect =
        response.requires_escalation === expected.requires_escalation;
      latencyMs = result.latencyMs;
      usage = collectUsage(response);
      errorCode = null;
      for (const model of Object.keys(usage.byModel)) {
        usedModels.add(model);
      }
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
    group.results.push({
      ticketId,
      workflowSucceeded,
      policyCorrect,
      escalationCorrect,
      consensusStatus,
      latencyMs,
      usage,
      errorCode,
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
      summary.tokens.averagePerCompletedTrial,
      baseline.tokens.averagePerCompletedTrial,
    ),
    averageCostMultiplier:
      summary.estimatedCostUsd === null || baseline.estimatedCostUsd === null
        ? null
        : ratio(
            summary.estimatedCostUsd.averagePerCompletedTrial,
            baseline.estimatedCostUsd.averagePerCompletedTrial,
          ),
  }));

  const orderedUsedModels = [...usedModels].sort();
  const caseComparisons = summarizeCaseComparisons(groups, baseline.sampleCount);

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
    caseComparisons,
    recommendation: buildRecommendation(summaries, baseline, caseComparisons),
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

function milliseconds(value) {
  return value === null ? "unavailable" : `${value.toFixed(2)} ms`;
}

function renderMarkdown(summary) {
  const lines = [
    "# Policy self-consistency summary",
    "",
    `Promptfoo evaluation: \`${summary.sourceEvalId ?? "unknown"}\``,
    "",
    "## Results by sample count",
    "",
    "| Samples | Cases | Trials | Workflow success | Policy accuracy | Escalation accuracy | Agreement | Disagreement | Tie | Avg latency | p95 latency | Observed tokens | Observed estimated cost |",
    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
  ];

  for (const result of summary.bySampleCount) {
    lines.push(
      `| ${result.sampleCount} | ${result.cases} | ${result.trials} | ${percentage(result.workflowSuccess.rate)} | ${percentage(result.policyAccuracy.rate)} | ${percentage(result.escalationAccuracy.rate)} | ${percentage(result.consensus.agreement.rate)} | ${percentage(result.consensus.disagreement.rate)} | ${percentage(result.consensus.tie.rate)} | ${milliseconds(result.latencyMs.average)} | ${milliseconds(result.latencyMs.p95)} | ${result.tokens.total} | ${currency(result.estimatedCostUsd?.total ?? null)} |`,
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

  lines.push(
    "",
    "## Per-case effect",
    "",
    "| Ticket | Samples | Trials | Workflow success | Policy accuracy | Escalation accuracy | Classification |",
    "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
  );
  for (const comparison of summary.caseComparisons) {
    for (const result of comparison.sampleCounts) {
      lines.push(
        `| ${comparison.ticketId} | ${result.sampleCount} | ${result.trials} | ${percentage(result.workflowSuccess)} | ${percentage(result.policyAccuracy)} | ${percentage(result.escalationAccuracy)} | ${result.classification} |`,
      );
    }
  }

  lines.push(
    "",
    "## Recommendation",
    "",
    `Use policy sample count **${summary.recommendation.sampleCount}**. ${summary.recommendation.reason}`,
  );

  const errors = summary.bySampleCount.flatMap((result) =>
    Object.entries(result.workflowSuccess.errorCodes).map(([code, count]) => ({
      sampleCount: result.sampleCount,
      code,
      count,
    })),
  );
  if (errors.length > 0) {
    lines.push(
      "",
      "## Workflow errors",
      "",
      "| Samples | Error code | Trials |",
      "| ---: | --- | ---: |",
      ...errors.map(
        (error) => `| ${error.sampleCount} | ${error.code} | ${error.count} |`,
      ),
      "",
      "Token and cost totals exclude failed workflows because the API does not return stage usage for failed requests; they are observed lower bounds.",
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
