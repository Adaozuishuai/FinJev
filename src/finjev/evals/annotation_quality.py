"""Audit a FinJev annotation set before it is used as a benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from finjev.domain.research.taxonomy import EVENT_TYPE_CRITERIA, RISK_FLAG_VOCABULARY

Severity = Literal["blocker", "warning", "info"]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class AuditReport:
    dataset_path: str
    record_count: int
    page_count: int
    distributions: dict[str, dict[str, int]]
    findings: list[Finding]

    @property
    def seed_ready(self) -> bool:
        structural_codes = {
            "missing_required_fields",
            "duplicate_record_ids",
            "broken_record_links",
            "source_hash_mismatch",
            "runtime_taxonomy_mismatch",
        }
        return not any(
            finding.severity == "blocker" and finding.code in structural_codes
            for finding in self.findings
        )

    @property
    def gold_ready(self) -> bool:
        return not any(finding.severity == "blocker" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "record_count": self.record_count,
            "page_count": self.page_count,
            "seed_ready": self.seed_ready,
            "gold_ready": self.gold_ready,
            "distributions": self.distributions,
            "findings": [asdict(finding) for finding in self.findings],
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(record.get(field)) for record in records).most_common())


def audit_annotation_set(dataset_path: Path) -> AuditReport:
    manifest = _load_json(dataset_path / "manifest.json")
    schema = _load_json(dataset_path / "label_schema.json")
    records = _load_jsonl(dataset_path / "annotations.jsonl")
    pages = _load_jsonl(dataset_path / "pages.jsonl")
    findings: list[Finding] = []

    required = schema.get("required", [])
    missing = Counter(
        field
        for record in records
        for field in required
        if field not in record or record[field] is None or record[field] == ""
    )
    if missing:
        findings.append(
            Finding(
                "blocker",
                "missing_required_fields",
                "Required fields are missing.",
                dict(missing),
            )
        )

    record_ids = [str(record.get("record_id")) for record in records]
    duplicate_ids = {key: count for key, count in Counter(record_ids).items() if count > 1}
    if duplicate_ids:
        findings.append(
            Finding(
                "blocker",
                "duplicate_record_ids",
                "Record identifiers are not unique.",
                duplicate_ids,
            )
        )

    record_id_set = set(record_ids)
    broken_links = [
        {"record_id": record.get("record_id"), "linked_record_id": linked_id}
        for record in records
        for linked_id in record.get("linked_record_ids", [])
        if linked_id not in record_id_set
    ]
    if broken_links:
        findings.append(
            Finding(
                "blocker",
                "broken_record_links",
                "Linked record identifiers do not resolve.",
                {"links": broken_links},
            )
        )

    sources = manifest.get("sources") or [manifest]
    for source in sources:
        source_path = Path(str(source.get("source_path", "")))
        expected_hash = source.get("source_sha256")
        if not source_path.is_file():
            findings.append(
                Finding(
                    "warning",
                    "source_file_unavailable",
                    "A provenance source file is unavailable.",
                    {"path": str(source_path)},
                )
            )
        elif expected_hash and _sha256(source_path) != expected_hash:
            findings.append(
                Finding(
                    "blocker",
                    "source_hash_mismatch",
                    "A source PDF no longer matches its manifest hash.",
                    {"path": str(source_path), "expected_sha256": expected_hash},
                )
            )

    runtime_events = set(EVENT_TYPE_CRITERIA)
    schema_events = set(schema.get("properties", {}).get("event_type", {}).get("enum", []))
    if runtime_events != schema_events:
        findings.append(
            Finding(
                "blocker",
                "runtime_taxonomy_mismatch",
                "Runtime and annotation event-type vocabularies differ.",
                {
                    "schema_only": sorted(schema_events - runtime_events),
                    "runtime_only": sorted(runtime_events - schema_events),
                },
            )
        )

    used_risk_flags = Counter(flag for record in records for flag in record.get("risk_flags", []))
    unknown_risk_flags = {
        flag: count for flag, count in used_risk_flags.items() if flag not in RISK_FLAG_VOCABULARY
    }
    if unknown_risk_flags:
        findings.append(
            Finding(
                "warning",
                "risk_flag_vocabulary_drift",
                "Records contain risk flags outside the documented controlled vocabulary.",
                unknown_risk_flags,
            )
        )

    annotation_status = Counter(record.get("annotation_status") for record in records)
    incomplete_adjudication = [
        record.get("record_id")
        for record in records
        if record.get("annotation_status") == "adjudicated"
        and (
            not record.get("reviewed_by")
            or not record.get("reviewed_at")
            or not record.get("conflict_resolution")
            or record.get("review_status") != "adjudicated"
        )
    ]
    if incomplete_adjudication:
        findings.append(
            Finding(
                "blocker",
                "incomplete_adjudication_metadata",
                "Adjudicated records must preserve reviewers, time, conflict resolution, and review status.",
                {"record_ids": incomplete_adjudication},
            )
        )
    non_adjudicated = len(records) - annotation_status.get("adjudicated", 0)
    if non_adjudicated:
        findings.append(
            Finding(
                "blocker",
                "records_not_adjudicated",
                "Non-adjudicated records cannot be treated as gold labels.",
                {"non_adjudicated": non_adjudicated, "status_distribution": dict(annotation_status)},
            )
        )

    annotators = Counter(record.get("annotator") for record in records)
    if len(annotators) < 2:
        findings.append(
            Finding(
                "blocker",
                "single_annotator",
                "Inter-annotator agreement cannot be measured with one annotator.",
                {"annotators": dict(annotators)},
            )
        )

    group_counts = {
        "issuers": len({record.get("issuer") for record in records}),
        "documents": len({record.get("source_document") for record in records}),
        "periods": len({record.get("report_period") for record in records}),
    }
    group_sizes = Counter(
        " | ".join(
            str(value)
            for value in (
                record.get("issuer"),
                record.get("source_document"),
                record.get("report_period"),
            )
        )
        for record in records
    )
    split_evidence = {
        **group_counts,
        "composite_groups": len(group_sizes),
        "group_sizes": dict(group_sizes),
    }
    if len(group_sizes) < 3:
        findings.append(
            Finding(
                "blocker",
                "insufficient_split_groups",
                "At least three issuer-document-period groups are required for a leakage-safe three-way split.",
                split_evidence,
            )
        )
    elif group_sizes and max(group_sizes.values()) >= 3 * min(group_sizes.values()):
        findings.append(
            Finding(
                "warning",
                "group_size_imbalance",
                "Group sizes are highly imbalanced, so one-group holdout metrics will have unequal variance.",
                split_evidence,
            )
        )

    gold_actions = Counter(record.get("gold_action") for record in records)
    absent_actions = sorted(
        set(schema.get("properties", {}).get("gold_action", {}).get("enum", [])) - set(gold_actions)
    )
    if absent_actions:
        findings.append(
            Finding(
                "warning",
                "uncovered_gold_actions",
                "Some policy outcomes have no examples, so per-class evaluation would be incomplete.",
                {"absent": absent_actions, "distribution": dict(gold_actions)},
            )
        )

    visual_page_keys = {
        (page.get("source_document"), page.get("pdf_page"))
        for page in pages
        if page.get("visual_review_status") == "sampled"
    }
    visually_reviewed_records = sum(
        (record.get("source_document"), record.get("pdf_page")) in visual_page_keys
        for record in records
    )
    findings.append(
        Finding(
            "info",
            "visual_review_coverage",
            "Visual review coverage is reported separately from text/schema validation.",
            {
                "reviewed_pages": len(visual_page_keys),
                "total_pages": len(pages),
                "reviewed_records": visually_reviewed_records,
                "total_records": len(records),
            },
        )
    )

    distributions = {
        field: _distribution(records, field)
        for field in (
            "annotation_status",
            "annotator",
            "event_type",
            "direction",
            "materiality",
            "evidence_relation",
            "gold_action",
            "label_confidence",
        )
    }
    return AuditReport(str(dataset_path.resolve()), len(records), len(pages), distributions, findings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset",
        type=Path,
        help="Directory containing the annotation-set JSON/JSONL files",
    )
    parser.add_argument(
        "--require-gold",
        action="store_true",
        help="Exit non-zero unless all gold-readiness blockers are resolved",
    )
    args = parser.parse_args()

    report = audit_annotation_set(args.dataset)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if args.require_gold and not report.gold_ready:
        raise SystemExit(1)
    if not report.seed_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
