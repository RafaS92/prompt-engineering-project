"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  hasReviewedFinalMessage,
  hasStageMetadata,
  matchesExpectedValues,
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
      outcome: { decision: "allow" },
      metadata: metadata("policy_decision"),
    },
    escalation: { required: false },
    draft: {
      outcome: { message: "We can process your return." },
      metadata: metadata("response_draft"),
    },
    review: {
      outcome: {
        verdict: "approved",
        final_message: "We can process your return.",
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
    },
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

test("custom assertions fail safely for malformed JSON", () => {
  assert.equal(matchesExpectedValues("not json", expectedContext).pass, false);
  assert.equal(hasStageMetadata("not json").pass, false);
  assert.equal(hasReviewedFinalMessage("not json").pass, false);
});
