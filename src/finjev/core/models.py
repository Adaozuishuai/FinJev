from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Primitive(StrEnum):
    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"


class DecisionAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    VERIFY = "VERIFY"
    CONTINUE = "CONTINUE"
    STOP = "STOP"
    RETRY = "RETRY"
    ESCALATE = "ESCALATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class RubricDefinition(StrictModel):
    name: str
    domain: str
    primitive: Primitive
    version: str
    policy_version: str
    description: str


class QuestionDefinition(StrictModel):
    primitive: Primitive
    instructions: Any
    criteria: Any | None = None
    rubric: str


class NoulAnswer(StrictModel):
    type: Literal["noul"] = "noul"
    noul: float = Field(ge=0, le=1)


class ChoiceAnswer(StrictModel):
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)


class ScoreAnswer(StrictModel):
    type: Literal["score"] = "score"
    score: float
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    legend: dict[str, Any] | None = None


type TypedAnswer = NoulAnswer | ChoiceAnswer | ScoreAnswer


class GatewayContext(StrictModel):
    request_id: str
    domain: str
    rubric_versions: dict[str, str]


class GatewayUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class GatewayResult(StrictModel):
    model: str
    answers: dict[str, TypedAnswer]
    usage: GatewayUsage | None = None
    latency_ms: int


class JudgmentBatch(StrictModel):
    request_id: str
    domain: str
    judgment: str
    state_hash: str
    model: str
    rubric_versions: dict[str, str]
    policy_versions: dict[str, str]
    answers: dict[str, TypedAnswer]
    usage: GatewayUsage | None = None
    latency_ms: int


class PolicyDecision(StrictModel):
    action: DecisionAction
    reason: str
    policy_version: str
