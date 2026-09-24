# Policy self-consistency evaluation

## Decision

Keep `POLICY_DECISION_SAMPLE_COUNT=1` as the production default.

The repeated evaluation did not find a case where three or five policy samples
improved the end-to-end result over one sample. Higher counts consumed substantially
more tokens, exposed more disagreement, and did not improve policy or escalation
accuracy.

## Method

- Model: `gpt-5.4-mini-2026-03-17`
- Dataset: eight ambiguous policy cases
- Configurations: one, three, and five policy samples
- Trials: three per case and configuration
- Total workflow evaluations: 72
- Promptfoo evaluation: `eval-T5f-2026-09-23T21:04:22`

Every result is classified relative to the matching one-sample case as
`recovered_by_consensus`, `unchanged`, `regressed`, or `tie`. Workflow failures count
against end-to-end accuracy rather than being omitted.

## Results

| Samples | Workflow success | Policy accuracy | Escalation accuracy | Observed tokens | Observed estimated cost |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 83.33% | 79.17% | 79.17% | 43,654 | $0.047429 |
| 3 | 75.00% | 70.83% | 70.83% | 78,384 | $0.080478 |
| 5 | 75.00% | 70.83% | 70.83% | 116,474 | $0.116928 |

Across the sixteen higher-sample case comparisons, the experiment produced zero
recoveries, eleven unchanged outcomes, three regressions, and two ties. Five samples
also produced more disagreement without improving final accuracy.

Sixteen trials returned `review_output_invalid`. Failed workflows do not expose stage
usage, so token and cost totals are observed lower bounds. This failure mode should be
addressed independently; it does not provide evidence that additional policy samples
help.

## Reproduction

Start API instances configured with policy sample counts one, three, and five as
documented in the project README, then run:

```bash
POLICY_EVAL_REPEAT=3 npm run eval:compare:policy-consensus
```

The command writes the raw Promptfoo report and generates JSON and Markdown summaries
under `evaluations/reports/`. It runs the summarizer even when Promptfoo reports failed
or errored trials, while preserving Promptfoo's non-zero exit status.
