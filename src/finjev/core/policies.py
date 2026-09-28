from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import DecisionAction, NoulAnswer, PolicyDecision, ScoreAnswer

DEFAULT_POLICY_VERSION = "core.default-policy.v1"


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def apply_noul_policy(
    answer: NoulAnswer,
    *,
    positive: float,
    negative: float,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> PolicyDecision:
    if answer.noul >= positive:
        return PolicyDecision(
            action=DecisionAction.ACCEPT,
            reason=f"Noul {answer.noul:.3f} is at or above the positive threshold {positive:.3f}.",
            policy_version=policy_version,
        )
    if answer.noul <= negative:
        return PolicyDecision(
            action=DecisionAction.REJECT,
            reason=f"Noul {answer.noul:.3f} is at or below the negative threshold {negative:.3f}.",
            policy_version=policy_version,
        )
    return PolicyDecision(
        action=DecisionAction.VERIFY,
        reason=f"Noul {answer.noul:.3f} is inside the uncertainty band.",
        policy_version=policy_version,
    )


def normalize_score(answer: ScoreAnswer) -> float:
    level_count = len(answer.probabilities)
    return 0.0 if level_count <= 1 else clamp01(answer.score / (level_count - 1))


@dataclass(frozen=True)
class WeightedSignal:
    name: str
    value: float
    weight: float


def compose_weighted_score(signals: Sequence[WeightedSignal]) -> dict[str, object]:
    total_weight = sum(signal.weight for signal in signals)
    if total_weight <= 0:
        raise ValueError("Composite score requires a positive total weight")
    value = clamp01(sum(clamp01(signal.value) * signal.weight for signal in signals) / total_weight)
    return {
        "value": value,
        "signals": [
            {"name": signal.name, "value": signal.value, "weight": signal.weight} for signal in signals
        ],
    }


def action_for_composite(
    value: float,
    *,
    accept: float,
    reject: float,
    policy_version: str,
) -> PolicyDecision:
    if value >= accept:
        action = DecisionAction.ACCEPT
        reason = f"Composite score {value:.3f} meets the acceptance threshold {accept:.3f}."
    elif value <= reject:
        action = DecisionAction.REJECT
        reason = f"Composite score {value:.3f} is at or below the rejection threshold {reject:.3f}."
    else:
        action = DecisionAction.VERIFY
        reason = "Composite score is between the policy thresholds."
    return PolicyDecision(action=action, reason=reason, policy_version=policy_version)
