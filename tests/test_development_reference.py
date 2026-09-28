import json
import shutil
from pathlib import Path

from finjev.evals.development_reference import build_development_reference

ROOT = Path(__file__).parents[1]


def test_build_development_reference_is_explicitly_not_gold(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    reviews = tmp_path / "reviews"
    output = tmp_path / "dev-reference"
    shutil.copytree(ROOT / "data/annotation_set_v0.2", dataset)
    shutil.copytree(ROOT / "data/reviews/v0.2", reviews)

    result = build_development_reference(dataset, reviews, output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (output / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["record_count"] == 49
    assert result["conflicting_records"] == 2
    assert result["conflicting_fields"] == 3
    assert manifest["status"] == "development_reference_not_gold"
    assert "gold_benchmark_performance" in manifest["prohibited_claims"]
    assert {record["annotation_status"] for record in records} == {"human_reviewed"}
    assert {record["label_version"] for record in records} == {"0.3-dev-reference"}
