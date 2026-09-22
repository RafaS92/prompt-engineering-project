"use strict";

function gradingResult(pass, reason) {
  return {
    pass,
    score: pass ? 1 : 0,
    reason,
  };
}

function parseResponse(output) {
  try {
    const parsed = JSON.parse(output);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : null;
  } catch {
    return null;
  }
}

function matchesExpectedValues(output, context) {
  const response = parseResponse(output);
  const expected = context.vars.expected;
  if (response === null || expected === null || typeof expected !== "object") {
    return gradingResult(false, "Response or expected labels are not valid objects");
  }

  const checks = [
    ["intent", response.triage?.outcome?.intent, expected.intent],
    ["urgency", response.triage?.outcome?.urgency, expected.urgency],
    [
      "policy decision",
      response.policy?.outcome?.decision,
      expected.policy_decision,
    ],
    [
      "escalation",
      response.requires_escalation,
      expected.requires_escalation,
    ],
  ];
  const mismatches = checks
    .filter(([, actual, wanted]) => actual !== wanted)
    .map(([label, actual, wanted]) => `${label}: expected ${wanted}, received ${actual}`);

  return gradingResult(
    mismatches.length === 0,
    mismatches.length === 0
      ? "Intent, urgency, policy decision, and escalation match"
      : mismatches.join("; "),
  );
}

function hasStageMetadata(output) {
  const response = parseResponse(output);
  if (response === null) {
    return gradingResult(false, "Response is not a JSON object");
  }

  const expectedPromptNames = {
    triage: "triage",
    policy: "policy_decision",
    draft: "response_draft",
    review: "response_review",
  };
  const requiredStages = ["triage", "policy"];
  if (!response.requires_escalation) {
    requiredStages.push("draft", "review");
  } else {
    for (const stage of ["draft", "review"]) {
      if (response[stage] !== null && response[stage] !== undefined) {
        requiredStages.push(stage);
      }
    }
  }

  const failures = [];
  for (const stage of requiredStages) {
    const stageResult = response[stage];
    if (stageResult === null || typeof stageResult !== "object") {
      failures.push(`${stage} stage is missing`);
      continue;
    }
    if (stageResult.outcome === null || typeof stageResult.outcome !== "object") {
      failures.push(`${stage} outcome is missing`);
    }
    const metadata = stageResult.metadata;
    if (metadata === null || typeof metadata !== "object") {
      failures.push(`${stage} metadata is missing`);
      continue;
    }
    if (metadata.prompt_name !== expectedPromptNames[stage]) {
      failures.push(`${stage} prompt name is missing or incorrect`);
    }
    if (!/^\d+\.\d+\.\d+$/.test(metadata.prompt_version ?? "")) {
      failures.push(`${stage} prompt version is missing or is not semantic`);
    }
  }

  return gradingResult(
    failures.length === 0,
    failures.length === 0
      ? "Every executed stage includes prompt metadata"
      : failures.join("; "),
  );
}

function hasReviewedFinalMessage(output) {
  const response = parseResponse(output);
  if (response === null) {
    return gradingResult(false, "Response is not a JSON object");
  }
  if (response.requires_escalation) {
    return gradingResult(true, "Final message is not required for escalated results");
  }

  const review = response.review?.outcome;
  const finalMessage = response.final_message;
  const isReviewedVerdict = ["approved", "revised"].includes(review?.verdict);
  const hasMessage = typeof finalMessage === "string" && finalMessage.trim().length > 0;
  const matchesReview = hasMessage && finalMessage === review?.final_message;

  return gradingResult(
    isReviewedVerdict && hasMessage && matchesReview,
    isReviewedVerdict && hasMessage && matchesReview
      ? "Non-escalated result contains the reviewed final message"
      : "Non-escalated result must contain an approved or revised final message",
  );
}

module.exports = {
  hasReviewedFinalMessage,
  hasStageMetadata,
  matchesExpectedValues,
};
