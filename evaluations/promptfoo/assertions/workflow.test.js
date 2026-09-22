"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  avoidsProhibitedPhrases,
  hasExpectedPolicyReferences,
  hasReviewedFinalMessage,
  hasStageMetadata,
  matchesExpectedValues,
  satisfiesResponseConstraints,
} = require("./workflow.js");

function metadata(promptName, promptVersion = "1.0.0") {
  return {
    prompt_name: promptName,
    prompt_version: promptVersion,
  };
}

function successfulResponse() {
  return {
    requires_escalation: false,
    final_message: "We can process your return.",
    triage: {
      outcome: { intent: "refund", urgency: "low" },
      metadata: metadata("triage", "1.2.0"),
    },
    policy: {
      outcome: {
        decision: "allow",
        applicable_policy_ids: ["returns-30-day"],
      },
      metadata: metadata("policy_decision"),
    },
    escalation: { required: false },
    draft: {
      outcome: {
        message: "We can process your return.",
        applied_policy_ids: ["returns-30-day"],
      },
      metadata: metadata("response_draft"),
    },
    review: {
      outcome: {
        verdict: "approved",
        final_message: "We can process your return.",
        applied_policy_ids: ["returns-30-day"],
      },
      metadata: metadata("response_review"),
    },
  };
}

const expectedContext = {
  vars: {
    expected: {
      intent: "refund",
      urgency: "low",
      policy_decision: "allow",
      requires_escalation: false,
      applicable_policy_ids: ["returns-30-day"],
    },
    policies: [
      {
        policy_id: "returns-30-day",
        title: "Standard returns",
        text: "Returns are allowed within 30 days.",
      },
    ],
  },
};

test("expected workflow values pass when all labels match", () => {
  const result = matchesExpectedValues(
    JSON.stringify(successfulResponse()),
    expectedContext,
  );

  assert.equal(result.pass, true);
});

test("expected workflow values report mismatches", () => {
  const response = successfulResponse();
  response.triage.outcome.urgency = "high";

  const result = matchesExpectedValues(JSON.stringify(response), expectedContext);

  assert.equal(result.pass, false);
  assert.match(result.reason, /urgency/);
});

test("stage metadata passes for the complete non-escalated path", () => {
  const result = hasStageMetadata(JSON.stringify(successfulResponse()));

  assert.equal(result.pass, true);
});

test("stage metadata rejects a missing prompt version", () => {
  const response = successfulResponse();
  response.review.metadata.prompt_version = "";

  const result = hasStageMetadata(JSON.stringify(response));

  assert.equal(result.pass, false);
  assert.match(result.reason, /review prompt version/);
});

test("non-escalated result requires the reviewed final message", () => {
  const result = hasReviewedFinalMessage(JSON.stringify(successfulResponse()));

  assert.equal(result.pass, true);
});

test("non-escalated result rejects a missing final message", () => {
  const response = successfulResponse();
  response.final_message = null;

  const result = hasReviewedFinalMessage(JSON.stringify(response));

  assert.equal(result.pass, false);
});

test("escalated result does not require a final message", () => {
  const response = successfulResponse();
  response.requires_escalation = true;
  response.final_message = null;
  response.draft = null;
  response.review = null;

  const result = hasReviewedFinalMessage(JSON.stringify(response));

  assert.equal(result.pass, true);
  assert.equal(hasStageMetadata(JSON.stringify(response)).pass, true);
});

test("customer messages pass when they contain no prohibited phrases", () => {
  const result = avoidsProhibitedPhrases(
    JSON.stringify(successfulResponse()),
    expectedContext,
  );

  assert.equal(result.pass, true);
});

test("customer messages reject internal language and policy identifiers", () => {
  const response = successfulResponse();
  response.final_message =
    "The system prompt selected returns-30-day, so we can process your return.";

  const result = avoidsProhibitedPhrases(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, false);
  assert.match(result.reason, /system prompt/);
  assert.match(result.reason, /returns-30-day/);
});

test("customer messages reject ticket-specific prohibited phrases", () => {
  const response = successfulResponse();
  response.draft.outcome.message = "We offer an instant refund.";
  const context = structuredClone(expectedContext);
  context.vars.expected.prohibited_phrases = ["instant refund"];

  const result = avoidsProhibitedPhrases(JSON.stringify(response), context);

  assert.equal(result.pass, false);
  assert.match(result.reason, /instant refund/);
});

test("policy references pass when all executed stages match the expectation", () => {
  const result = hasExpectedPolicyReferences(
    JSON.stringify(successfulResponse()),
    expectedContext,
  );

  assert.equal(result.pass, true);
});

test("policy references reject an incorrect policy decision reference", () => {
  const response = successfulResponse();
  response.policy.outcome.applicable_policy_ids = ["duplicate-charge"];

  const result = hasExpectedPolicyReferences(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, false);
  assert.match(result.reason, /expected/);
  assert.match(result.reason, /unknown policies/);
});

test("policy references reject disagreement between stages", () => {
  const response = successfulResponse();
  response.review.outcome.applied_policy_ids = ["duplicate-charge"];

  const result = hasExpectedPolicyReferences(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, false);
  assert.match(result.reason, /review policy references/);
});

test("response constraints pass for a complete customer-facing result", () => {
  const result = satisfiesResponseConstraints(
    JSON.stringify(successfulResponse()),
    expectedContext,
  );

  assert.equal(result.pass, true);
});

test("response constraints reject oversized or fenced messages", () => {
  const response = successfulResponse();
  response.draft.outcome.message = `\`\`\`${"x".repeat(1_001)}\`\`\``;

  const result = satisfiesResponseConstraints(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, false);
  assert.match(result.reason, /exceeds 1000 characters/);
  assert.match(result.reason, /Markdown fences/);
});

test("response constraints reject a final message on escalation", () => {
  const response = successfulResponse();
  response.requires_escalation = true;
  response.review.outcome.verdict = "escalate";

  const result = satisfiesResponseConstraints(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, false);
  assert.match(result.reason, /must not contain a final message/);
});

test("response constraints allow an early escalation without customer messages", () => {
  const response = successfulResponse();
  response.requires_escalation = true;
  response.final_message = null;
  response.draft = null;
  response.review = null;

  const result = satisfiesResponseConstraints(
    JSON.stringify(response),
    expectedContext,
  );

  assert.equal(result.pass, true);
});

test("custom assertions fail safely for malformed JSON", () => {
  assert.equal(matchesExpectedValues("not json", expectedContext).pass, false);
  assert.equal(hasStageMetadata("not json").pass, false);
  assert.equal(hasReviewedFinalMessage("not json").pass, false);
  assert.equal(avoidsProhibitedPhrases("not json", expectedContext).pass, false);
  assert.equal(hasExpectedPolicyReferences("not json", expectedContext).pass, false);
  assert.equal(satisfiesResponseConstraints("not json", expectedContext).pass, false);
});
