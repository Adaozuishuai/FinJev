"""Run a resumable Jev baseline over a FinJev development reference dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.gateway import TypeSafeGateway
from ..domain.research.materiality import evaluate_materiality_rules, max_materiality
from ..domain.research.models import (
    ClassifyFinancialEventInput,
    FinancialEvent,
    ResearchContext,
    Source,
)
from ..domain.research.service import MATERIALITY_LEVELS, ResearchService
from ..domain.research.taxonomy import EVENT_TYPE_CRITERIA

SMOKE_RECORD_IDS = (
    "futong-annual-2023-p062-001",
    "futong-annual-2023-p061-001",
    "my-annual-2025-p105-001",
    "my-annual-2025-p073-001",
    "my-annual-2025-p032-001",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def _predicted_score_label(answer: dict[str, Any], levels: list[str]) -> str:
    probabilities = answer.get("probabilities") or {}
    legend = answer.get("legend") or {}
    if probabilities:
        key = max(probabilities, key=probabilities.get)
        legend_value = legend.get(str(key), legend.get(key))
        if isinstance(legend_value, str) and legend_value in levels:
            return legend_value
        if isinstance(legend_value, dict) and legend_value.get("label") in levels:
            return str(legend_value["label"])
    score = float(answer["score"])
    index = min(len(levels) - 1, max(0, round(score)))
    return levels[index]


def _event_input(record: dict[str, Any]) -> ClassifyFinancialEventInput:
    return ClassifyFinancialEventInput(
        event=FinancialEvent(
            headline=record["claim"],
            content=record["evidence_text"],
            company=record.get("issuer"),
            publication_date=record.get("report_period"),
            source=Source(
                publisher=record.get("issuer") or record["source_document"],
                source_type="audited_report",
                is_primary_source=True,
            ),
            numeric_facts=record.get("numeric_facts"),
        ),
        research_context=ResearchContext(
            company=record.get("issuer"),
            question=(
                "Classify the disclosed financial event and its task-level materiality using only "
                "the supplied annual-report claim and evidence."
            ),
            as_of=record.get("report_period"),
        ),
    )


def _refresh_v2_policy(row: dict[str, Any], final: str, rule_floor: str | None) -> None:
    value = float(row["composition"]["value"])
    relevance = float(row["judgments"]["relevance"]["noul"])
    follow_up = float(row["judgments"]["follow_up"]["noul"])
    if relevance <= 0.3:
        action, reason = "REJECT", "Event is unlikely to be relevant to the stated research scope."
    elif value >= 0.65:
        action, reason = "ACCEPT", f"Composite score {value:.3f} meets the acceptance threshold 0.650."
    elif value <= 0.3:
        action, reason = (
            "REJECT",
            f"Composite score {value:.3f} is at or below the rejection threshold 0.300.",
        )
    else:
        action, reason = "VERIFY", "Composite score is between the policy thresholds."
    if follow_up >= 0.75 and action == "ACCEPT":
        action, reason = "VERIFY", "Event looks material but follow-up research is required."
    if final == "critical":
        action, reason = "HUMAN_REVIEW", "A critical materiality trigger requires human review."
    elif rule_floor == "high" and action == "REJECT":
        action, reason = "VERIFY", "A deterministic high-materiality trigger prevents automatic rejection."
    row["policy"] = {
        "action": action,
        "reason": reason,
        "policy_version": "research.event-policy.v2",
    }
    row["prediction"]["policy_action"] = action


async def _evaluate_record(
    service: ResearchService,
    record: dict[str, Any],
    semaphore: asyncio.Semaphore,
    retries: int,
) -> dict[str, Any]:
    async with semaphore:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                result = await service.classify_financial_event(_event_input(record))
                event_answer = result["judgments"]["event_type"]
                materiality_answer = result["judgments"]["materiality"]
                materiality_decision = result.get("materiality_decision") or {}
                return {
                    "record_id": record["record_id"],
                    "issuer": record.get("issuer"),
                    "reference": {
                        "event_type": record["event_type"],
                        "materiality": record["materiality"],
                        "gold_action": record["gold_action"],
                    },
                    "prediction": {
                        "event_type": event_answer["choice"],
                        "materiality": materiality_decision.get("final")
                        or _predicted_score_label(materiality_answer, MATERIALITY_LEVELS),
                        "policy_action": result["policy"]["action"],
                    },
                    "materiality_decision": materiality_decision,
                    "model": result["model"],
                    "request_id": result["request_id"],
                    "state_hash": result["state_hash"],
                    "latency_ms": result["latency_ms"],
                    "usage": result.get("usage"),
                    "rubric_versions": result["rubric_versions"],
                    "policy_versions": result["policy_versions"],
                    "judgments": result["judgments"],
                    "composition": result["composition"],
                    "policy": result["policy"],
                    "status": "ok",
                    "attempts": attempt + 1,
                    "evaluated_at": datetime.now(UTC).isoformat(),
                }
            except Exception as exc:  # external API failures must be retained verbatim by type/message
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(2**attempt)
        assert last_error is not None
        return {
            "record_id": record["record_id"],
            "issuer": record.get("issuer"),
            "reference": {
                "event_type": record["event_type"],
                "materiality": record["materiality"],
                "gold_action": record["gold_action"],
            },
            "status": "error",
            "attempts": retries + 1,
            "error_type": type(last_error).__name__,
            "error": str(last_error),
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


def _classification_metrics(rows: list[dict[str, Any]], field: str, labels: list[str]) -> dict[str, Any]:
    pairs = [(row["reference"][field], row["prediction"][field]) for row in rows]
    confusion = {reference: {predicted: 0 for predicted in labels} for reference in labels}
    for reference, predicted in pairs:
        if reference in confusion and predicted in confusion[reference]:
            confusion[reference][predicted] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[other][label] for other in labels if other != label)
        false_negative = sum(confusion[label][other] for other in labels if other != label)
        precision = (
            true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        )
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = sum(confusion[label].values())
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
        }
    supported = [metrics for metrics in per_class.values() if metrics["support"]]
    return {
        "accuracy": round(sum(left == right for left, right in pairs) / len(pairs), 4) if pairs else None,
        "macro_f1_supported_classes": (
            round(sum(float(item["f1"]) for item in supported) / len(supported), 4) if supported else None
        ),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if row["status"] == "ok"]
    errors = [row for row in rows if row["status"] == "error"]
    materiality_metrics = _classification_metrics(successful, "materiality", MATERIALITY_LEVELS)
    semantic_rows = [
        {
            **row,
            "prediction": {
                **row["prediction"],
                "materiality": (row.get("materiality_decision") or {}).get("semantic")
                or row["prediction"]["materiality"],
            },
        }
        for row in successful
    ]
    high_value = [row for row in successful if row["reference"]["materiality"] in {"high", "critical"}]
    high_value_hits = [row for row in high_value if row["prediction"]["materiality"] in {"high", "critical"}]
    critical = [row for row in successful if row["reference"]["materiality"] == "critical"]
    severe_critical_undercalls = [
        row for row in critical if row["prediction"]["materiality"] in {"low", "medium"}
    ]
    latencies = sorted(row["latency_ms"] for row in successful)
    input_tokens = sum((row.get("usage") or {}).get("input_tokens") or 0 for row in successful)
    output_tokens = sum((row.get("usage") or {}).get("output_tokens") or 0 for row in successful)
    p95_index = max(0, min(len(latencies) - 1, round(0.95 * len(latencies) + 0.5) - 1)) if latencies else 0
    return {
        "record_count": len(rows),
        "successful": len(successful),
        "errors": len(errors),
        "error_rate": round(len(errors) / len(rows), 4) if rows else None,
        "models": dict(Counter(row["model"] for row in successful)),
        "event_type": _classification_metrics(successful, "event_type", list(EVENT_TYPE_CRITERIA)),
        "materiality": materiality_metrics,
        "materiality_semantic_only": _classification_metrics(
            semantic_rows, "materiality", MATERIALITY_LEVELS
        ),
        "high_value_recall": round(len(high_value_hits) / len(high_value), 4) if high_value else None,
        "high_value_support": len(high_value),
        "critical_severe_undercall_rate": (
            round(len(severe_critical_undercalls) / len(critical), 4) if critical else None
        ),
        "critical_support": len(critical),
        "latency_ms": {
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p95": latencies[p95_index] if latencies else None,
        },
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "rule_floors": dict(
            Counter((row.get("materiality_decision") or {}).get("rule_floor") or "none" for row in successful)
        ),
        "rule_triggers": dict(
            Counter(
                trigger
                for row in successful
                for trigger in (row.get("materiality_decision") or {}).get("rule_triggers", [])
            )
        ),
        "limitations": [
            "The reference core labels share an AI-assisted prefill and are not independent gold labels.",
            "Only three issuer-document-period groups and 49 records are represented.",
            "Policy action is retained for analysis but is not scored against gold_action because their semantics differ.",
        ],
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    records = _read_jsonl(args.dataset / "annotations.jsonl")
    if args.smoke:
        selected = set(SMOKE_RECORD_IDS)
        records = [record for record in records if record["record_id"] in selected]
        if len(records) != len(SMOKE_RECORD_IDS):
            raise ValueError("Smoke record IDs are missing from the dataset")
    elif args.limit:
        records = records[: args.limit]

    existing = _read_jsonl(args.output) if args.output.exists() and args.resume else []
    completed_ids = {row["record_id"] for row in existing if row.get("status") == "ok"}
    pending = [record for record in records if record["record_id"] not in completed_ids]
    gateway = TypeSafeGateway()
    service = ResearchService(gateway, materiality_profile=args.materiality_profile)
    semaphore = asyncio.Semaphore(args.concurrency)
    try:
        tasks = [_evaluate_record(service, record, semaphore, args.retries) for record in pending]
        for future in asyncio.as_completed(tasks):
            row = await future
            _append_jsonl(args.output, row)
            print(
                json.dumps(
                    {key: row.get(key) for key in ("record_id", "status", "prediction", "error")},
                    ensure_ascii=False,
                )
            )
    finally:
        await gateway.aclose()

    final_rows_by_id = {
        row["record_id"]: row
        for row in _read_jsonl(args.output)
        if row["record_id"] in {record["record_id"] for record in records}
    }
    ordered_rows = [
        final_rows_by_id[record["record_id"]] for record in records if record["record_id"] in final_rows_by_id
    ]
    for row in ordered_rows:
        if row.get("status") != "ok":
            continue
        materiality_decision = row.get("materiality_decision") or {}
        semantic = materiality_decision.get("semantic") or _predicted_score_label(
            row["judgments"]["materiality"], MATERIALITY_LEVELS
        )
        if args.materiality_profile == "v2":
            source_record = next(record for record in records if record["record_id"] == row["record_id"])
            rules = evaluate_materiality_rules(_event_input(source_record).event)
            final = max_materiality(semantic, rules.floor)
            row["materiality_decision"] = {
                "profile": "v2",
                "semantic": semantic,
                "rule_floor": rules.floor,
                "rule_triggers": list(rules.triggers),
                "rules_version": rules.policy_version,
                "final": final,
            }
            _refresh_v2_policy(row, final, rules.floor)
        else:
            final = semantic
        row["prediction"]["materiality"] = final
    _write_jsonl(args.output, ordered_rows)
    summary = summarize(ordered_rows)
    summary["dataset"] = str(args.dataset.resolve())
    summary["results"] = str(args.output.resolve())
    summary["run_mode"] = "smoke" if args.smoke else "baseline"
    summary["model_requested"] = os.getenv("TYPESAFE_MODEL", "jev-latest")
    summary["materiality_profile"] = args.materiality_profile
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--materiality-profile", choices=("v1", "v2"), default="v2")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
