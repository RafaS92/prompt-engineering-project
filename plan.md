# SupportPrompt Lab — Production-Style Prompt Engineering Portfolio

## Summary

Build a FastAPI service that processes fictional e-commerce support tickets through a multi-step prompt workflow:

1. Detect unsafe or out-of-scope input.
2. Classify intent, urgency, and sentiment.
3. Apply supplied support policies.
4. Decide whether human escalation is required.
5. Draft a policy-compliant response.
6. Review and revise the response.
7. Return validated, structured JSON.

The project will demonstrate the major Chapter 5 concepts while measuring classification quality, policy compliance, injection resistance, schema validity, latency, token usage, and cost.

## Free and Open-Source Tooling

- **Promptfoo** will run prompt comparisons, assertions, regression evaluations, and adversarial red-team tests against the FastAPI endpoint. It is open source and supports HTTP targets and CI/CD integration. Some tests still incur OpenAI API charges. See the [Promptfoo documentation](https://www.promptfoo.dev/docs/red-team/quickstart/).
- **Langfuse** will be an optional Docker profile for LLM tracing, experiment comparison, token/cost monitoring, and evaluation dashboards. Its core capabilities are MIT-licensed and self-hostable without usage limits. See the [Langfuse open-source details](https://langfuse.com/handbook/chapters/open-source).
- **Pydantic** will define request, response, prompt metadata, and model-output contracts.
- **Jinja2** will render versioned prompt templates and validate required variables.
- **pytest** will cover deterministic unit, contract, integration, and security tests.
- **uv** will manage Python versions, dependencies, virtual environments, and lockfiles.
- **Ruff** and **mypy** will enforce formatting, linting, and static typing.
- **pre-commit** will run local quality checks before commits.
- **GitHub Actions** will run tests, Promptfoo regressions, security checks, and Docker builds.
- **Docker Compose** will run FastAPI, PostgreSQL, and the optional Langfuse stack locally.
- **OpenAPI/Swagger UI** will serve as the MVP's interactive interface.

Git remains the source of truth for prompts. Langfuse receives prompt names, versions, and trace metadata but does not replace the repository's prompt library.

## Architecture and Interfaces

```text
support-prompt-lab/
├── app/
│   ├── api/                 # FastAPI routes and schemas
│   ├── application/         # Prompt-chain orchestration
│   ├── domain/              # Tickets, policies, decisions, evaluations
│   ├── infrastructure/      # OpenAI, PostgreSQL, Langfuse adapters
│   ├── guardrails/          # Injection, leakage, input/output checks
│   └── observability/       # Tracing, tokens, latency, and cost
├── prompts/
│   ├── triage/
│   ├── policy_decision/
│   ├── response_draft/
│   ├── response_review/
│   └── injection_detection/
├── evaluations/
│   ├── datasets/            # Versioned golden and adversarial cases
│   ├── promptfoo/           # Promptfoo configs and assertions
│   ├── rubrics/
│   └── reports/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── security/
├── docs/
├── migrations/
└── docker-compose.yml
```

Each prompt version contains:

- `system.md`: persona, trusted rules, boundaries, and instruction hierarchy.
- `user.md`: task template with untrusted content inside XML delimiters.
- `examples.jsonl`: zero-shot, few-shot, or many-shot examples.
- `metadata.yaml`: semantic version, variables, strategy, model settings, output schema, and changelog.

Primary endpoints:

- `POST /v1/tickets/analyze`: execute the complete prompt chain.
- `POST /v1/prompts/compare`: compare prompt versions on one case.
- `POST /v1/evaluations/run`: start a named evaluation suite.
- `GET /v1/runs/{run_id}`: retrieve sanitized execution and metric data.
- `GET /health` and `GET /ready`: operational checks.

Promptfoo will call the public API as an external consumer, ensuring evaluations test the whole application rather than isolated prompt functions.

## Prompt Engineering Demonstrations

- Separate system and user messages with direct action verbs, explicit constraints, XML delimiters, and required JSON schemas.
- Compare zero-shot, few-shot, and many-shot triage variants on the same dataset.
- Implement conditional behavior for missing context, unsupported requests, unsafe content, policy exceptions, low confidence, and required escalation.
- Decompose the workflow into triage, policy analysis, drafting, and review prompts.
- Use focused personas: triage specialist, policy analyst, empathetic support writer, and compliance reviewer.
- Request internal deliberation for complex cases but return only concise decision rationales and policy identifiers—not hidden chain-of-thought.
- Implement self-consistency through multiple independent structured decisions followed by deterministic majority voting.
- Treat ticket and policy text as untrusted input through instruction hierarchy, delimiter isolation, length limits, injection checks, schema validation, and leakage canaries.
- Trace prompt name/version, model settings, latency, tokens, estimated cost, outcome, and trace ID. Raw ticket logging remains disabled by default.

## Milestones

### 1. Project foundation

- Initialize Git, `uv`, FastAPI, Pydantic, PostgreSQL, Alembic, pytest, Ruff, mypy, pre-commit, Docker Compose, and GitHub Actions.
- Add architecture, threat-model, and prompt-convention documentation.
- Complete when the containerized API, database, health checks, and CI pipeline pass.

### 2. Versioned prompt library

- Implement the Jinja2 prompt renderer, metadata schema, registry, semantic-version rules, and zero-/few-/many-shot variants.
- Test template variables, delimiters, metadata, and prompt-loading failures.
- Complete when application code contains no embedded production prompts.

### 3. Structured support workflow

- Implement typed triage, policy-decision, response-drafting, and response-review stages.
- Add conditional escalation and out-of-scope handling.
- Complete when `/v1/tickets/analyze` returns a schema-valid result with stage and prompt-version metadata.

### 4. Promptfoo evaluation baseline

- Configure Promptfoo to call the FastAPI API.
- Add golden datasets and assertions for JSON validity, intent, urgency, escalation, prohibited phrases, policy references, and response constraints.
- Compare zero-shot, few-shot, and many-shot strategies.
- Complete when a single command generates HTML and JSON comparison reports.

### 5. Reasoning and self-consistency

- Add configurable independent sampling for ambiguous policy decisions.
- Implement deterministic voting, tie handling, and disagreement reporting.
- Compare quality gains against additional latency, tokens, and cost.
- Complete when evaluation reports show when self-consistency helps and when it is wasteful.

### 6. Defensive prompt engineering

- Add injection detection, instruction isolation, leakage canaries, output validation, safe refusal, and human escalation.
- Use Promptfoo red-team tests for instruction overrides, fake system messages, jailbreaks, prompt extraction, delimiter attacks, and malicious policy text.
- Complete when the security suite meets a documented pass threshold and failures are reproducible.

### 7. Optional Langfuse observability

- Instrument every prompt-chain stage with the Langfuse Python SDK.
- Associate traces with Git-controlled prompt versions and record latency, tokens, cost, errors, and evaluation scores.
- Provide a lightweight default mode without Langfuse and an opt-in Docker profile with it.
- Complete when the same request works in both modes and traced runs appear in the self-hosted dashboard.

### 8. Portfolio release

- Publish architecture diagrams, API examples, evaluation reports, prompt-version case studies, security findings, and cost/quality tradeoffs.
- Add seeded synthetic tickets, environment templates, one-command startup, and a demonstration script.
- Complete when a reviewer can clone the repository, run the API, execute Promptfoo evaluations, and inspect optional Langfuse traces.

## Test and Acceptance Scenarios

- Refund, damaged-order, delivery-delay, cancellation, billing, and account-access tickets.
- Missing details, conflicting claims, unsupported requests, and mandatory escalation.
- Correct handling of strict length, tone, and JSON requirements.
- Invalid or truncated model responses.
- Prompt injection and leakage attacks inside ticket and policy fields.
- Self-consistency agreement, disagreement, ties, and partial failures.
- OpenAI timeout, authentication failure, rate limiting, and malformed responses.
- Prompt-version regressions across quality, latency, token usage, and cost.
- Operation with Langfuse enabled, disabled, or temporarily unavailable.
- Verification that secrets, complete system prompts, and unsanitized customer data are absent from logs.

## Assumptions

- The MVP uses fictional policies and synthetic tickets only.
- OpenAI is the sole live model provider, while deterministic fake clients support tests.
- Promptfoo introduces a Node-based CLI but requires no JavaScript application development.
- Langfuse is optional and cannot prevent the API from serving requests if unavailable.
- "Free tools" means the software can be used locally without a paid license; OpenAI model calls and model-driven red-team generation can still incur API charges.
- Authentication, queues, RAG, fine-tuning, and a custom frontend remain outside the MVP.
