# Evaluation report

## Release decision

The recorded release evidence supports the default configuration:

- triage prompt `1.6.0` with the `zero_shot` strategy;
- policy-decision prompt `1.1.0`;
- `POLICY_DECISION_SAMPLE_COUNT=1`; and
- injection detection and leakage-canary protection enabled for every request.

The final golden and adversarial gates passed. The self-consistency study did not show
a quality gain from additional policy samples, so the lowest-cost configuration
remains the default.

## Recorded runs

All runs used `gpt-5.4-mini-2026-03-17` and synthetic data. Dates are UTC timestamps
embedded in Promptfoo evaluation IDs.

| Evaluation | Evaluation ID | Cases or trials | Result | Release interpretation |
| --- | --- | ---: | --- | --- |
| Golden workflow | `eval-vgy-2026-09-30T03:15:48` | 12 cases | 12 passed, 0 failed, 0 errors | Final functional gate passed |
| Security red team | `eval-wzX-2026-09-30T03:15:22` | 6 attacks | 6 passed, 0 failed, 0 errors | Final defensive gate passed |
| Policy self-consistency | `eval-T5f-2026-09-23T21:04:22` | 72 trials | 1, 3, and 5 samples compared | Keep one sample |
| Triage strategies | `eval-QlL-2026-09-23T02:32:11` | 36 runs | 30 passed, 3 failed, 3 errors | Exposed a cancellation-urgency regression |
| Cancellation regression | `eval-2Aj-2026-09-23T02:48:01` | 3 variants | `1.6.0` passed targeted case | Adopted corrected zero-shot prompt |

The strategy comparison predates injection detection and is diagnostic evidence, not
the final release gate. The later golden and security runs exercise the complete
current workflow.

## Golden workflow gate

The golden dataset contains six routine supported requests and six edge cases covering
refunds, damaged orders, delivery delays, cancellations, billing, account access,
missing information, out-of-scope requests, hard denials, conflicting claims, and
policy exceptions.

Each response is checked for:

- valid JSON and the expected end-to-end outcome;
- required prompt and model metadata;
- a reviewed final message when drafting is permitted;
- prohibited-phrase avoidance and response constraints; and
- policy identifiers that match the expected decision.

All 84 named assertions passed in the final 12-case run. The configured HTTP provider
performed one retry for `eval-cancel-allow`: the first attempt returned the sanitized
`review_output_invalid` error and the retry passed. This is retained as a model-output
reliability limitation, not hidden as deterministic success.

## Security gate

The fixed adversarial set covers instruction override, role impersonation, prompt
extraction, jailbreaks, delimiter attacks, and malicious policy text. All 30 named
assertions passed across six cases. The assertions require the expected category,
blocked execution path, attack-marker suppression, stage metadata, and the
application-owned safe refusal.

See [Defensive Prompt Evaluation](security-evaluation.md) for the threat-specific
method, pass threshold, and residual risk.

## Self-consistency results

Eight ambiguous policy cases ran three times at each sample count, producing 72 total
workflow trials.

| Policy samples | Workflow success | Policy accuracy | Escalation accuracy | Avg. latency | Observed tokens | Observed estimated cost |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 83.33% | 79.17% | 79.17% | 3,485 ms | 43,654 | $0.047429 |
| 3 | 75.00% | 70.83% | 70.83% | 4,299 ms | 78,384 | $0.080478 |
| 5 | 75.00% | 70.83% | 70.83% | 3,947 ms | 116,474 | $0.116928 |

Compared with one sample, three samples used 2.00 times the average tokens and 1.89
times the average estimated cost; five used 2.96 times the tokens and 2.74 times the
cost. Neither improved accuracy. Across the higher-sample comparisons there were zero
recoveries, eleven unchanged outcomes, three regressions, and two ties.

Token and cost totals are lower bounds because failed workflows do not expose partial
stage usage. Pricing assumes uncached input at the rates recorded in
`evaluations/pricing/model-pricing.json`.

See [Cost and Quality Tradeoffs](cost-quality.md) for the production decision.

## Reproduce the evidence

First run the API with a configured model. Then install the pinned Node dependency and
validate every Promptfoo configuration without making model calls:

```bash
npm ci
npm run eval:test-assertions
npm run eval:test-reports
npm run eval:validate
npm run eval:validate:triage
npm run eval:validate:policy-consensus
npm run eval:validate:red-team
```

Execute the golden and security gates:

```bash
npm run eval:baseline
npm run eval:red-team
```

The triage comparison uses the same API process:

```bash
npm run eval:compare:triage
```

The self-consistency experiment requires API processes on ports `8011`, `8013`, and
`8015` configured with sample counts one, three, and five. The README contains the
exact commands. Then run:

```bash
POLICY_EVAL_REPEAT=3 npm run eval:compare:policy-consensus
```

Live evaluations call OpenAI and can incur charges. Promptfoo writes raw JSON and HTML
reports to the ignored `evaluations/reports/` directory. They are deliberately not
committed because they contain complete synthetic prompts and responses; this
sanitized report publishes the release metrics, IDs, methods, and limitations.

## Interpretation limits

- Results describe one model snapshot, prompt set, dataset, and run date.
- A perfect fixed-suite score does not prove general safety or future model stability.
- The datasets are deliberately small and synthetic; they are regression gates rather
  than statistically representative production benchmarks.
- Every model, prompt, schema, guardrail, or harness change requires a fresh run.
