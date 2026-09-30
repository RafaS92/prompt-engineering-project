# Cost and quality tradeoffs

## Production choice

The release defaults to one policy-decision sample. Three or five samples remain
available for experiments, but the recorded self-consistency study found higher cost
and token use without an accuracy improvement.

| Samples | Policy accuracy | Escalation accuracy | Avg. latency | Avg. tokens per completed trial | Avg. cost per completed trial |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 79.17% | 79.17% | 3,485 ms | 2,183 | $0.002371 |
| 3 | 70.83% | 70.83% | 4,299 ms | 4,355 | $0.004471 |
| 5 | 70.83% | 70.83% | 3,947 ms | 6,471 | $0.006496 |

The experiment used eight ambiguous cases, three trials per case and configuration,
and `gpt-5.4-mini-2026-03-17`. It produced no case recovered by consensus. Higher
sampling added disagreement and ties, and five samples used almost three times the
average tokens of one sample.

## Why latency is not monotonic

Five samples did not have a higher observed average latency than three samples. The
workflow executes samples sequentially, but failed workflows omit some downstream
work and partial token data. Provider variability and the small completed-trial set
also affect the mean. Token and estimated-cost growth provide the clearer scaling
signal here.

## Pricing assumptions

The summarizer uses exact model identifiers and the checked-in rate table at
`evaluations/pricing/model-pricing.json`. The recorded rates were:

- input: $0.75 per million tokens;
- output: $4.50 per million tokens; and
- all input priced as uncached.

These are experiment estimates, not billing records. Failed workflows do not expose
partial stage usage, so totals are observed lower bounds. Pricing must be reviewed
whenever the configured model changes.

## Other quality safeguards

The lower-cost choice does not remove safety layers. Every request still uses:

- injection detection before normal processing;
- deterministic policy-reference and escalation checks;
- one independently validated policy decision;
- leakage-canary scanning on every provider response; and
- a separate response-review stage before a message is returned.

The release therefore reduces redundant sampling, not validation depth.

## When to reconsider

Revisit the default only when a larger evaluation demonstrates that additional samples
recover meaningful failures at an acceptable latency and cost. The comparison should
report workflow failures, disagreements, ties, tokens, and costs rather than accuracy
alone. The reproduction method and detailed results are in
[Policy Self-Consistency Evaluation](self-consistency.md).
