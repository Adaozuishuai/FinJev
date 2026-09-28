from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import Primitive, QuestionDefinition, RubricDefinition


class RubricRegistry:
    def __init__(self, definitions: Iterable[RubricDefinition] = ()) -> None:
        self._definitions: dict[str, RubricDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: RubricDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Rubric already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> RubricDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"Unknown rubric: {name}") from exc

    def question(self, rubric: str, instructions: Any, criteria: Any | None = None) -> QuestionDefinition:
        definition = self.get(rubric)
        return QuestionDefinition(
            primitive=definition.primitive,
            instructions=instructions,
            criteria=criteria,
            rubric=rubric,
        )

    def versions_for(self, questions: Mapping[str, QuestionDefinition]) -> dict[str, str]:
        return {question.rubric: self.get(question.rubric).version for question in questions.values()}

    def policy_versions_for(self, questions: Mapping[str, QuestionDefinition]) -> dict[str, str]:
        return {question.rubric: self.get(question.rubric).policy_version for question in questions.values()}

    def primitive_for(self, rubric: str) -> Primitive:
        return self.get(rubric).primitive
