"""Generate deterministic, label-blind review packets for independent annotators."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

TARGET_LABEL_FIELDS = (
    "source_authority",
    "claim_type",
    "event_type",
    "direction",
    "materiality",
    "risk_flags",
    "evidence_relation",
    "label_confidence",
    "gold_action",
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_order(record_id: str, reviewer_id: str) -> str:
    return hashlib.sha256(f"{reviewer_id}:{record_id}".encode()).hexdigest()


def build_reviewer_packet(
    records: list[dict[str, Any]], reviewer_id: str
) -> list[dict[str, Any]]:
    if not reviewer_id.strip():
        raise ValueError("reviewer_id must not be empty")

    packet: list[dict[str, Any]] = []
    for record in sorted(
        records,
        key=lambda item: _review_order(str(item["record_id"]), reviewer_id),
    ):
        packet.append(
            {
                "record_id": record["record_id"],
                "reviewer_id": reviewer_id,
                "source_document": record["source_document"],
                "source_path": record.get("source_path"),
                "issuer": record.get("issuer"),
                "stock_code": record.get("stock_code"),
                "report_period": record.get("report_period"),
                "pdf_page": record["pdf_page"],
                "section": record.get("section"),
                "proposed_claim": record["claim"],
                "source_excerpts": record["source_excerpts"],
                "evidence_text": record["evidence_text"],
                "proposed_numeric_facts": record.get("numeric_facts", []),
                "claim_review": None,
                "corrected_claim": None,
                "numeric_facts_review": None,
                "corrected_numeric_facts": None,
                "labels": {field: None for field in TARGET_LABEL_FIELDS},
                "materiality_basis": None,
                "follow_up_questions": [],
                "reviewer_notes": None,
                "reviewed_at": None,
            }
        )
    return packet


def review_packet_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "FinJev Independent Review Record",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "record_id",
            "reviewer_id",
            "source_document",
            "pdf_page",
            "proposed_claim",
            "source_excerpts",
            "evidence_text",
            "claim_review",
            "numeric_facts_review",
            "labels",
            "reviewed_at",
        ],
        "properties": {
            "record_id": {"type": "string", "minLength": 1},
            "reviewer_id": {"type": "string", "minLength": 1},
            "source_document": {"type": "string", "minLength": 1},
            "source_path": {"type": ["string", "null"]},
            "issuer": {"type": ["string", "null"]},
            "stock_code": {"type": ["string", "null"]},
            "report_period": {"type": ["string", "null"]},
            "pdf_page": {"type": "integer", "minimum": 1},
            "section": {"type": ["string", "null"]},
            "proposed_claim": {"type": "string", "minLength": 1},
            "source_excerpts": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "evidence_text": {"type": "string", "minLength": 1},
            "proposed_numeric_facts": {"type": "array", "items": {"type": "object"}},
            "claim_review": {"enum": [None, "ACCEPT", "EDIT", "REJECT"]},
            "corrected_claim": {"type": ["string", "null"]},
            "numeric_facts_review": {
                "enum": [None, "ACCEPT", "EDIT", "NOT_APPLICABLE"],
            },
            "corrected_numeric_facts": {
                "type": ["array", "null"],
                "items": {"type": "object"},
            },
            "labels": {
                "type": "object",
                "additionalProperties": False,
                "required": list(TARGET_LABEL_FIELDS),
                "properties": {
                    field: ({"type": ["array", "null"]} if field == "risk_flags" else {"type": ["string", "null"]})
                    for field in TARGET_LABEL_FIELDS
                },
            },
            "materiality_basis": {"type": ["string", "null"]},
            "follow_up_questions": {"type": "array", "items": {"type": "string"}},
            "reviewer_notes": {"type": ["string", "null"]},
            "reviewed_at": {"type": ["string", "null"], "format": "date-time"},
        },
    }


def write_review_packets(
    dataset_path: Path,
    output_path: Path,
    reviewer_ids: list[str],
) -> list[Path]:
    if len(set(reviewer_ids)) != len(reviewer_ids):
        raise ValueError("reviewer IDs must be unique")
    if len(reviewer_ids) < 2:
        raise ValueError("at least two independent reviewers are required")

    annotations_path = dataset_path / "annotations.jsonl"
    records = _load_jsonl(annotations_path)
    output_path.mkdir(parents=True, exist_ok=True)
    target_paths = [output_path / f"{reviewer_id}.jsonl" for reviewer_id in reviewer_ids]
    target_paths.extend([output_path / "review_packet_schema.json", output_path / "manifest.json"])
    existing = [str(path) for path in target_paths if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing review files: {existing}")

    written: list[Path] = []
    for reviewer_id in reviewer_ids:
        path = output_path / f"{reviewer_id}.jsonl"
        packet = build_reviewer_packet(records, reviewer_id)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in packet),
            encoding="utf-8",
        )
        written.append(path)

    schema_path = output_path / "review_packet_schema.json"
    schema_path.write_text(
        json.dumps(review_packet_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(schema_path)

    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_dataset": str(dataset_path.resolve()),
                "source_annotations_sha256": _file_sha256(annotations_path),
                "record_count": len(records),
                "reviewer_ids": reviewer_ids,
                "blind_fields": list(TARGET_LABEL_FIELDS),
                "packet_files": [path.name for path in written if path.suffix == ".jsonl"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewer", action="append", required=True, dest="reviewers")
    args = parser.parse_args()

    written = write_review_packets(args.dataset, args.output, args.reviewers)
    print(json.dumps({"written": [str(path) for path in written]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
