# FinJev Jev development baseline v0.3

## Scope

- Dataset: `data/annotation_set_v0.3-dev-reference`
- Grain: 49 annual-report `metric_event` records from 3 issuer-document-period groups
- Runtime model returned by the API: `jev-1.13.0`
- Operation: `classify_financial_event`
- Status: development evidence only; not a gold benchmark

Claim and numeric checks were completed in both review packets. Core labels came
from a shared AI-assisted prefill, so apparent reviewer agreement is not an
independent reliability measurement.

## Execution integrity

- Successful requests: 49 / 49
- API errors: 0
- Retries required: 0
- Input tokens: 56,243
- Output tokens: 11,848
- Mean latency: 914.88 ms
- P95 latency: 1,616 ms

## Baseline metrics

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Event-type accuracy | 85.71% | Promising development result, not generalization evidence |
| Event-type Macro-F1, supported classes | 84.60% | Seven category errors remain |
| Materiality accuracy | 48.98% | Not acceptable for autonomous use |
| Materiality Macro-F1, supported classes | 50.51% | High/medium separation is unstable |
| High-value recall (`high` + `critical`) | 62.50% | 12 of 32 high-value records were undercalled below high |
| Critical recall | 50.00% | 3 of 6 critical records were predicted high |
| Critical severe-undercall rate | 0.00% | No critical record was reduced to medium or low |

## Event-type errors

| Record | Reference | Jev |
| --- | --- | --- |
| `my-annual-2025-p011-001` | accounting_policy | earnings |
| `futong-annual-2023-p015-001` | operations | earnings |
| `langfang-annual-2024-p006-001` | capital_allocation | merger_acquisition |
| `langfang-annual-2024-p019-001` | related_party | merger_acquisition |
| `my-annual-2025-p081-001` | fundraising | operations |
| `my-annual-2025-p023-001` | operations | earnings |
| `my-annual-2025-p034-002` | related_party | guarantee |

Several errors are plausible taxonomy-boundary disputes rather than obvious
model failures. In particular, a completed related-party divestiture can be read
as either `related_party` or `merger_acquisition`. These cases need an explicit
primary-event precedence rule before the metric can be treated as stable.

## Materiality diagnosis

The current Jev question receives the event claim and evidence, but it does not
receive the annotation policy's quantitative thresholds or qualitative critical
triggers. The four materiality labels are passed as ordered score levels without
the dataset's detailed definitions. This is the leading explanation for the
weak 48.98% accuracy and 62.50% high-value recall.

Materiality should not be fixed by changing thresholds against these same 49
records alone. The next experiment should add versioned materiality criteria,
apply deterministic ratio/trigger rules when denominators are known, and rerun
without changing the reference labels. A larger issuer-group holdout is still
required before any production claim.

## Files

- Raw results: `artifacts/evals/jev-baseline-v0.3.jsonl`
- Machine-readable summary: `artifacts/evals/jev-baseline-v0.3.summary.json`
- Smoke results: `artifacts/evals/jev-smoke-v0.3.jsonl`
- Development reference manifest: `data/annotation_set_v0.3-dev-reference/manifest.json`
- Dataset quality report: `data/annotation_set_v0.3-dev-reference/validation_report.json`
