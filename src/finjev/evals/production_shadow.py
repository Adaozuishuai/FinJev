"""Run advisory-only FinJev judgments over unlabeled production-like JSONL events."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..core.gateway import TypeSafeGateway
from ..domain.research.models import (
    ClassifyFinancialEventInput,
    FinancialEvent,
    ResearchContext,
    Source,
)
from ..domain.research.service import ResearchService


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object")
        value["_line_number"] = line_number
        rows.append(value)
    return rows


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def _build_input(record: dict[str, Any]) -> tuple[str, ClassifyFinancialEventInput]:
    record_id = str(record.get("record_id") or "").strip()
    if not record_id:
        raise ValueError("record_id is required")
    source_value = record.get("source")
    source = Source.model_validate(source_value) if source_value else None
    event = FinancialEvent(
        headline=record.get("headline"),
        content=record.get("content"),
        company=record.get("company"),
        publication_date=record.get("publication_date"),
        source=source,
        related_entities=record.get("related_entities"),
        numeric_facts=record.get("numeric_facts"),
    )
    question = str(record.get("research_question") or "").strip()
    context = (
        ResearchContext(
            company=record.get("company"),
            question=question,
            known_claims=record.get("known_claims"),
            as_of=record.get("as_of"),
        )
        if question
        else None
    )
    return record_id, ClassifyFinancialEventInput(event=event, research_context=context)


async def _evaluate(
    service: ResearchService,
    record: dict[str, Any],
    semaphore: asyncio.Semaphore,
    retries: int,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or f"line-{record.get('_line_number', 'unknown')}")
    try:
        validated_id, input_data = _build_input(record)
        record_id = validated_id
    except (ValueError, ValidationError) as exc:
        return {
            "record_id": record_id,
            "status": "invalid_input",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "evaluated_at": datetime.now(UTC).isoformat(),
        }

    async with semaphore:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                result = await service.classify_financial_event(input_data)
                return {
                    "record_id": record_id,
                    "status": "ok",
                    "attempts": attempt + 1,
                    "decision_authority": "advisory_only",
                    "result": result,
                    "evaluated_at": datetime.now(UTC).isoformat(),
                }
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(2**attempt)
        assert last_error is not None
        return {
            "record_id": record_id,
            "status": "error",
            "attempts": retries + 1,
            "error_type": type(last_error).__name__,
            "error": str(last_error),
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    records = _read_jsonl(args.input)
    existing = _read_jsonl(args.output) if args.resume and args.output.exists() else []
    completed = {row.get("record_id") for row in existing if row.get("status") == "ok"}
    pending = [record for record in records if record.get("record_id") not in completed]
    gateway = TypeSafeGateway()
    service = ResearchService(gateway, materiality_profile=args.materiality_profile)
    semaphore = asyncio.Semaphore(args.concurrency)
    try:
        tasks = [_evaluate(service, record, semaphore, args.retries) for record in pending]
        for future in asyncio.as_completed(tasks):
            row = await future
            _append_jsonl(args.output, row)
            print(
                json.dumps(
                    {
                        "record_id": row["record_id"],
                        "status": row["status"],
                        "action": (row.get("result") or {}).get("policy", {}).get("action"),
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        await gateway.aclose()

    rows = _read_jsonl(args.output)
    selected_ids = {record.get("record_id") for record in records}
    latest_by_id = {row.get("record_id"): row for row in rows if row.get("record_id") in selected_ids}
    selected = list(latest_by_id.values())
    statuses: dict[str, int] = {}
    actions: dict[str, int] = {}
    for row in selected:
        status = str(row.get("status"))
        statuses[status] = statuses.get(status, 0) + 1
        action = (row.get("result") or {}).get("policy", {}).get("action")
        if action:
            actions[action] = actions.get(action, 0) + 1
    summary = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "record_count": len(records),
        "materiality_profile": args.materiality_profile,
        "model_requested": os.getenv("TYPESAFE_MODEL", "jev-latest"),
        "decision_authority": "advisory_only",
        "statuses": statuses,
        "actions": actions,
        "warning": "Unlabeled production data measures operability and review yield, not accuracy.",
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--materiality-profile", choices=("v1", "v2"), default="v2")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
