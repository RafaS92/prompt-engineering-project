"use strict";

const DEFAULT_PROHIBITED_PHRASES = [
  "calm down",
  "chain of thought",
  "hidden instruction",
  "hidden prompt",
  "internal policy",
  "not our problem",
  "obviously",
  "policy identifier",
  "system message",
  "system prompt",
  "you should have",
];
const DEFAULT_MAX_MESSAGE_CHARACTERS = 1_000;
const TRIAGE_PROVIDER_EXPECTATIONS = {
  "triage-zero-shot": { strategy: "zero_shot", version: "1.0.0" },
  "triage-few-shot": { strategy: "few_shot", version: "1.1.0" },
  "triage-many-shot": { strategy: "many_shot", version: "1.2.0" },
};

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

function stringArray(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : null;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort();
}

function sameStringSet(left, right) {
  return JSON.stringify(uniqueSorted(left)) === JSON.stringify(uniqueSorted(right));
}

function customerMessages(response) {
  return [
    ["draft message", response.draft?.outcome?.message],
    ["reviewed message", response.review?.outcome?.final_message],
    ["final message", response.final_message],
  ].filter(([, message]) => typeof message === "string");
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

function avoidsProhibitedPhrases(output, context) {
  const response = parseResponse(output);
  if (response === null) {
    return gradingResult(false, "Response is not a JSON object");
  }

  const configuredPhrases = stringArray(context.vars.expected?.prohibited_phrases) ?? [];
  const suppliedPolicies = Array.isArray(context.vars.policies) ? context.vars.policies : [];
  const policyIds = suppliedPolicies
    .map((policy) => policy?.policy_id)
    .filter((policyId) => typeof policyId === "string");
  const prohibitedPhrases = uniqueSorted([
    ...DEFAULT_PROHIBITED_PHRASES,
    ...configuredPhrases,
    ...policyIds,
  ]);

  const failures = [];
  for (const [label, message] of customerMessages(response)) {
    const normalizedMessage = message.toLocaleLowerCase("en-US");
    for (const phrase of prohibitedPhrases) {
      if (normalizedMessage.includes(phrase.toLocaleLowerCase("en-US"))) {
        failures.push(`${label} contains prohibited phrase: ${phrase}`);
      }
    }
  }

  return gradingResult(
    failures.length === 0,
    failures.length === 0
      ? "Customer-visible messages contain no prohibited phrases or internal policy IDs"
      : failures.join("; "),
  );
}

function hasExpectedPolicyReferences(output, context) {
  const response = parseResponse(output);
  const expectedPolicyIds = stringArray(context.vars.expected?.applicable_policy_ids);
  if (response === null || expectedPolicyIds === null) {
    return gradingResult(
      false,
      "Response is invalid or expected applicable_policy_ids are missing",
    );
  }

  const suppliedPolicies = Array.isArray(context.vars.policies) ? context.vars.policies : [];
  const suppliedPolicyIds = suppliedPolicies
    .map((policy) => policy?.policy_id)
    .filter((policyId) => typeof policyId === "string");
  const policyIds = stringArray(response.policy?.outcome?.applicable_policy_ids);
  const failures = [];

  if (policyIds === null) {
    failures.push("policy stage applicable_policy_ids are missing");
  } else {
    if (!sameStringSet(policyIds, expectedPolicyIds)) {
      failures.push(
        `policy references: expected ${JSON.stringify(expectedPolicyIds)}, received ${JSON.stringify(policyIds)}`,
      );
    }
    const unknownPolicyIds = policyIds.filter(
      (policyId) => !suppliedPolicyIds.includes(policyId),
    );
    if (unknownPolicyIds.length > 0) {
      failures.push(`policy stage references unknown policies: ${unknownPolicyIds.join(", ")}`);
    }
  }

  const draftPolicyIds = stringArray(response.draft?.outcome?.applied_policy_ids);
  if (response.draft !== null && response.draft !== undefined) {
    if (draftPolicyIds === null) {
      failures.push("draft applied_policy_ids are missing");
    } else if (policyIds !== null && !sameStringSet(draftPolicyIds, policyIds)) {
      failures.push("draft policy references do not match the policy decision");
    }
  }

  const review = response.review?.outcome;
  const reviewPolicyIds = stringArray(review?.applied_policy_ids);
  if (response.review !== null && response.review !== undefined) {
    if (reviewPolicyIds === null) {
      failures.push("review applied_policy_ids are missing");
    } else if (
      review?.verdict !== "escalate" &&
      policyIds !== null &&
      !sameStringSet(reviewPolicyIds, policyIds)
    ) {
      failures.push("review policy references do not match the policy decision");
    } else if (
      reviewPolicyIds.some((policyId) => !suppliedPolicyIds.includes(policyId))
    ) {
      failures.push("review references an unknown policy");
    }
  }

  return gradingResult(
    failures.length === 0,
    failures.length === 0
      ? "Policy references match the golden expectation and remain consistent"
      : failures.join("; "),
  );
}

function satisfiesResponseConstraints(output, context) {
  const response = parseResponse(output);
  if (response === null) {
    return gradingResult(false, "Response is not a JSON object");
  }

  const configuredLimit = context.vars.expected?.max_final_message_characters;
  const maxCharacters =
    Number.isInteger(configuredLimit) && configuredLimit > 0
      ? configuredLimit
      : DEFAULT_MAX_MESSAGE_CHARACTERS;
  const failures = [];

  for (const [label, message] of customerMessages(response)) {
    if (message.length === 0 || message !== message.trim()) {
      failures.push(`${label} must be non-empty and trimmed`);
    }
    if (message.length > maxCharacters) {
      failures.push(`${label} exceeds ${maxCharacters} characters`);
    }
    if (message.includes("```")) {
      failures.push(`${label} must not contain Markdown fences`);
    }
  }

  if (response.requires_escalation) {
    if (response.final_message !== null) {
      failures.push("escalated results must not contain a final message");
    }
    if (response.review?.outcome?.verdict !== undefined && response.review.outcome.verdict !== "escalate") {
      failures.push("an executed review must escalate when the workflow escalates");
    }
  } else {
    if (response.draft === null || typeof response.draft !== "object") {
      failures.push("non-escalated results require a draft");
    }
    if (response.review === null || typeof response.review !== "object") {
      failures.push("non-escalated results require a review");
    }
  }

  return gradingResult(
    failures.length === 0,
    failures.length === 0
      ? "Customer-visible messages satisfy length, formatting, and escalation constraints"
      : failures.join("; "),
  );
}

function matchesProviderTriageStrategy(output, context) {
  const response = parseResponse(output);
  const providerLabel = context.provider?.label;
  const expected = TRIAGE_PROVIDER_EXPECTATIONS[providerLabel];
  if (response === null || expected === undefined) {
    return gradingResult(
      false,
      "Response is invalid or the comparison provider label is unknown",
    );
  }

  const metadata = response.triage?.metadata;
  const matches =
    metadata?.strategy === expected.strategy &&
    metadata?.prompt_version === expected.version;
  return gradingResult(
    matches,
    matches
      ? `Triage used ${expected.strategy} at ${expected.version}`
      : `Expected ${expected.strategy} at ${expected.version}, received ${metadata?.strategy} at ${metadata?.prompt_version}`,
  );
}

module.exports = {
  avoidsProhibitedPhrases,
  hasExpectedPolicyReferences,
  hasReviewedFinalMessage,
  hasStageMetadata,
  matchesExpectedValues,
  matchesProviderTriageStrategy,
  satisfiesResponseConstraints,
};
