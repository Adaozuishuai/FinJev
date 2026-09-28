# FinJev MCP

## Repository status

FinJev v0.3.0 provides a stdio MCP judgment backend with seven tools. The host
Agent retrieves financial data, FinJev/Jev returns structured judgments, and the
host Agent writes the final cited natural-language answer. Retrieval relies on
the host Agent's search, browser, files, or financial-data connectors.

Install and register with one command (requires uv, Codex CLI and an existing Jev key file):

```sh
uvx --python 3.12 --from "git+https://github.com/Adaozuishuai/FinJev.git@v0.3.0" finjev-install --client codex --key-file /absolute/path/to/apikey
```

Use `--client claude-code`, `claude-desktop`, `cursor`, `vscode`, or `generic`
for other MCP clients. The installer keeps unrelated configuration, backs up
existing files, stores no key contents, and checks the real stdio handshake
before registering. The default check makes no paid model call.
See [installation, client scopes, safety and verification limits](docs/INSTALL.md).

The server now includes the agent-neutral `financial_research_workflow` prompt.
The Codex plugin adapter source remains in `adapters/codex/finjev-financial-research`.
Client configuration generation and standard MCP are tested; every client's
GUI and every operating system have not been individually accepted.

The checked-in annotation sets are development references, not an independent
gold benchmark. Original PDFs and local API keys are not included. Historical
source paths in dataset manifests describe the original local setup; rebuilding
those sets and viewing PDFs requires configuring your own source files.

Clone the repository, run `uv sync`, and configure credentials through
`TYPESAFE_API_KEY` or `FINJEV_API_KEY_FILE`. For a standalone MCP executable,
install from the repository root using `uv tool install .`, then configure your
MCP client to launch `finjev`. The local paths in the historical evaluation
examples below must be replaced with your own key-file path.

FinJev is a Financial Judgment Infrastructure for MCP-compatible agents. It turns
narrow, ambiguous financial micro-decisions into typed, versioned and composable
judgments. It is not a financial agent, a Jev wrapper, or a replacement for an
LLM or human review.

## V0.2 production-shadow boundary

This first slice implements the Research Judgment MCP surface:

- search-result evaluation
- search-result reranking
- source evaluation
- evidence verification
- financial-event classification
- financial-materiality judgment
- research continuation decision

The server is a stateless Python modular monolith. MCP is the transport and
tool contract; `src/finjev/core` owns schemas, state hashing, rubric registration,
gateway abstraction and decision policies; `src/finjev/domain/research` owns financial
questions and composition. No database, OCR, PDF parser, autonomous web search,
LLM fallback, or transaction execution is included. V0.2 defaults to the
materiality v2 hybrid profile and marks conclusions `advisory_only`. Critical
conclusions require human review; low-confidence or evidence-deficient
high-impact conclusions return `ABSTAIN`.

## Why Python first

The repository uses a project-local Python 3.12 environment managed by `uv`.
That gives the V0.2 service the official TypeSafe Python SDK, Pydantic models for
structured state, and a natural home for the later benchmark/calibration work.
The system Python 3.9 is intentionally not modified.

## Run

```sh
uv sync
uv run pytest
uv run ruff check .
```

Audit an annotation set before using it in an evaluation:

```sh
uv run finjev-audit-annotations data/annotation_set_v0.1
uv run finjev-audit-annotations data/annotation_set_v0.1 --require-gold
```

The current multi-issuer development seed is `data/annotation_set_v0.2`. Rebuild
and audit it with:

```sh
uv run python scripts/build_annotation_set_v0_2.py
uv run finjev-audit-annotations data/annotation_set_v0.2
```

Prepare two independent, label-blind review packets before gold adjudication:

```sh
uv run finjev-prepare-reviews data/annotation_set_v0.2 data/reviews/v0.2 \
  --reviewer reviewer_a --reviewer reviewer_b
```

Use stable reviewer identifiers before running this command. Existing packet
files are never overwritten. Each reviewer receives a deterministic but
reviewer-specific record order and cannot see the seed classification labels.

Start the local annotation workbench:

```sh
uv run finjev-review-app
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765). The server binds only
to the local loopback interface by default. It supports PDF/page review,
autosave, completion locks, reviewer agreement metrics, conflict adjudication,
and validated `data/annotation_set_v0.3-gold` export. Unlocking a completed
packet archives any prior adjudications as stale so changed reviews cannot reuse
old conflict decisions.

The first command checks structural seed readiness. The second intentionally
returns a non-zero status until gold-label blockers such as adjudication,
multi-annotator review, and leakage-safe dataset groups are resolved.

Build the explicitly non-gold development reference after packets are locked
and every conflict has an adjudication record:

```sh
uv run finjev-build-dev-reference \
  data/annotation_set_v0.2 \
  data/reviews/v0.2 \
  data/annotation_set_v0.3-dev-reference
```

Run a five-record real-Jev smoke test before the full development baseline:

```sh
FINJEV_API_KEY_FILE=/Users/Admin/Documents/FinJev/apikey \
  uv run finjev-eval data/annotation_set_v0.3-dev-reference \
  artifacts/evals/jev-smoke-v0.3.jsonl --smoke --concurrency 1

FINJEV_API_KEY_FILE=/Users/Admin/Documents/FinJev/apikey \
  uv run finjev-eval data/annotation_set_v0.3-dev-reference \
  artifacts/evals/jev-baseline-v0.3.jsonl --concurrency 2

FINJEV_API_KEY_FILE=/Users/Admin/Documents/FinJev/apikey \
  uv run finjev-eval data/annotation_set_v0.3-dev-reference \
  artifacts/evals/jev-baseline-v0.3-materiality-v2.jsonl \
  --materiality-profile v2 --concurrency 2
```

The evaluator is resumable and stores raw typed judgments, model and rubric
versions, state hashes, latency, token usage, policy output, and errors. The
v0.3 reference must not be described as a gold benchmark because its core
labels share an AI-assisted prefill.

`--materiality-profile v2` sends Jev explicit ordered materiality definitions
and applies auditable deterministic floors for supported triggers. It never
downgrades the semantic Jev result. The summary reports semantic-only and
hybrid metrics separately so rule gains cannot be attributed to the model.

For a real Jev-backed MCP process, set `TYPESAFE_API_KEY` in the environment used
by the MCP client, or set `FINJEV_API_KEY_FILE` to a file containing either
`TYPESAFE_API_KEY=<key>` or the raw key. The environment variable takes priority.
For the current local file:

```sh
FINJEV_API_KEY_FILE=/Users/Admin/Documents/FinJev/apikey \
FINJEV_MATERIALITY_PROFILE=v2 \
uv run finjev
```

`FINJEV_MATERIALITY_PROFILE` accepts only `v1` or `v2` and defaults to `v2`.
An invalid value fails startup instead of silently selecting another policy.

The server intentionally fails with a configuration error when the real gateway
is selected but no key is present. Tests use a fake gateway; a fake response must
never be confused with a financial judgment from Jev.

## Shadow-test production data

Production-like data can be tested without pretending it is labeled truth. Put
one JSON object per line in a local file:

```json
{"record_id":"prod-001","company":"Example Co","headline":"Example Co received a qualified audit opinion","content":"The auditor could not obtain sufficient appropriate audit evidence.","publication_date":"2026-09-23","source":{"publisher":"Example Co filing","source_type":"regulator_filing","is_primary_source":true},"research_question":"How material is this disclosed event?"}
```

Then run:

```sh
FINJEV_API_KEY_FILE=/Users/Admin/Documents/FinJev/apikey \
uv run finjev-shadow-test production-events.jsonl artifacts/shadow/production-results.jsonl
```

The command is resumable and writes one result per record plus a `.summary.json`
file. It reports operational success and the `ACCEPT`, `VERIFY`, `ABSTAIN`, and
`HUMAN_REVIEW` review yield. Without human reference labels it does **not** report
accuracy. Input text is sent to the configured Jev provider; do not submit data
whose provider processing is prohibited by your confidentiality policy.

## Architecture

```text
MCP tools
    -> research application services
        -> normalized Pydantic state + versioned rubric registry
            -> Jev gateway (or explicit test fake)
                -> typed atomic answers
                    -> deterministic composition
                        -> risk-aware decision policy
                            -> MCP structured result + redacted telemetry
```

The external tools are business-level operations. Atomic questions stay internal
so the public MCP surface does not grow with every new factor.
