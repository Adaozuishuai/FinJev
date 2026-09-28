---
name: financial-research
description: Research companies, filings, earnings, financial events, claims, risks, and materiality by gathering current evidence with Codex, sending narrow structured judgments to FinJev/Jev, and writing the final cited natural-language analysis in Codex. Use when the user asks to查金融数据, research a company, verify a financial claim, analyze a filing or event, rank sources, assess evidence, or decide what deserves deeper research.
---

# FinJev Financial Research

## Product Boundary

Use this plugin as a three-stage research pipeline:

1. Codex gathers and normalizes financial data from available search, browser, file, or connected-data tools.
2. FinJev sends narrow structured questions to Jev and applies explicit deterministic policies.
3. Codex interprets the structured result and writes the final natural-language answer.

Jev is an internal judge, not the final author. Never paste raw Jev output as the answer unless the user explicitly asks for raw diagnostics. Never attribute Codex's prose, thesis, causal explanation, or recommendation to Jev.

The plugin does not execute trades, place orders, modify portfolios, or silently turn an advisory judgment into a final investment decision.

## Research Workflow

### 1. Frame the request

Identify the company or security, market, requested period, as-of date, claim or decision, and required depth. Resolve ambiguous tickers before combining data. Distinguish historical facts, current market data, estimates, management guidance, and Codex inference.

For time-sensitive requests, use live retrieval. Do not answer current prices, filings, management, regulations, or news from model memory.

### 2. Gather data with Codex

Use the best retrieval capability already available to Codex. Prefer sources in this order when applicable:

1. securities regulator or exchange filings;
2. audited reports and transaction documents;
3. company investor-relations releases and presentations;
4. official statistical agencies, central banks, and regulators;
5. reputable financial databases and news agencies;
6. analyst commentary or social sources only as leads or clearly labeled opinion.

The FinJev MCP does not fetch webpages. If Codex has no retrieval tool and the user supplied no source, state that the data cannot be verified and ask for a document or link. Do not invent a source, URL, quote, figure, period, currency, or denominator.

Record the source URL or document identity, publication date, publisher, source type, relevant text, and page or section when available. Match currencies, units, periods, consolidation scope, and denominators before comparing numbers.

### 3. Use FinJev for narrow judgments

Call only the tools needed for the request:

- `evaluate_search_results`: assess relevance, novelty, fetch value, and expected information value before opening many results.
- `rerank_search_results`: prioritize candidate results using the atomic judgments.
- `evaluate_source`: judge source type, authority, directness, independence, and cross-validation need.
- `verify_evidence`: test whether retrieved evidence supports or contradicts a concrete claim.
- `classify_financial_event`: classify an event and assess relevance, materiality, fundamental impact, novelty, and follow-up need.
- `judge_materiality`: make a focused materiality judgment when the event and financial context are already defined.
- `should_continue_research`: decide whether another research round is justified after summarizing evidence and gaps.

Do not call every tool mechanically. A broad company question normally follows:

`search → evaluate/rerank → fetch → evaluate source → verify evidence → classify event/materiality → continue or stop → synthesize`

A user-supplied filing may start at source evaluation or evidence verification. A focused event with sufficient primary evidence may start at event classification.

### 4. Obey the policy result

Treat FinJev fields as structured evidence about the judgment, not ground truth.

- `ACCEPT`: the narrow policy threshold was met; Codex may use the finding with source citations and stated scope.
- `REJECT`: do not use the rejected item as support for the claim. Explain contradiction or irrelevance when useful.
- `VERIFY`: gather another source, denominator, period, or clarification before making a strong conclusion.
- `ABSTAIN`: do not force a conclusion. State what evidence is missing and what would resolve it.
- `HUMAN_REVIEW`: present the evidence and implications, but explicitly require analyst review for the conclusion.
- `CONTINUE` / `STOP`: control the research loop; they are not investment recommendations.

Never hide `ABSTAIN`, `VERIFY`, or `HUMAN_REVIEW` behind confident prose. A deterministic rule floor may raise materiality, but it does not prove the underlying disclosure is correct.

### 5. Let Codex write the final answer

Produce a concise, cited natural-language response shaped to the user's question. Normally include:

- the direct answer or current research status;
- the most important verified facts with dates, units, and source links;
- Codex's interpretation of why those facts matter;
- materiality and policy status from FinJev in plain language;
- contradictory evidence, missing information, and uncertainty;
- the next research step when the system returns `VERIFY`, `ABSTAIN`, or `HUMAN_REVIEW`.

Do not expose large raw JSON blobs, token counts, internal prompts, or all rubric probabilities unless requested. It is acceptable to say that FinJev/Jev was used as a structured judgment layer, but the final synthesis must remain Codex's own evidence-based analysis.

## Data and Safety Rules

- Cite the retrieved source supporting each time-sensitive factual claim.
- Prefer primary evidence; label company statements as company claims until independently corroborated.
- Separate observed facts from calculations and inferences.
- Recompute important ratios from normalized numbers when possible; do not ask Jev to invent missing denominators.
- Do not interpret `confidence` as a calibrated probability that an investment conclusion is correct.
- Do not claim accuracy from unlabeled production data.
- Do not send confidential material to Jev unless the user's data policy permits processing by the configured provider.
- Do not turn the result into personalized financial advice or a transaction without a separately authorized and appropriately controlled system.

## Failure Handling

If FinJev is unavailable, report the configuration or provider failure and continue only with clearly labeled source analysis when that still answers part of the request. Never fabricate a successful Jev call or replace it with a hidden fake. If retrieval succeeds but judgment fails, preserve the citations and distinguish verified facts from the unavailable judgment layer.
