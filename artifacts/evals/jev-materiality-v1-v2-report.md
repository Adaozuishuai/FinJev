# FinJev materiality v1 → v2 comparison

## Result

Materiality v2 materially improves the development baseline, but it is not yet
production evidence because the 49-record reference uses shared AI-assisted
core labels and covers only three issuer-document-period groups.

| Metric | v1 | v2 semantic only | v2 hybrid | Hybrid vs v1 |
| --- | ---: | ---: | ---: | ---: |
| Accuracy | 48.98% | 71.43% | 79.59% | +30.61 pp |
| Macro-F1, supported classes | 50.88% | 74.11% | 88.57% | +37.69 pp |
| High-value recall | 68.75% | 71.88% | 75.00% | +6.25 pp |
| Critical recall | 50.00% | 50.00% | 100.00% | +50.00 pp |
| Critical precision | 50.00% | 100.00% | 100.00% | +50.00 pp |
| Critical severe-undercall rate | 0.00% | 0.00% | 0.00% | unchanged |

The semantic-only column isolates the effect of giving Jev explicit materiality
definitions. The hybrid column additionally applies deterministic floors. This
separation prevents rule gains from being misreported as model gains.

## V2 class performance

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Medium | 83.33% | 88.24% | 85.71% | 17 |
| High | 94.74% | 69.23% | 80.00% | 26 |
| Critical | 100.00% | 100.00% | 100.00% | 6 |

There are no `low` reference examples, so low precision/recall cannot be
meaningfully estimated. High recall remains the main weakness: 8 of 26 high
records are still undercalled.

## Rule contribution

- No floor: 33 records
- High floor: 10 records
- Critical floor: 6 records
- Critical triggers correctly covered all six critical reference records
- The rule engine does not infer absent denominators or reduce a Jev level

Implemented trigger families include non-standard audit opinions, going-concern
uncertainty, material control weakness, revenue KAM coverage over 80%, guarantee
exposure over 5% of equity, project delay, negative operating cash flow, major
contract-asset or short-term-debt growth, and margin compression.

## Cost and latency trade-off

| Measure | v1 | v2 | Change |
| --- | ---: | ---: | ---: |
| Input tokens | 56,243 | 78,627 | +39.80% |
| Output tokens | 11,848 | 11,849 | approximately unchanged |
| Total tokens | 68,091 | 90,476 | +32.88% |
| Mean latency | 914.88 ms | 715.39 ms | not directly attributable |
| P95 latency | 1,616 ms | 995 ms | not directly attributable |

The lower observed v2 latency should not be interpreted as a rubric improvement;
the runs occurred at different times and the sample is small. The token increase
is structural because v2 sends richer criteria and structured numeric facts.

## Remaining risks

1. The reference labels are not independent gold labels.
2. `high` recall is only 69.23%, below a reasonable safety target for research
   triage.
3. Standard unqualified audit-opinion records have inconsistent reference
   materiality (`medium` and `high`) and need human policy clarification.
4. Event-type output changed slightly between runs (85.71% to 83.67%), showing
   normal model/run sensitivity and possible interaction inside one multi-question
   request.
5. There are no low-materiality examples, so the four-class benchmark is not
   distributionally complete.

## Recommendation

Keep v2 opt-in. Do not replace the default v1 path until an independent holdout
contains more issuers and explicit low examples. The next data task is to add
and independently review at least 50-100 records emphasizing `low`, `medium`,
standard audit opinions, related-party/M&A boundaries, and high-but-not-critical
events. Then rerun the same frozen v1/v2 commands without changing rules.
