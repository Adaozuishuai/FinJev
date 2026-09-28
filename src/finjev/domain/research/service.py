from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from ...core.gateway import AsyncJevGateway
from ...core.models import (
    ChoiceAnswer,
    DecisionAction,
    JudgmentBatch,
    NoulAnswer,
    PolicyDecision,
    QuestionDefinition,
    ScoreAnswer,
)
from ...core.policies import (
    WeightedSignal,
    action_for_composite,
    apply_noul_policy,
    clamp01,
    compose_weighted_score,
    normalize_score,
)
from ...core.registry import RubricRegistry
from ...core.state import build_state, hash_state
from ...observability import create_request_id, emit_judgment_telemetry
from .materiality import evaluate_materiality_rules, max_materiality
from .models import (
    ClassifyFinancialEventInput,
    EvaluateSearchResultsInput,
    EvaluateSourceInput,
    JudgeMaterialityInput,
    RerankSearchResultsInput,
    ShouldContinueResearchInput,
    VerifyEvidenceInput,
)
from .rubrics import R, create_research_registry
from .taxonomy import EVENT_TYPE_CRITERIA

SOURCE_TYPE_CRITERIA = {
    "regulator_filing": "A filing or disclosure made to a securities regulator.",
    "audited_report": "An audited annual or financial report.",
    "company_release": "A company-issued release, presentation, or investor announcement.",
    "transaction_document": "A contract, prospectus, merger document, or transaction filing.",
    "financial_database": "A structured market or financial data provider.",
    "news_agency": "A professional news organization reporting the event.",
    "analyst_commentary": "Analyst, broker, or research commentary without primary authority.",
    "social_media": "A social post, forum, or other informal source.",
    "other": "A source that does not fit the other categories.",
}
INFORMATION_VALUE_LEVELS = ["low", "medium", "high"]
AUTHORITY_LEVELS = ["low", "medium", "high", "very_high"]
DIRECTNESS_LEVELS = ["indirect", "mixed", "direct", "explicit"]
EVIDENCE_STRENGTH_LEVELS = ["weak", "moderate", "strong", "decisive"]
MATERIALITY_LEVELS = ["low", "medium", "high", "critical"]
MATERIALITY_V2_CRITERIA = [
    {
        "label": "low",
        "definition": (
            "Background or a small fact with no identifiable financial, governance, legal, liquidity, "
            "or execution consequence. Do not use merely because context is missing."
        ),
    },
    {
        "label": "medium",
        "definition": (
            "A meaningful but non-core item, commonly around 1%-10% of a stated relevant denominator, "
            "or a governance/operating item such as ordinary treasury management, dividends, incentives, "
            "customer concentration, or auditor change without a stronger trigger."
        ),
    },
    {
        "label": "high",
        "definition": (
            "A core metric conflict or loss; at least 10% of revenue, assets, or equity when the denominator "
            "is explicit; guarantee or concentration exposure above 5% of equity; or a high-risk topic such "
            "as revenue recognition, impairment, major estimates, litigation, regulatory approval, liquidity, "
            "refinancing, or project delay."
        ),
    },
    {
        "label": "critical",
        "definition": (
            "A non-standard audit opinion, material going-concern uncertainty, unremediated material internal-"
            "control weakness, bankruptcy/default/control-changing event, or a key audit matter covering over "
            "80% of revenue/assets with explicit manipulation, misstatement, or major-estimate risk. Use the "
            "highest triggered level and do not invent a missing denominator."
        ),
    },
]
FUNDAMENTAL_IMPACT_LEVELS = ["none", "limited", "moderate", "material", "transformative"]


def _noul(batch: JudgmentBatch, key: str) -> NoulAnswer:
    answer = batch.answers.get(key)
    if not isinstance(answer, NoulAnswer):
        raise TypeError(f"Expected Noul answer for {key}")
    return answer


def _choice(batch: JudgmentBatch, key: str) -> ChoiceAnswer:
    answer = batch.answers.get(key)
    if not isinstance(answer, ChoiceAnswer):
        raise TypeError(f"Expected Choice answer for {key}")
    return answer


def _score(batch: JudgmentBatch, key: str) -> ScoreAnswer:
    answer = batch.answers.get(key)
    if not isinstance(answer, ScoreAnswer):
        raise TypeError(f"Expected Score answer for {key}")
    return answer


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _dump(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_dump(child) for child in value]
    return value


def _score_value(answer: ScoreAnswer) -> float:
    return normalize_score(answer)


def _score_label(answer: ScoreAnswer, levels: list[str]) -> str:
    key = max(answer.probabilities, key=answer.probabilities.get)
    legend_value = (answer.legend or {}).get(key)
    if isinstance(legend_value, str) and legend_value in levels:
        return legend_value
    if isinstance(legend_value, dict) and legend_value.get("label") in levels:
        return str(legend_value["label"])
    return levels[min(len(levels) - 1, max(0, round(answer.score)))]


def _versioning(batch: JudgmentBatch) -> dict[str, dict[str, str]]:
    return {"rubric_versions": batch.rubric_versions, "policy_versions": batch.policy_versions}


class ResearchService:
    def __init__(
        self,
        gateway: AsyncJevGateway,
        registry: RubricRegistry | None = None,
        materiality_profile: str = "v2",
    ) -> None:
        if materiality_profile not in {"v1", "v2"}:
            raise ValueError("materiality_profile must be 'v1' or 'v2'")
        self.gateway = gateway
        self.registry = registry or create_research_registry()
        self.materiality_profile = materiality_profile

    def _materiality_result(self, event: Any, answer: ScoreAnswer) -> dict[str, Any]:
        semantic = _score_label(answer, MATERIALITY_LEVELS)
        rules = evaluate_materiality_rules(event)
        final = max_materiality(semantic, rules.floor) if self.materiality_profile == "v2" else semantic
        return {
            "profile": self.materiality_profile,
            "semantic": semantic,
            "semantic_confidence": answer.confidence,
            "rule_floor": rules.floor if self.materiality_profile == "v2" else None,
            "rule_triggers": list(rules.triggers) if self.materiality_profile == "v2" else [],
            "rules_version": rules.policy_version if self.materiality_profile == "v2" else None,
            "final": final,
        }

    def _materiality_policy(
        self,
        *,
        event: Any,
        decision: dict[str, Any],
        base_policy: PolicyDecision,
        follow_up: NoulAnswer,
        policy_name: str,
    ) -> PolicyDecision:
        policy_version = f"{policy_name}.v2" if self.materiality_profile == "v2" else f"{policy_name}.v1"
        has_supporting_context = bool(
            getattr(event, "content", None)
            or getattr(event, "numeric_facts", None)
            or getattr(event, "source", None)
        )
        if float(decision["semantic_confidence"]) < 0.35:
            return PolicyDecision(
                action=DecisionAction.ABSTAIN,
                reason="Materiality confidence is below 0.35; no automated conclusion is allowed.",
                policy_version=policy_version,
            )
        if decision["final"] in {"high", "critical"} and not has_supporting_context:
            return PolicyDecision(
                action=DecisionAction.ABSTAIN,
                reason="A high-impact conclusion lacks source, content, or normalized numeric evidence.",
                policy_version=policy_version,
            )
        if decision["final"] == "critical":
            return PolicyDecision(
                action=DecisionAction.HUMAN_REVIEW,
                reason="A critical materiality conclusion requires human review.",
                policy_version=policy_version,
            )
        if follow_up.noul >= 0.75 and base_policy.action == DecisionAction.ACCEPT:
            return PolicyDecision(
                action=DecisionAction.VERIFY,
                reason="Potentially material, but additional evidence is required.",
                policy_version=policy_version,
            )
        if decision["rule_floor"] == "high" and base_policy.action == DecisionAction.REJECT:
            return PolicyDecision(
                action=DecisionAction.VERIFY,
                reason="A deterministic high-materiality trigger prevents automatic rejection.",
                policy_version=policy_version,
            )
        return PolicyDecision(
            action=base_policy.action,
            reason=base_policy.reason,
            policy_version=policy_version,
        )

    async def _judge(
        self,
        judgment: str,
        state: Any,
        questions: Mapping[str, QuestionDefinition],
    ) -> JudgmentBatch:
        request_id = create_request_id()
        normalized_state = build_state(state)
        rubric_versions = self.registry.versions_for(questions)
        policy_versions = self.registry.policy_versions_for(questions)
        result = await self.gateway.evaluate(
            normalized_state,
            questions,
            {
                "request_id": request_id,
                "domain": "research",
                "rubric_versions": rubric_versions,
            },
        )
        batch = JudgmentBatch(
            request_id=request_id,
            domain="research",
            judgment=judgment,
            state_hash=hash_state(normalized_state),
            model=result.model,
            rubric_versions=rubric_versions,
            policy_versions=policy_versions,
            answers=result.answers,
            usage=result.usage,
            latency_ms=result.latency_ms,
        )
        emit_judgment_telemetry(batch)
        return batch

    async def evaluate_search_results(self, input_data: EvaluateSearchResultsInput) -> dict[str, Any]:
        questions: dict[str, QuestionDefinition] = {}
        for index, _result in enumerate(input_data.results):
            questions[f"result_{index}_relevance"] = self.registry.question(
                R["search_relevance"],
                f"Considering `query`, `research_context`, and `results[{index}]`, does this search result materially help answer the research question?",
            )
            questions[f"result_{index}_new_information"] = self.registry.question(
                R["search_new_information"],
                f"Considering `research_context.known_claims` and `results[{index}]`, does this result contain information not already represented in the known claims?",
            )
            questions[f"result_{index}_worth_fetching"] = self.registry.question(
                R["search_worth_fetching"],
                f"Considering `results[{index}]`, is fetching the full source likely worth the latency and cost for the research question?",
            )
            questions[f"result_{index}_information_value"] = self.registry.question(
                R["search_information_value"],
                f"Considering `query`, `research_context`, and `results[{index}]`, how much expected information value does this result have?",
                INFORMATION_VALUE_LEVELS,
            )

        batch = await self._judge(
            "evaluate_search_results",
            {
                "query": input_data.query,
                "research_context": input_data.research_context,
                "results": input_data.results,
            },
            questions,
        )
        evaluations = []
        for index, result in enumerate(input_data.results):
            relevance = _noul(batch, f"result_{index}_relevance")
            new_information = _noul(batch, f"result_{index}_new_information")
            worth_fetching = _noul(batch, f"result_{index}_worth_fetching")
            information_value = _score(batch, f"result_{index}_information_value")
            policy = apply_noul_policy(
                worth_fetching,
                positive=0.75,
                negative=0.25,
                policy_version="research.search-fetch-policy.v1",
            )
            evaluations.append(
                {
                    "result_id": result.id,
                    "title": result.title,
                    "judgments": {
                        "relevance": relevance,
                        "new_information": new_information,
                        "worth_fetching": worth_fetching,
                        "information_value": information_value,
                    },
                    "signals": {
                        "relevance": relevance.noul,
                        "new_information": new_information.noul,
                        "worth_fetching": worth_fetching.noul,
                        "information_value": _score_value(information_value),
                    },
                    "policy": policy,
                }
            )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "evaluations": _dump(evaluations),
                **_versioning(batch),
            }
        )

    async def rerank_search_results(self, input_data: RerankSearchResultsInput) -> dict[str, Any]:
        if input_data.evaluations:
            provided_by_id = {evaluation.result_id: evaluation for evaluation in input_data.evaluations}
            evaluations = []
            for result in input_data.results:
                provided = provided_by_id.get(result.id)
                if provided is None:
                    raise ValueError(f"Missing provided evaluation for result {result.id}")
                evaluations.append(
                    {
                        "result_id": result.id,
                        "title": result.title,
                        "signals": {
                            "relevance": provided.relevance,
                            "new_information": provided.new_information,
                            "worth_fetching": provided.worth_fetching,
                            "information_value": provided.information_value,
                        },
                    }
                )
            request_id = create_request_id()
            method = "provided_atomic_judgments"
        else:
            evaluated = await self.evaluate_search_results(input_data)
            evaluations = evaluated["evaluations"]
            request_id = evaluated["request_id"]
            method = "jev_atomic_judgments"

        weights = {
            "relevance": 0.35,
            "new_information": 0.2,
            "worth_fetching": 0.25,
            "information_value": 0.2,
        }
        ranked = []
        for original_position, evaluation in enumerate(evaluations):
            signals = evaluation["signals"]
            score = clamp01(sum(signals[name] * weight for name, weight in weights.items()))
            ranked.append(
                {
                    "result_id": evaluation["result_id"],
                    "title": evaluation["title"],
                    "original_position": original_position,
                    "score": score,
                    "signals": signals,
                }
            )
        ranked.sort(key=lambda item: (-item["score"], item["original_position"]))
        for rank, item in enumerate(ranked, start=1):
            item["rank"] = rank
        return {
            "request_id": request_id,
            "method": method,
            "weights": weights,
            "ranked": ranked,
            **({"evaluations": evaluations} if method == "jev_atomic_judgments" else {}),
        }

    async def evaluate_source(self, input_data: EvaluateSourceInput) -> dict[str, Any]:
        questions = {
            "source_type": self.registry.question(
                R["source_type"], "What kind of financial source is `source`?", SOURCE_TYPE_CRITERIA
            ),
            "is_primary_source": self.registry.question(
                R["source_primary"], "Is `source` primary for `claim`?"
            ),
            "source_authority": self.registry.question(
                R["source_authority"], "How authoritative is `source` for `claim`?", AUTHORITY_LEVELS
            ),
            "claim_directness": self.registry.question(
                R["source_directness"], "How directly does `source` support `claim`?", DIRECTNESS_LEVELS
            ),
            "source_independence": self.registry.question(
                R["source_independence"],
                "Is `source` sufficiently independent of the company or party making `claim`?",
            ),
            "needs_cross_validation": self.registry.question(
                R["source_cross_validation"],
                "Does `source` require cross-validation before `claim` is relied on?",
            ),
        }
        batch = await self._judge(
            "evaluate_source",
            {
                "source": input_data.source,
                "claim": input_data.claim,
                "research_context": input_data.research_context,
            },
            questions,
        )
        source_type = _choice(batch, "source_type")
        is_primary = _noul(batch, "is_primary_source")
        authority = _score(batch, "source_authority")
        directness = _score(batch, "claim_directness")
        independence = _noul(batch, "source_independence")
        cross_validation = _noul(batch, "needs_cross_validation")
        composition = compose_weighted_score(
            [
                WeightedSignal("authority", _score_value(authority), 0.3),
                WeightedSignal("directness", _score_value(directness), 0.25),
                WeightedSignal("primary_source", is_primary.noul, 0.2),
                WeightedSignal("independence", independence.noul, 0.15),
                WeightedSignal("no_cross_validation_needed", 1 - cross_validation.noul, 0.1),
            ]
        )
        policy = action_for_composite(
            composition["value"],
            accept=0.75,
            reject=0.3,
            policy_version="research.source-credibility-policy.v1",
        )
        if min(source_type.confidence, authority.confidence, directness.confidence) < 0.35:
            policy = PolicyDecision(
                action=DecisionAction.HUMAN_REVIEW,
                reason="At least one source judgment has low confidence.",
                policy_version="research.source-credibility-policy.v1",
            )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "claim": input_data.claim,
                "judgments": {
                    "source_type": source_type,
                    "is_primary_source": is_primary,
                    "source_authority": authority,
                    "claim_directness": directness,
                    "source_independence": independence,
                    "needs_cross_validation": cross_validation,
                },
                "credibility": composition,
                "policy": policy,
                **_versioning(batch),
            }
        )

    async def verify_evidence(self, input_data: VerifyEvidenceInput) -> dict[str, Any]:
        questions: dict[str, QuestionDefinition] = {}
        for index, _evidence in enumerate(input_data.evidence):
            questions[f"evidence_{index}_support"] = self.registry.question(
                R["evidence_support"],
                f"Considering `claim` and `evidence[{index}]`, does the evidence support the claim?",
            )
            questions[f"evidence_{index}_contradiction"] = self.registry.question(
                R["evidence_contradiction"],
                f"Considering `claim` and `evidence[{index}]`, does the evidence contradict the claim?",
            )
            questions[f"evidence_{index}_directness"] = self.registry.question(
                R["evidence_directness"],
                f"How directly does `evidence[{index}]` address `claim`?",
                DIRECTNESS_LEVELS,
            )
            questions[f"evidence_{index}_strength"] = self.registry.question(
                R["evidence_strength"],
                f"How strong is `evidence[{index}]` for `claim`?",
                EVIDENCE_STRENGTH_LEVELS,
            )
        batch = await self._judge(
            "verify_evidence",
            {
                "claim": input_data.claim,
                "research_context": input_data.research_context,
                "evidence": input_data.evidence,
            },
            questions,
        )
        findings = []
        for index, evidence in enumerate(input_data.evidence):
            support = _noul(batch, f"evidence_{index}_support")
            contradiction = _noul(batch, f"evidence_{index}_contradiction")
            directness = _score(batch, f"evidence_{index}_directness")
            strength = _score(batch, f"evidence_{index}_strength")
            composition = compose_weighted_score(
                [
                    WeightedSignal("support", support.noul, 0.4),
                    WeightedSignal("no_contradiction", 1 - contradiction.noul, 0.2),
                    WeightedSignal("directness", _score_value(directness), 0.2),
                    WeightedSignal("strength", _score_value(strength), 0.2),
                ]
            )
            policy = action_for_composite(
                composition["value"], accept=0.65, reject=0.25, policy_version="research.evidence-policy.v1"
            )
            if contradiction.noul >= 0.7 and contradiction.noul > support.noul:
                policy = PolicyDecision(
                    action=DecisionAction.REJECT,
                    reason="Contradiction probability dominates support probability.",
                    policy_version="research.evidence-policy.v1",
                )
            finding = {
                DecisionAction.ACCEPT: "supports",
                DecisionAction.REJECT: "contradicts",
            }.get(policy.action, "insufficient")
            findings.append(
                {
                    "evidence_id": evidence.id,
                    "judgments": {
                        "support": support,
                        "contradiction": contradiction,
                        "directness": directness,
                        "strength": strength,
                    },
                    "composition": composition,
                    "finding": finding,
                    "policy": policy,
                }
            )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "claim": input_data.claim,
                "findings": findings,
                **_versioning(batch),
            }
        )

    async def classify_financial_event(self, input_data: ClassifyFinancialEventInput) -> dict[str, Any]:
        materiality_rubric = (
            R["event_materiality_v2"] if self.materiality_profile == "v2" else R["event_materiality"]
        )
        materiality_criteria = (
            MATERIALITY_V2_CRITERIA if self.materiality_profile == "v2" else MATERIALITY_LEVELS
        )
        questions = {
            "event_type": self.registry.question(
                R["event_type"], "What type of financial event is `event`?", EVENT_TYPE_CRITERIA
            ),
            "company_relevance": self.registry.question(
                R["event_relevance"], "Is `event` relevant to the company and `research_context.question`?"
            ),
            "financial_materiality": self.registry.question(
                materiality_rubric,
                (
                    "Apply the FinJev task-priority materiality rubric to `event`. Judge the disclosed event, "
                    "not the whole company or an investment recommendation. Use the highest level whose stated "
                    "trigger is supported, and do not invent missing amounts or denominators."
                    if self.materiality_profile == "v2"
                    else "How financially material is `event`?"
                ),
                materiality_criteria,
            ),
            "fundamental_impact": self.registry.question(
                R["event_fundamental_impact"],
                "How likely is `event` to affect company fundamentals?",
                FUNDAMENTAL_IMPACT_LEVELS,
            ),
            "novel_information": self.registry.question(
                R["event_novel_information"], "Does `event` add materially new information?"
            ),
            "requires_follow_up": self.registry.question(
                R["event_follow_up"], "Does `event` require follow-up research?"
            ),
        }
        batch = await self._judge(
            "classify_financial_event",
            {"event": input_data.event, "research_context": input_data.research_context},
            questions,
        )
        event_type = _choice(batch, "event_type")
        relevance = _noul(batch, "company_relevance")
        materiality = _score(batch, "financial_materiality")
        materiality_decision = self._materiality_result(input_data.event, materiality)
        fundamental_impact = _score(batch, "fundamental_impact")
        novel_information = _noul(batch, "novel_information")
        follow_up = _noul(batch, "requires_follow_up")
        composition = compose_weighted_score(
            [
                WeightedSignal("relevance", relevance.noul, 0.2),
                WeightedSignal("materiality", _score_value(materiality), 0.35),
                WeightedSignal("fundamental_impact", _score_value(fundamental_impact), 0.3),
                WeightedSignal("novel_information", novel_information.noul, 0.15),
            ]
        )
        policy = action_for_composite(
            composition["value"], accept=0.65, reject=0.3, policy_version="research.event-policy.v1"
        )
        if relevance.noul <= 0.3:
            policy = PolicyDecision(
                action=DecisionAction.REJECT,
                reason="Event is unlikely to be relevant to the stated research scope.",
                policy_version="research.event-policy.v1",
            )
        elif follow_up.noul >= 0.75 and policy.action == DecisionAction.ACCEPT:
            policy = PolicyDecision(
                action=DecisionAction.VERIFY,
                reason="Event looks material but follow-up research is required.",
                policy_version="research.event-policy.v1",
            )
        policy = self._materiality_policy(
            event=input_data.event,
            decision=materiality_decision,
            base_policy=policy,
            follow_up=follow_up,
            policy_name="research.event-policy",
        )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "usage": batch.usage,
                "decision_authority": "advisory_only",
                "materiality_decision": materiality_decision,
                "judgments": {
                    "event_type": event_type,
                    "relevance": relevance,
                    "materiality": materiality,
                    "fundamental_impact": fundamental_impact,
                    "novel_information": novel_information,
                    "follow_up": follow_up,
                },
                "composition": composition,
                "policy": policy,
                **_versioning(batch),
            }
        )

    async def judge_materiality(self, input_data: JudgeMaterialityInput) -> dict[str, Any]:
        materiality_rubric = (
            R["event_materiality_v2"] if self.materiality_profile == "v2" else R["materiality_score"]
        )
        materiality_criteria = (
            MATERIALITY_V2_CRITERIA if self.materiality_profile == "v2" else MATERIALITY_LEVELS
        )
        questions = {
            "is_material": self.registry.question(
                R["materiality_decision"], "Is `event` material to `company` given `financial_context`?"
            ),
            "materiality": self.registry.question(
                materiality_rubric,
                (
                    "Apply the FinJev task-priority materiality rubric to `event` and `financial_context`. "
                    "Use the highest supported level and do not invent missing amounts or denominators."
                    if self.materiality_profile == "v2"
                    else "What is the materiality level of `event`?"
                ),
                materiality_criteria,
            ),
            "fundamental_impact": self.registry.question(
                R["materiality_impact"],
                "How significant could `event` be for company fundamentals?",
                FUNDAMENTAL_IMPACT_LEVELS,
            ),
            "requires_follow_up": self.registry.question(
                R["materiality_follow_up"], "Does this materiality judgment require follow-up evidence?"
            ),
        }
        batch = await self._judge(
            "judge_materiality",
            {
                "company": input_data.company,
                "event": input_data.event,
                "financial_context": input_data.financial_context,
            },
            questions,
        )
        is_material = _noul(batch, "is_material")
        materiality = _score(batch, "materiality")
        materiality_decision = self._materiality_result(input_data.event, materiality)
        fundamental_impact = _score(batch, "fundamental_impact")
        follow_up = _noul(batch, "requires_follow_up")
        composition = compose_weighted_score(
            [
                WeightedSignal("is_material", is_material.noul, 0.45),
                WeightedSignal("materiality", _score_value(materiality), 0.35),
                WeightedSignal("fundamental_impact", _score_value(fundamental_impact), 0.2),
            ]
        )
        policy = action_for_composite(
            composition["value"], accept=0.65, reject=0.3, policy_version="research.materiality-policy.v1"
        )
        policy = self._materiality_policy(
            event=input_data.event,
            decision=materiality_decision,
            base_policy=policy,
            follow_up=follow_up,
            policy_name="research.materiality-policy",
        )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "usage": batch.usage,
                "company": input_data.company,
                "decision_authority": "advisory_only",
                "materiality_decision": materiality_decision,
                "judgments": {
                    "is_material": is_material,
                    "materiality": materiality,
                    "fundamental_impact": fundamental_impact,
                    "follow_up": follow_up,
                },
                "composition": composition,
                "policy": policy,
                "limitation": "Only explicit normalized facts and audited deterministic triggers are used; missing denominators are never inferred.",
                **_versioning(batch),
            }
        )

    async def should_continue_research(self, input_data: ShouldContinueResearchInput) -> dict[str, Any]:
        questions = {
            "evidence_sufficient": self.registry.question(
                R["continuation_evidence_sufficient"],
                "Is the current `evidence_summary` sufficient to answer `research_question`?",
            ),
            "material_information_gap": self.registry.question(
                R["continuation_information_gap"],
                "Does a material information gap remain given `information_gaps`?",
            ),
            "marginal_information_gain": self.registry.question(
                R["continuation_information_gain"],
                "What marginal information gain is likely from another research round?",
                INFORMATION_VALUE_LEVELS,
            ),
        }
        batch = await self._judge("should_continue_research", input_data, questions)
        sufficient = _noul(batch, "evidence_sufficient")
        gap = _noul(batch, "material_information_gap")
        gain = _score(batch, "marginal_information_gain")
        gain_value = _score_value(gain)
        if sufficient.noul >= 0.8 and gap.noul <= 0.3:
            action, reason = (
                DecisionAction.STOP,
                "Evidence is likely sufficient and no material gap is indicated.",
            )
        elif gap.noul >= 0.7 and gain_value >= 0.5:
            action, reason = (
                DecisionAction.CONTINUE,
                "A material gap remains and another round has meaningful expected information value.",
            )
        elif gain_value >= 0.67 and sufficient.noul < 0.8:
            action, reason = (
                DecisionAction.CONTINUE,
                "Evidence is not yet sufficient and another round has high expected information value.",
            )
        elif gap.noul <= 0.3 and gain_value <= 0.34:
            action, reason = (
                DecisionAction.STOP,
                "No material gap and low expected information value make another round unjustified.",
            )
        else:
            action, reason = (
                DecisionAction.VERIFY,
                "Continuation signals are mixed; gather evidence or request review before looping.",
            )
        return _dump(
            {
                "request_id": batch.request_id,
                "state_hash": batch.state_hash,
                "model": batch.model,
                "latency_ms": batch.latency_ms,
                "research_rounds": input_data.research_rounds,
                "judgments": {
                    "evidence_sufficient": sufficient,
                    "information_gap": gap,
                    "information_gain": gain,
                },
                "policy": PolicyDecision(
                    action=action, reason=reason, policy_version="research.continuation-policy.v1"
                ),
                **_versioning(batch),
            }
        )
