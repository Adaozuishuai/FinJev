from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import TypeAdapter
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

from .models import (
    GatewayContext,
    GatewayResult,
    GatewayUsage,
    QuestionDefinition,
    TypedAnswer,
)


class AsyncJevGateway(Protocol):
    async def evaluate(
        self,
        state: Any,
        questions: Mapping[str, QuestionDefinition],
        context: GatewayContext,
    ) -> GatewayResult: ...


def _to_sdk_question(question: QuestionDefinition) -> Any:
    if question.primitive.value == "noul":
        return Noul(instructions=question.instructions, criteria=question.criteria)
    if question.primitive.value == "choice":
        return Choice(instructions=question.instructions, criteria=question.criteria or {})
    return Score(instructions=question.instructions, criteria=question.criteria or [])


def resolve_api_key() -> str:
    """Resolve credentials without ever logging the credential value."""
    environment_key = os.getenv("TYPESAFE_API_KEY")
    if environment_key:
        return environment_key

    configured_file = os.getenv("FINJEV_API_KEY_FILE")
    if configured_file:
        path = Path(configured_file).expanduser()
        if not path.is_file():
            raise RuntimeError(f"FINJEV_API_KEY_FILE does not point to a file: {path}")
        raw = path.read_text(encoding="utf-8").strip()
        name, separator, value = raw.partition("=")
        if separator and name.strip() in {"TYPESAFE_API_KEY", "JEV_API_KEY"}:
            raw = value.strip()
        raw = raw.strip('"').strip("'")
        if raw:
            return raw
        raise RuntimeError(f"FINJEV_API_KEY_FILE is empty: {path}")

    raise RuntimeError(
        "TYPESAFE_API_KEY or FINJEV_API_KEY_FILE is required for the real gateway; "
        "use a FakeGateway only in tests."
    )


class TypeSafeGateway:
    def __init__(self, client: AsyncTypeSafeClient | None = None) -> None:
        self._owns_client = client is None
        if client is not None:
            self.client = client
            return
        api_key = resolve_api_key()
        self.client = AsyncTypeSafeClient(api_key=api_key, model=os.getenv("TYPESAFE_MODEL", "jev-latest"))

    async def evaluate(
        self,
        state: Any,
        questions: Mapping[str, QuestionDefinition],
        _context: GatewayContext,
    ) -> GatewayResult:
        started = time.perf_counter()
        response = await self.client.system_one(
            state=state,
            questions={key: _to_sdk_question(question) for key, question in questions.items()},
        )
        answers: dict[str, TypedAnswer] = {}
        adapter = TypeAdapter(TypedAnswer)
        for key, answer in response.answers.items():
            answers[key] = adapter.validate_python(answer.model_dump(mode="json"))
        usage = response.usage.model_dump(mode="python") if response.usage else {}
        return GatewayResult(
            model=response.model,
            answers=answers,
            usage=GatewayUsage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
            ),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class FakeGateway:
    def __init__(
        self,
        resolver: Mapping[str, TypedAnswer]
        | Callable[
            [Any, Mapping[str, QuestionDefinition], GatewayContext],
            Mapping[str, TypedAnswer] | Awaitable[Mapping[str, TypedAnswer]],
        ],
    ) -> None:
        self.resolver = resolver

    async def evaluate(
        self,
        state: Any,
        questions: Mapping[str, QuestionDefinition],
        context: GatewayContext,
    ) -> GatewayResult:
        started = time.perf_counter()
        if callable(self.resolver):
            resolved = self.resolver(state, questions, context)
            answers = await resolved if hasattr(resolved, "__await__") else resolved
        else:
            answers = {key: self.resolver[key] for key in questions}
        return GatewayResult(
            model="fixture",
            answers=dict(answers),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
