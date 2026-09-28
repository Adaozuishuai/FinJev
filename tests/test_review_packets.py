import json

import pytest

from finjev.evals.review_packets import TARGET_LABEL_FIELDS, build_reviewer_packet, write_review_packets


def sample_record(record_id: str) -> dict:
    return {
        "record_id": record_id,
        "source_document": "report.pdf",
        "source_path": "/tmp/report.pdf",
        "issuer": "Example Co",
        "stock_code": "000001",
        "report_period": "2025",
        "pdf_page": 1,
        "section": "Results",
        "claim": "Revenue increased.",
        "source_excerpts": ["Revenue increased by 10%."],
        "evidence_text": "Revenue increased by 10%.",
        "numeric_facts": [],
        "source_authority": "issuer_primary_reported",
        "claim_type": "reported_metric",
        "event_type": "earnings",
        "direction": "positive",
        "materiality": "high",
        "risk_flags": ["earnings_quality"],
        "evidence_relation": "supports",
        "label_confidence": "high",
        "gold_action": "VERIFY",
    }


def test_review_packet_blinds_seed_labels() -> None:
    packet = build_reviewer_packet([sample_record("record-1")], "reviewer_a")

    assert packet[0]["labels"] == {field: None for field in TARGET_LABEL_FIELDS}
    assert packet[0]["proposed_claim"] == "Revenue increased."
    assert "event_type" not in packet[0]
    assert "gold_action" not in packet[0]


def test_reviewer_order_is_deterministic_and_reviewer_specific() -> None:
    records = [sample_record(f"record-{index}") for index in range(20)]

    first = [record["record_id"] for record in build_reviewer_packet(records, "reviewer_a")]
    repeated = [record["record_id"] for record in build_reviewer_packet(records, "reviewer_a")]
    second = [record["record_id"] for record in build_reviewer_packet(records, "reviewer_b")]

    assert first == repeated
    assert first != second


def test_write_review_packets_requires_two_unique_reviewers(tmp_path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "annotations.jsonl").write_text(
        json.dumps(sample_record("record-1")) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="at least two"):
        write_review_packets(dataset, tmp_path / "reviews", ["reviewer_a"])
    with pytest.raises(ValueError, match="unique"):
        write_review_packets(dataset, tmp_path / "reviews", ["reviewer_a", "reviewer_a"])

    written = write_review_packets(
        dataset,
        tmp_path / "reviews",
        ["reviewer_a", "reviewer_b"],
    )
    assert {path.name for path in written} == {
        "reviewer_a.jsonl",
        "reviewer_b.jsonl",
        "review_packet_schema.json",
        "manifest.json",
    }
