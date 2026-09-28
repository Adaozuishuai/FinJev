# FinJev V0.2 Architecture

## Positioning

FinJev is a Financial Judgment Infrastructure for MCP-compatible agents. It
turns narrow, ambiguous financial micro-decisions into typed, versioned,
composable judgments. It is not a Jev API wrapper, a financial LLM, an
autonomous research agent, or an investment-decision authority.

The first implementation intentionally keeps the agent loop outside FinJev:
FinJev returns judgments and policy suggestions; calling code decides whether to
continue, fetch another source, invoke an LLM, or request human review.

## Language and runtime decision

The primary runtime is Python 3.12 managed by `uv`.

This decision is based on the actual repository environment, not preference:

| Observation | Evidence in this checkout | Consequence |
| --- | --- | --- |
| System Python is 3.9.6 | `python3 --version` | Do not rely on the system interpreter |
| Project Python 3.12.14 is available | `uv python list` / `.venv` | Pin a project-local runtime |
| `typesafe-sdk 0.7.1` installs | `uv pip install` succeeded | Use the official async TypeSafe client |
| `mcp 2.2.0` installs | `uv pip install` succeeded | Use the current `MCPServer` API, not old `FastMCP` examples |
| Pydantic 2.13.5 installs | `uv sync` succeeded | Use one validation model for domain state and MCP schemas |

TypeScript remains a valid alternative for a web-heavy MCP gateway. It is not
the selected V0.1 implementation because the benchmark, structured financial
data, and later calibration workflow are more naturally colocated with Python.
Maintaining both implementations now would create contract drift without any
measured benefit, so the repository has one Python source of truth.

## Overall architecture

```text
MCP-compatible Agent
        |
        v
MCP Business Tools (7 V0.1 tools)
        |
        v
Research Application Service
        |
        +--> Pydantic input/state models
        +--> State normalization + SHA-256 state hash
        +--> Versioned Rubric Registry
        |
        v
Async Jev Gateway  <---->  TypeSafe API
        |
        v
Typed Answers: Noul / Choice / Score
        |
        v
Deterministic Composition + Domain Policy
        |
        +--> ACCEPT / REJECT / VERIFY
        +--> CONTINUE / STOP
        +--> HUMAN_REVIEW
        |
        v
Structured MCP result + redacted stderr telemetry
```

The gateway is an adapter boundary. Tests use an explicit `FakeGateway`; the
production entrypoint refuses to start without `TYPESAFE_API_KEY`, so a fixture
cannot silently become a financial judgment.

## Responsibilities by layer

### MCP interface

MCP exposes business-level operations rather than every atomic question:

1. `evaluate_search_results`
2. `rerank_search_results`
3. `evaluate_source`
4. `verify_evidence`
5. `classify_financial_event`
6. `judge_materiality`
7. `should_continue_research`

MCP is transport and schema, not business logic. The seven tools are registered
with structured output schemas. The server is stateless in V0.1 and does not
perform web search, source fetching, OCR, or an autonomous loop.

### Core

`src/finjev/core` contains reusable infrastructure:

- `models.py`: typed questions, typed answers, gateway envelopes, actions;
- `state.py`: JSON-compatible normalization, stable serialization, state hash;
- `registry.py`: rubric and policy version lookup;
- `policies.py`: Noul thresholds, score normalization, weighted composition;
- `gateway.py`: official async TypeSafe adapter and test-only fake adapter.

### State layer

State and Question are separate. State contains only the evidence required for
the current judgment, for example a query, a research question, known claims,
and normalized search results. The state hash is logged instead of the raw
financial content.

### Question and Rubric Registry

Every question is registered with:

- domain and stable name;
- primitive;
- rubric version;
- policy version;
- description.

The domain service may create multiple indexed questions over one state. This
implements fan-out while keeping questions independent. A dependent judgment
must create a new state and a second call in code.

### Primitive layer

The implementation keeps the three answer semantics distinct:

- Noul: probability that a yes/no statement is true. It has no separate
  confidence field.
- Choice: one option from a closed set, plus option probabilities and
  confidence.
- Score: a position over ordered levels, plus level probabilities and
  confidence.

`confidence` is not treated as the probability that a business conclusion is
correct. It is a routing signal derived from the answer distribution. Thresholds
are therefore policy-specific and must be validated on a labeled benchmark.

### Composition and Decision Policy

Jev produces atomic signals. Ordinary Python code combines them. For example,
source credibility is initially composed from authority, directness,
primary-source status, independence, and cross-validation need. The weights and
thresholds in V0.1 are engineering defaults, not empirical financial truth.

High-level policies return an action and a reason. They do not execute the
action. The caller owns the workflow and any side effects.

### Observability and versioning

Every completed batch records on stderr:

- request ID;
- domain and judgment name;
- state hash;
- model name;
- rubric and policy versions;
- latency and available token usage.

Raw financial state is not written to telemetry. A later production sink can
add PII masking, retention, trace IDs, cost accounting, and sampled debug data.

## Rule / Jev / LLM / Human boundary

| Task | Owner | Reason |
| --- | --- | --- |
| Date parsing, numeric conversion, unit conversion, null handling, exact deduplication | Rule/code | Deterministic and auditable |
| Closed event category, source type, claim support, fetch worthiness | Jev | Narrow semantic judgment with typed output |
| Weighted credibility/materiality composition | Rule/code | Business weights must remain explicit and testable |
| Open-ended investment thesis, multi-step document reasoning, query generation | LLM or application code | Outside a single atomic judgment |
| High-risk or responsibility-bearing conclusion | Human review | Probability and schema validity do not transfer responsibility |

## V0.1 implemented boundary

Implemented now:

- seven Research MCP tools;
- async TypeSafe gateway;
- explicit fake gateway for tests;
- Noul/Choice/Score parsing;
- batch fan-out over result/evidence arrays;
- deterministic reranking and composition;
- default policy actions and reasons;
- rubric/policy versioning;
- stable state hash and redacted telemetry;
- MCP schema inspection and unit tests.

Explicitly not implemented:

- autonomous web search or source fetching;
- PDF parsing, OCR, table extraction, and document chunking;
- a database, cache, queue, auth, tenant model, or admin UI;
- LLM fallback or provider routing;
- calibrated thresholds learned from a gold financial benchmark;
- general-purpose financial-number extraction or denominator inference;
- trade execution, portfolio advice, or investment recommendation;
- Risk Pack, Due Diligence Pack, Data Quality Pack, or Control Plane as
  production modules.

The numeric materiality limitation is deliberate. A threshold such as
`amount > 5% of revenue` belongs to code after amount, period, currency, and
denominator have been normalized. Jev may judge semantic impact, but it should
not invent or extract a critical financial number in V0.1.

### Materiality profile v2

The MCP and evaluators default to the `v2` profile. `v1` remains available only
as an explicit compatibility/baseline selection. The profile combines:

- a versioned Jev Score rubric with explicit `low`, `medium`, `high`, and
  `critical` definitions;
- normalized numeric facts supplied by the caller, when available;
- deterministic materiality floors for narrow, auditable triggers such as a
  non-standard audit opinion, material going-concern uncertainty, an
  unremediated material control weakness, a revenue KAM explicitly covering
  over 80%, guarantee exposure explicitly over 5% of equity, and selected core
  metric deterioration;
- a `HUMAN_REVIEW` policy override for final `critical` judgments.

The rule layer only raises a materiality floor and never downgrades Jev. It
does not infer missing denominators. Evaluation reports semantic-only and
hybrid metrics separately. The profile remains advisory-only because the
current 49-record reference is AI-assisted and has only three issuer groups.
A critical result is routed to human review; a low-confidence or
evidence-deficient high-impact result abstains.

## Development route

### V0.1 — Research Judgment MCP (current)

Validate the interface and decomposition on a labeled, versioned benchmark.
Compare Rule, Jev, and an LLM judge on accuracy, latency, cost, calibration,
coverage, and escalation rate.

Not doing: autonomous research loops, OCR, and broad financial data ingestion.

### V0.2 — Due Diligence Pack

Add normalized document sections, disclosure review, transaction semantics,
related-party judgment, missing evidence, and conflict detection.

Not doing: allowing Jev to read raw PDFs/images or make deterministic amount
comparisons.

### V0.3 — Decision Control Plane

Add tool routing, workflow retry, continuation, stop, escalation, and model
routing. Keep transport retries separate from workflow retries.

Not doing: giving Jev authority to execute an agent loop or side effect.

### V0.4 — Data Quality and Extraction

Add entity resolution, financial schema alignment, parser candidates, and
candidate-value selection. The parser produces candidates; code validates the
numeric result.

Not doing: open-ended generation of financial numbers.

### V1.0 — Financial Judgment Infrastructure

Add independent Risk and Data Quality policies, benchmark management, calibration
reports, regression gates, storage/retention controls, and deployment hardening.

Not doing: treating V1.0 as an autonomous financial decision-maker.

## Decisions still requiring real evidence

The following are not knowable from `master_prompt` alone and must be checked on
the actual workload:

1. Jev accuracy and calibration on Chinese A-share, US public-company, or other
   target-market data;
2. useful thresholds for source credibility, materiality, and continuation;
3. whether the seven tools should accept Chinese, English, or bilingual state;
4. the acceptable false-negative/false-positive trade-off for each future risk
   pack;
5. TypeSafe API latency, quota, error, and data-retention behavior for the
   intended deployment region.

Until those are measured, the V0.1 weights and thresholds should be read as
versioned hypotheses, not validated financial policy.
