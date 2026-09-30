# API examples

The interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`
after startup. These examples use only synthetic tickets and fictional policies.

## Analyze a supported refund

```bash
curl --fail-with-body \
  --request POST \
  --header 'Content-Type: application/json' \
  --data @- \
  http://127.0.0.1:8000/v1/tickets/analyze <<'JSON'
{
  "ticket": {
    "ticket_id": "example-refund-001",
    "subject": "Refund an unused item",
    "message": "Order example-order-001 was delivered eight days ago. The item is unused and I would like a refund.",
    "order_id": "example-order-001"
  },
  "policies": [
    {
      "policy_id": "returns-30-day",
      "title": "Standard returns and refunds",
      "text": "Allow a refund for an unused item requested within 30 calendar days of delivery when the order identifier and delivery timing are provided. Deny requests made after 30 days. Escalate when the order identifier or delivery timing is missing."
    }
  ]
}
JSON
```

A successful response follows this shape. Token counts and natural-language fields
vary by run; the excerpt omits rationales and draft text for readability.

```json
{
  "ticket_id": "example-refund-001",
  "requires_escalation": false,
  "final_message": "Your unused item is eligible for return under the 30-day policy.",
  "injection_detection": {
    "outcome": {
      "detected": false,
      "categories": [],
      "rationale": "The input contains a support request rather than instructions."
    },
    "metadata": {
      "prompt_name": "injection_detection",
      "prompt_version": "1.0.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 850, "output_tokens": 35}
    }
  },
  "triage": {
    "outcome": {
      "intent": "refund",
      "urgency": "low",
      "sentiment": "neutral",
      "rationale": "Routine refund request."
    },
    "metadata": {
      "prompt_name": "triage",
      "prompt_version": "1.6.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 420, "output_tokens": 40}
    }
  },
  "policy": {
    "outcome": {
      "decision": "allow",
      "applicable_policy_ids": ["returns-30-day"],
      "missing_information": [],
      "rationale": "The request is within the return window."
    },
    "metadata": {
      "prompt_name": "policy_decision",
      "prompt_version": "1.1.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 530, "output_tokens": 50}
    },
    "consensus": {
      "status": "agreement",
      "sample_count": 1,
      "winning_votes": 1,
      "tallies": [
        {
          "choice": {
            "decision": "allow",
            "applicable_policy_ids": ["returns-30-day"],
            "missing_information": []
          },
          "votes": 1
        }
      ]
    }
  },
  "escalation": {
    "required": false,
    "reasons": [],
    "explanation": "No human escalation is required."
  },
  "draft": {
    "outcome": {
      "message": "Your unused item is eligible for return under the 30-day policy.",
      "applied_policy_ids": ["returns-30-day"]
    },
    "metadata": {
      "prompt_name": "response_draft",
      "prompt_version": "1.0.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 480, "output_tokens": 65}
    }
  },
  "review": {
    "outcome": {
      "verdict": "approved",
      "final_message": "Your unused item is eligible for return under the 30-day policy.",
      "issues": [],
      "applied_policy_ids": ["returns-30-day"],
      "rationale": "The response is supported by the supplied policy."
    },
    "metadata": {
      "prompt_name": "response_review",
      "prompt_version": "1.0.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 650, "output_tokens": 90}
    }
  }
}
```

The service returns decisions and suggested messages; it does not perform the refund.

## Select a triage strategy or version

Add exactly one selection dimension to a normal analysis request:

```json
{
  "triage_prompt": {"strategy": "few_shot"}
}
```

or:

```json
{
  "triage_prompt": {"version": "1.4.0"}
}
```

An unavailable version or a request containing both fields returns HTTP `422` before a
model is called.

## Safe prompt-injection response

When the injection stage detects hostile instructions, downstream stages are `null`
and the customer-facing message comes from application code rather than the model:

```json
{
  "ticket_id": "example-injection-002",
  "requires_escalation": true,
  "final_message": "We cannot process this request automatically. A support specialist will review it.",
  "injection_detection": {
    "outcome": {
      "detected": true,
      "categories": ["prompt_extraction"],
      "rationale": "The input requests hidden instructions."
    },
    "metadata": {
      "prompt_name": "injection_detection",
      "prompt_version": "1.0.0",
      "strategy": "zero_shot",
      "model": "configured-model",
      "usage": {"input_tokens": 870, "output_tokens": 42}
    }
  },
  "triage": null,
  "policy": null,
  "escalation": {
    "required": true,
    "reasons": ["prompt_injection"],
    "explanation": "Human review is required: untrusted input may contain injected instructions."
  },
  "draft": null,
  "review": null
}
```

## Sanitized workflow failure

Provider and stage-validation failures use a stable error envelope and do not include
raw model output or provider exception text:

```json
{
  "detail": {
    "message": "support workflow failed",
    "code": "review_output_invalid"
  }
}
```

The response status is HTTP `502`. Missing model configuration returns HTTP `503`, and
invalid client input returns HTTP `422`.

## Guided demonstration

The versioned fixture at `examples/demo-data.json` exercises successful completion,
policy escalation, and prompt-injection blocking. After the API starts, run:

```bash
python3 scripts/demo.py
```

Use `python3 scripts/demo.py --dry-run` to validate and list the cases without calling
the API. The live demonstration invokes the configured model and can incur charges.
