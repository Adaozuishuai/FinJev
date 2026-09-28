"""Build an explicitly non-gold development reference from completed review packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .review_packets import TARGET_LABEL_FIELDS


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decision(record: dict[str, Any]) -> dict[str, Any]:
    claim = record.get("corrected_claim") if record.get("claim_review") == "EDIT" else record["proposed_claim"]
    if record.get("numeric_facts_review") == "EDIT":
        numeric_facts = record.get("corrected_numeric_facts") or []
    elif record.get("numeric_facts_review") == "NOT_APPLICABLE":
        numeric_facts = []
    else:
        numeric_facts = record.get("proposed_numeric_facts") or []
    return {
        "claim": claim,
        "numeric_facts": numeric_facts,
        "labels": record["labels"],
        "materiality_basis": record["materiality_basis"],
        "follow_up_questions": record.get("follow_up_questions", []),
    }


def build_development_reference(dataset_root: Path, review_root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Development reference already exists: {output}")

    base_manifest = _read_json(dataset_root / "manifest.json")
    review_manifest = _read_json(review_root / "manifest.json")
    completion = _read_json(review_root / "completion.json")
    adjudications = _read_json(review_root / "adjudications.json")
    reviewers = review_manifest["reviewer_ids"]
    if set(completion) != set(reviewers):
        raise ValueError("Every review packet must be completed and locked")

    base_records = {record["record_id"]: record for record in _read_jsonl(dataset_root / "annotations.jsonl")}
    packets = {
        reviewer: {record["record_id"]: record for record in _read_jsonl(review_root / f"{reviewer}.jsonl")}
        for reviewer in reviewers
    }
    if any(set(packet) != set(base_records) for packet in packets.values()):
        raise ValueError("Review packets do not match the source annotation records")

    generated_at = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    conflict_records = 0
    conflict_fields = 0
    for record_id, base in base_records.items():
        decisions = {reviewer: _decision(packets[reviewer][record_id]) for reviewer in reviewers}
        differing = [
            field
            for field in TARGET_LABEL_FIELDS
            if decisions[reviewers[0]]["labels"][field] != decisions[reviewers[1]]["labels"][field]
        ]
        if decisions[reviewers[0]]["claim"] != decisions[reviewers[1]]["claim"]:
            differing.append("claim")
        if decisions[reviewers[0]]["numeric_facts"] != decisions[reviewers[1]]["numeric_facts"]:
            differing.append("numeric_facts")

        adjudication = adjudications.get(record_id)
        if differing:
            conflict_records += 1
            conflict_fields += len(differing)
            if not adjudication:
                raise ValueError(f"Unresolved review conflict: {record_id} {differing}")
            selected = adjudication["resolution"]
            if selected == "custom":
                decision = adjudication["final"]
                labels = {field: decision[field] for field in TARGET_LABEL_FIELDS}
                decision = {**decision, "labels": labels}
            else:
                decision = decisions[selected]
            resolution = adjudication["conflict_resolution"]
        else:
            decision = decisions[reviewers[0]]
            resolution = (
                "Claim and numeric reviews agreed. Core labels were produced by a shared AI-assisted "
                "prefill and therefore do not constitute independent reviewer agreement."
            )

        record = deepcopy(base)
        record["claim"] = decision["claim"]
        record["numeric_facts"] = decision["numeric_facts"]
        for field in TARGET_LABEL_FIELDS:
            record[field] = decision["labels"][field]
        record["materiality_basis"] = decision["materiality_basis"]
        record["follow_up_questions"] = decision.get("follow_up_questions", [])
        record["annotation_status"] = "human_reviewed"
        record["review_status"] = "reviewed"
        record["annotator"] = "human_claim_numeric_plus_shared_ai_core"
        record["reviewed_by"] = reviewers
        record["reviewed_at"] = generated_at
        record["conflict_resolution"] = resolution
        record["label_version"] = "0.3-dev-reference"
        records.append(record)

    schema = _read_json(dataset_root / "label_schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{record['record_id']}: {error.message}"
        for record in records
        for error in validator.iter_errors(record)
    ]
    if errors:
        raise ValueError(f"Development reference validation failed: {errors[:5]}")

    output.mkdir(parents=True)
    for name in ("label_schema.json", "labeling_rules.md", "pages.jsonl"):
        shutil.copy2(dataset_root / name, output / name)
    _write_jsonl(output / "annotations.jsonl", records)
    manifest = {
        **base_manifest,
        "dataset_version": "0.3-dev-reference",
        "status": "development_reference_not_gold",
        "parent_dataset": str(dataset_root),
        "intended_use": ["development_baseline", "pipeline_smoke_test", "error_analysis"],
        "prohibited_claims": [
            "independent_core-label_agreement",
            "gold_benchmark_performance",
            "production_generalization",
        ],
        "review_provenance": {
            "claim_and_numeric": "human reviewed in both packets",
            "core_labels": "shared AI-assisted prefill; not independent",
            "reviewers": reviewers,
            "adjudicator": "codex_evidence_rules",
            "conflicting_records": conflict_records,
            "conflicting_fields": conflict_fields,
        },
        "review_packet_sha256": {
            reviewer: _sha256(review_root / f"{reviewer}.jsonl") for reviewer in reviewers
        },
        "source_annotations_sha256": _sha256(dataset_root / "annotations.jsonl"),
        "generated_at_utc": generated_at,
    }
    _write_json(output / "manifest.json", manifest)
    (output / "README.md").write_text(
        "# FinJev v0.3 development reference\n\n"
        "This dataset is for development evaluation only. Claim and numeric checks were completed "
        "in both review packets, while core labels came from a shared AI-assisted prefill. It is "
        "not a gold benchmark and cannot support claims of independent inter-annotator agreement.\n",
        encoding="utf-8",
    )
    return {
        "output": str(output.resolve()),
        "record_count": len(records),
        "conflicting_records": conflict_records,
        "conflicting_fields": conflict_fields,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("reviews", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build_development_reference(args.dataset, args.reviews, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
