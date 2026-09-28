"""Prefill missing review labels from the versioned seed annotation set.

This utility is deliberately provenance-preserving:
- claim and numeric review decisions are never modified;
- existing non-empty scalar labels are preserved;
- the packet is backed up before any write;
- every touched record is marked as AI-assisted and non-independent.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCALAR_LABEL_FIELDS = (
    "source_authority",
    "claim_type",
    "event_type",
    "direction",
    "materiality",
    "evidence_relation",
    "label_confidence",
    "gold_action",
)
PROVENANCE_NOTE = (
    "AI-assisted core-label prefill from annotation_set_v0.2 seed; "
    "not an independent reviewer label. Claim and numeric reviews were not modified."
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    temporary.write_text(payload)
    temporary.replace(path)


def prefill_packet(
    packet_path: Path,
    seeds: dict[str, dict[str, Any]],
    timestamp: str,
) -> dict[str, Any]:
    records = load_jsonl(packet_path)
    changed_records = 0
    preserved_scalar_labels = 0

    for record in records:
        seed = seeds[record["record_id"]]
        changed = False

        for field in SCALAR_LABEL_FIELDS:
            if record["labels"].get(field) in (None, ""):
                record["labels"][field] = seed[field]
                changed = True
            elif record["labels"][field] != seed[field]:
                preserved_scalar_labels += 1

        # Empty risk lists are packet placeholders, not meaningful human labels.
        if not record["labels"].get("risk_flags"):
            record["labels"]["risk_flags"] = list(seed["risk_flags"])
            changed = True

        if not str(record.get("materiality_basis") or "").strip():
            record["materiality_basis"] = seed["materiality_basis"]
            changed = True

        if changed:
            existing_note = str(record.get("reviewer_notes") or "").strip()
            if PROVENANCE_NOTE not in existing_note:
                record["reviewer_notes"] = (
                    f"{existing_note}\n{PROVENANCE_NOTE}".strip() if existing_note else PROVENANCE_NOTE
                )
            record["reviewed_at"] = timestamp
            changed_records += 1

    backup_path = packet_path.with_name(f"{packet_path.stem}.pre-ai-core-labels-{timestamp.replace(':', '')}.jsonl")
    shutil.copy2(packet_path, backup_path)
    write_jsonl(packet_path, records)
    return {
        "packet": str(packet_path),
        "backup": str(backup_path),
        "changed_records": changed_records,
        "preserved_scalar_labels": preserved_scalar_labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--reviewers", nargs="+", required=True)
    args = parser.parse_args()

    seed_records = load_jsonl(args.dataset / "annotations.jsonl")
    seeds = {record["record_id"]: record for record in seed_records}
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    results = [
        prefill_packet(args.review_root / f"{reviewer}.jsonl", seeds, timestamp)
        for reviewer in args.reviewers
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
