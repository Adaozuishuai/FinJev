import json
from pathlib import Path

from finjev.domain.research.taxonomy import RISK_FLAG_VOCABULARY
from finjev.evals.annotation_quality import audit_annotation_set

DATASET = Path(__file__).parents[1] / "data" / "annotation_set_v0.1"
DATASET_V0_2 = Path(__file__).parents[1] / "data" / "annotation_set_v0.2"


def test_seed_set_is_structurally_ready_but_not_gold_ready() -> None:
    report = audit_annotation_set(DATASET)

    assert report.record_count == 34
    assert report.page_count == 54
    assert report.seed_ready is True
    assert report.gold_ready is False

    findings = {finding.code: finding for finding in report.findings}
    assert findings["records_not_adjudicated"].evidence["non_adjudicated"] == 34
    assert findings["single_annotator"].severity == "blocker"
    assert findings["insufficient_split_groups"].evidence["composite_groups"] == 1
    assert findings["visual_review_coverage"].evidence["reviewed_pages"] == 4
    assert "risk_flag_vocabulary_drift" not in findings


def test_runtime_event_taxonomy_matches_annotation_schema() -> None:
    report = audit_annotation_set(DATASET)

    assert "runtime_taxonomy_mismatch" not in {finding.code for finding in report.findings}


def test_schema_can_represent_required_adjudication_metadata() -> None:
    schema = json.loads((DATASET / "label_schema.json").read_text(encoding="utf-8"))

    assert {"reviewed_by", "reviewed_at", "conflict_resolution"} <= set(schema["properties"])
    assert schema["allOf"][0]["then"]["properties"]["review_status"] == {
        "const": "adjudicated"
    }


def test_v0_2_adds_two_sources_without_structural_regressions() -> None:
    report = audit_annotation_set(DATASET_V0_2)

    assert report.record_count == 49
    assert report.page_count == 67
    assert report.seed_ready is True
    assert report.gold_ready is False
    finding_codes = {finding.code for finding in report.findings}
    assert "source_hash_mismatch" not in finding_codes
    assert "runtime_taxonomy_mismatch" not in finding_codes
    assert "insufficient_split_groups" not in finding_codes
    assert "group_size_imbalance" in finding_codes


def test_v0_2_new_records_use_controlled_risk_flags() -> None:
    records = [
        json.loads(line)
        for line in (DATASET_V0_2 / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    new_records = [record for record in records if record["label_version"] == "0.2"]

    assert len(new_records) == 15
    assert {
        record["issuer"] for record in new_records
    } == {"天津富通信息科技股份有限公司", "廊坊发展股份有限公司"}
    assert not {
        flag
        for record in new_records
        for flag in record["risk_flags"]
        if flag not in RISK_FLAG_VOCABULARY
    }
