# Prompt-version case study: cancellation urgency

## Problem

The triage strategy comparison found that shipment status was influencing urgency for
cancellation requests. The policy decision legitimately depends on whether an order
has shipped, but the operational urgency rubric does not: a routine cancellation is
low urgency unless the ticket contains an independent safety, fraud, or time-critical
signal.

In evaluation `eval-QlL-2026-09-23T02:32:11`, zero-shot `1.3.0`, few-shot `1.4.0`, and
many-shot `1.5.0` each failed the cancellation-after-shipment case by returning medium
instead of low urgency. The comparison also showed more provider-format errors in the
larger-example variants, so adding examples alone was not treated as a reliable fix.

## Change

Triage `1.6.0` made one focused zero-shot change: it explicitly separated cancellation
eligibility from urgency. The version retained the existing schema, temperature,
token budget, XML-delimited input, and broader urgency rubric. Its metadata changelog
records the behavior change while preserving every prior version for reproduction.

```text
1.3.0 zero-shot: calibrated general urgency rubric
1.4.0 few-shot:  urgency boundary examples
1.5.0 many-shot: supported-intent examples
1.6.0 zero-shot: shipment state affects eligibility, not urgency
```

## Targeted result

Evaluation `eval-2Aj-2026-09-23T02:48:01` reran the failing cancellation case against
all three strategies:

| Prompt | Strategy | Triage input tokens | Result |
| --- | --- | ---: | --- |
| `1.6.0` | zero-shot | 427 | Passed: `cancellation`, `low` |
| `1.4.0` | few-shot | 605 | Failed: returned `medium` |
| `1.5.0` | many-shot | 1,009 | Failed: returned `medium` |

The final full-workflow golden evaluation later passed all 12 cases with `1.6.0` as
the default zero-shot prompt. The project keeps the older versions selectable so the
behavior and token tradeoff can be reproduced through the public API.

## Why this change was adopted

- It addressed the minimized failing behavior instead of broadly rewriting the task.
- It used fewer triage input tokens than the example-heavy variants in the targeted
  run.
- It preserved the strict output contract and did not require application-code
  changes.
- It passed the later end-to-end regression and adversarial gates.

## Lesson

Examples are not automatically better than explicit decision boundaries. The most
useful prompt change was a precise distinction between two concepts the model had
conflated. Versioned prompts, a selectable runtime strategy, and a minimized regression
case made that conclusion inspectable rather than anecdotal.
