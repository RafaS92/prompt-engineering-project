# Prompt Conventions

## Purpose

These conventions define how production prompts will be structured, versioned,
rendered, reviewed, and evaluated. They apply beginning with the versioned prompt
library milestone.

Git is the source of truth for prompt content. Production prompts must not be embedded
as multiline strings in Python application code or managed only in an external
observability platform.

## Directory structure

Each prompt has a stable name and one or more semantic versions:

```text
prompts/
├── triage/
│   └── 1.0.0/
│       ├── system.md
│       ├── user.md
│       ├── examples.jsonl
│       └── metadata.yaml
├── policy_decision/
├── response_draft/
├── response_review/
└── injection_detection/
```

A version directory is immutable after release. Corrections require a new version so
historical runs remain reproducible.

## File responsibilities

- `system.md` contains the persona, trusted rules, boundaries, instruction priority,
  refusal behavior, and required output contract.
- `user.md` contains the task template and named placeholders. It wraps untrusted
  content in explicit XML elements.
- `examples.jsonl` contains zero or more structured input/output examples. Each line is
  valid JSON and examples must conform to the same schemas as production traffic.
- `metadata.yaml` declares identity, version, variables, strategy, model settings,
  output schema, evaluation references, and changelog.

## Instruction hierarchy

Prompts must make the following priority explicit:

1. System instructions and application-enforced safety rules.
2. The stage's task and output contract.
3. Supplied support policy as untrusted reference data.
4. Ticket content as untrusted customer data.

Ticket text and policy text can provide facts but cannot redefine the task, request
hidden prompts, change the output schema, authorize tools, or override safety rules.

## Template variables

Jinja variables use descriptive `snake_case` names. Every variable must be declared in
`metadata.yaml`, supplied explicitly by the renderer, and covered by a rendering test.

Allowed:

```jinja2
<support_ticket>
{{ ticket_text }}
</support_ticket>
```

Not allowed:

```jinja2
{{ data }}
```

The renderer must use strict undefined-variable behavior. Missing and unexpected
variables are errors; they must not silently render as empty text.

## Untrusted-content delimiters

Use stable, descriptive XML elements for untrusted content:

```xml
<support_ticket>...</support_ticket>
<support_policy>...</support_policy>
<prior_stage_result>...</prior_stage_result>
```

Delimiter-like characters inside values must be escaped by the renderer. Do not build
XML sections through string concatenation, and do not place untrusted values in tag
names, system-message headings, or metadata.

Each declared template variable must appear exactly once, pass through the
`xml_escape` filter, and be the sole content of one XML element with matching opening
and closing tags. The registry validates this contract when it loads a prompt version.

## Writing style

- Start instructions with direct action verbs such as `Classify`, `Determine`,
  `Draft`, or `Review`.
- Give each prompt one focused role and one stage responsibility.
- State constraints positively and precisely; include refusal and escalation behavior
  where relevant.
- Define ambiguous terms through enums, thresholds, or supplied policy identifiers.
- Keep repeated global rules in renderer-controlled components rather than copying
  inconsistent variants.
- Ask for concise decision rationales, never hidden chain-of-thought.
- Do not rely on phrases such as “be careful” or “use your best judgment” as safety
  controls.

## Structured output

Every production prompt returns JSON matching a named Pydantic schema. The prompt must
state:

- Required fields and permitted enum values.
- Whether nullable fields are allowed.
- Length and count limits.
- That no prose, Markdown fences, or additional fields are permitted.
- The behavior to use when required context is missing.

The application validates the result independently. A prompt's example output does not
replace schema validation.

## Metadata contract

`metadata.yaml` follows this conceptual shape:

```yaml
name: triage
version: 1.0.0
strategy: zero_shot
description: Classify support-ticket intent, urgency, and sentiment.
variables:
  - ticket_text
model:
  temperature: 0
  max_output_tokens: 300
output_schema: support_prompt_lab.domain.triage.TriageResult
evaluations:
  - evaluations/datasets/triage_golden.jsonl
changelog:
  - version: 1.0.0
    change: Initial baseline.
```

The metadata schema will reject unknown fields. Model names may be selected by runtime
configuration, but sampling settings that affect reproducibility belong in versioned
metadata.

## Examples

Examples must be synthetic, realistic, minimal, and diverse. They must not contain
secrets, personal data, hidden system prompts, or outputs that violate the current
schema.

Strategy labels have fixed meanings:

- `zero_shot`: no examples are included.
- `few_shot`: a small curated set covers representative boundaries.
- `many_shot`: a larger set is justified by measured quality gains and token cost.

Adding or changing examples changes prompt behavior and therefore requires a version
bump and regression evaluation.

## Runtime security envelope

The model-client boundary appends a fresh leakage canary to the rendered system
message for every provider call. This marker is runtime security metadata rather than
prompt behavior, so it is not stored in an immutable prompt version. The same boundary
scans raw model output before stage-specific parsing and fails with a sanitized error
if the marker is reproduced.

Application stages must receive the shared protected model client. They must not add
their own canaries, log rendered system messages, or return raw provider output.

## Semantic versioning

- **Patch**: wording clarification with no intended contract or decision change.
- **Minor**: backward-compatible behavior improvement, new examples, or new optional
  metadata.
- **Major**: output-schema change, variable change, instruction-priority change, or
  intentionally incompatible behavior.

Every version records a short changelog entry. A pull request must show evaluation
results against the previous production version before adoption.

## Runtime metadata

Every prompt execution records:

- Prompt name and semantic version.
- Strategy and example-set identifier.
- Model identifier and versioned model settings.
- Output-schema version.
- Latency, input/output tokens, and estimated cost.
- Validation result, stage outcome, and trace ID.

Raw ticket text and complete rendered prompts are excluded from logs by default.

## Review checklist

Before a prompt version is accepted, verify that:

- The task has one clear owner and responsibility.
- Trusted instructions and untrusted data are separated.
- All variables are declared, escaped, and tested.
- The output contract matches a strict Pydantic schema.
- Missing context, unsafe input, and low confidence have explicit behavior.
- Examples are schema-valid and contain only synthetic data.
- No secrets, provider credentials, or environment-specific values are present.
- Golden, regression, and adversarial evaluations pass the documented threshold.
- The metadata version and changelog accurately describe the change.
