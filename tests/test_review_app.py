import json
import shutil
from pathlib import Path

from starlette.testclient import TestClient

from finjev.review_app import ReviewAppConfig, create_app

ROOT = Path(__file__).parents[1]


def copy_workspace(tmp_path: Path) -> ReviewAppConfig:
    review_root = tmp_path / "reviews"
    dataset_root = tmp_path / "dataset"
    shutil.copytree(ROOT / "data/reviews/v0.2", review_root)
    shutil.copytree(ROOT / "data/annotation_set_v0.2", dataset_root)
    for transient in ("completion.json", "adjudications.json"):
        (review_root / transient).unlink(missing_ok=True)
    for reviewer in ("wgy1", "wgy2"):
        reset_packet(review_root / f"{reviewer}.jsonl")
    return ReviewAppConfig(
        review_root=review_root,
        dataset_root=dataset_root,
        gold_output=tmp_path / "gold",
    )


def reset_packet(path: Path) -> None:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record.update(
            {
                "claim_review": None,
                "corrected_claim": None,
                "numeric_facts_review": None,
                "corrected_numeric_facts": None,
                "materiality_basis": None,
                "follow_up_questions": [],
                "reviewer_notes": None,
                "reviewed_at": None,
            }
        )
        record["labels"] = {field: None for field in record["labels"]}
        record["labels"]["risk_flags"] = []
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def valid_payload() -> dict:
    return {
        "claim_review": "ACCEPT",
        "corrected_claim": None,
        "numeric_facts_review": "ACCEPT",
        "corrected_numeric_facts": None,
        "labels": {
            "source_authority": "issuer_primary_reported",
            "claim_type": "reported_metric",
            "event_type": "earnings",
            "direction": "neutral",
            "materiality": "medium",
            "risk_flags": [],
            "evidence_relation": "supports",
            "label_confidence": "high",
            "gold_action": "VERIFY",
        },
        "materiality_basis": "Independent review based on the cited annual-report evidence.",
        "follow_up_questions": [],
        "reviewer_notes": None,
    }


def fill_packet(path: Path, *, conflicting_record_id: str | None = None) -> None:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    payload = valid_payload()
    for record in records:
        record.update(payload)
        record["labels"] = dict(payload["labels"])
        if record["record_id"] == conflicting_record_id:
            record["labels"]["direction"] = "negative"
        record["reviewed_at"] = "2026-09-22T14:00:00+08:00"
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_review_api_autosaves_only_editable_fields(tmp_path: Path) -> None:
    config = copy_workspace(tmp_path)
    client = TestClient(create_app(config))

    records = client.get("/api/reviewers/wgy1/records").json()
    record_id = records["items"][0]["record_id"]

    forbidden = client.put(
        f"/api/reviewers/wgy1/records/{record_id}",
        json={"proposed_claim": "tampered"},
    )
    assert forbidden.status_code == 422

    saved = client.put(
        f"/api/reviewers/wgy1/records/{record_id}",
        json=valid_payload(),
    )
    assert saved.status_code == 200
    assert saved.json()["validation_errors"] == []
    assert client.get("/api/reviewers/wgy1/records").json()["completed"] == 1
    assert client.post("/api/reviewers/wgy1/complete").status_code == 409
    assert client.get("/api/comparison").status_code == 409


def test_completed_reviews_require_conflict_adjudication_before_gold_export(tmp_path: Path) -> None:
    config = copy_workspace(tmp_path)
    packet_a = config.review_root / "wgy1.jsonl"
    packet_b = config.review_root / "wgy2.jsonl"
    conflict_id = json.loads(packet_a.read_text(encoding="utf-8").splitlines()[0])["record_id"]
    fill_packet(packet_a)
    fill_packet(packet_b, conflicting_record_id=conflict_id)
    client = TestClient(create_app(config))

    assert client.post("/api/reviewers/wgy1/complete").status_code == 200
    assert client.post("/api/reviewers/wgy2/complete").status_code == 200
    comparison = client.get("/api/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["conflicts"] == 1
    assert client.post("/api/gold/export").status_code == 409

    adjudicated = client.put(
        f"/api/adjudications/{conflict_id}",
        json={
            "resolution": "wgy1",
            "adjudicator_id": "chief_reviewer",
            "conflict_resolution": "The source describes a neutral reported metric.",
            "final": None,
        },
    )
    assert adjudicated.status_code == 200

    exported = client.post("/api/gold/export")
    assert exported.status_code == 200
    gold_records = [
        json.loads(line)
        for line in (config.gold_output / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(gold_records) == 49
    assert {record["annotation_status"] for record in gold_records} == {"adjudicated"}
    assert {tuple(record["reviewed_by"]) for record in gold_records} == {("wgy1", "wgy2")}

    assert client.post("/api/reviewers/wgy1/unlock").status_code == 200
    assert not (config.review_root / "adjudications.json").exists()
    assert len(list(config.review_root.glob("adjudications.stale-*.json"))) == 1
