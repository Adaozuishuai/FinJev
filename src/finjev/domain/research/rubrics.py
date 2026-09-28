from __future__ import annotations

from ...core.models import Primitive, RubricDefinition
from ...core.registry import RubricRegistry

R = {
    "search_relevance": "research.search-relevance",
    "search_new_information": "research.search-new-information",
    "search_worth_fetching": "research.search-worth-fetching",
    "search_information_value": "research.search-information-value",
    "source_type": "research.source-type",
    "source_primary": "research.source-primary",
    "source_authority": "research.source-authority",
    "source_directness": "research.source-directness",
    "source_independence": "research.source-independence",
    "source_cross_validation": "research.source-cross-validation",
    "evidence_support": "research.evidence-support",
    "evidence_contradiction": "research.evidence-contradiction",
    "evidence_directness": "research.evidence-directness",
    "evidence_strength": "research.evidence-strength",
    "event_type": "research.event-type",
    "event_relevance": "research.event-relevance",
    "event_materiality": "research.event-materiality",
    "event_materiality_v2": "research.event-materiality-v2",
    "event_fundamental_impact": "research.event-fundamental-impact",
    "event_novel_information": "research.event-novel-information",
    "event_follow_up": "research.event-follow-up",
    "materiality_decision": "research.materiality-decision",
    "materiality_score": "research.materiality-score",
    "materiality_impact": "research.materiality-impact",
    "materiality_follow_up": "research.materiality-follow-up",
    "continuation_evidence_sufficient": "research.continuation-evidence-sufficient",
    "continuation_information_gap": "research.continuation-information-gap",
    "continuation_information_gain": "research.continuation-information-gain",
}

_DEFINITION_DATA = [
    (
        R["search_relevance"],
        Primitive.NOUL,
        "Does this search result materially help answer the research question?",
    ),
    (
        R["search_new_information"],
        Primitive.NOUL,
        "Does this result contain information not already represented in the known claims?",
    ),
    (
        R["search_worth_fetching"],
        Primitive.NOUL,
        "Is fetching the full source likely worth the latency and cost?",
    ),
    (
        R["search_information_value"],
        Primitive.SCORE,
        "How much expected information value does this result have?",
    ),
    (R["source_type"], Primitive.CHOICE, "What kind of financial source is this?"),
    (R["source_primary"], Primitive.NOUL, "Is this source primary for the claim being evaluated?"),
    (R["source_authority"], Primitive.SCORE, "How authoritative is this source for the claim?"),
    (R["source_directness"], Primitive.SCORE, "How directly does the source support the claim?"),
    (
        R["source_independence"],
        Primitive.NOUL,
        "Is this source sufficiently independent of the company or party making the claim?",
    ),
    (
        R["source_cross_validation"],
        Primitive.NOUL,
        "Does this source require cross-validation before the claim is relied on?",
    ),
    (R["evidence_support"], Primitive.NOUL, "Does the evidence support the claim?"),
    (R["evidence_contradiction"], Primitive.NOUL, "Does the evidence contradict the claim?"),
    (R["evidence_directness"], Primitive.SCORE, "How directly does this evidence address the claim?"),
    (R["evidence_strength"], Primitive.SCORE, "How strong is this evidence for the claim?"),
    (R["event_type"], Primitive.CHOICE, "What type of financial event is this?"),
    (R["event_relevance"], Primitive.NOUL, "Is this event relevant to the company and research question?"),
    (R["event_materiality"], Primitive.SCORE, "How financially material is this event?"),
    (
        R["event_materiality_v2"],
        Primitive.SCORE,
        "How financially material is this event under the FinJev task-priority rubric?",
    ),
    (
        R["event_fundamental_impact"],
        Primitive.SCORE,
        "How likely is this event to affect the company fundamentals?",
    ),
    (R["event_novel_information"], Primitive.NOUL, "Does this event add materially new information?"),
    (R["event_follow_up"], Primitive.NOUL, "Does this event require follow-up research?"),
    (
        R["materiality_decision"],
        Primitive.NOUL,
        "Is this event material to the stated company and financial context?",
    ),
    (R["materiality_score"], Primitive.SCORE, "What is the materiality level of this event?"),
    (
        R["materiality_impact"],
        Primitive.SCORE,
        "How significant could the event be for company fundamentals?",
    ),
    (R["materiality_follow_up"], Primitive.NOUL, "Does the materiality judgment require follow-up evidence?"),
    (
        R["continuation_evidence_sufficient"],
        Primitive.NOUL,
        "Is the current evidence sufficient to answer the research question?",
    ),
    (R["continuation_information_gap"], Primitive.NOUL, "Does a material information gap remain?"),
    (
        R["continuation_information_gain"],
        Primitive.SCORE,
        "What marginal information gain is likely from another research round?",
    ),
]


def create_research_registry() -> RubricRegistry:
    return RubricRegistry(
        RubricDefinition(
            name=name,
            domain="research",
            primitive=primitive,
            version=(
                "research.event-materiality.v2"
                if name == R["event_materiality_v2"]
                else f"{name}.v1"
            ),
            policy_version=(
                "research.event-materiality.policy.v2"
                if name == R["event_materiality_v2"]
                else f"{name}.policy.v1"
            ),
            description=description,
        )
        for name, primitive, description in _DEFINITION_DATA
    )
