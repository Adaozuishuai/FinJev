import json

import pytest

from finjev.evals.production_shadow import _build_input, _read_jsonl


def test_build_input_accepts_production_event() -> None:
    record_id, input_data = _build_input(
        {
            "record_id": "prod-001",
            "company": "Acme",
            "headline": "Acme reports annual results",
            "content": "Revenue increased by 10%.",
            "source": {"publisher": "Acme", "source_type": "company_release"},
            "research_question": "Is this event material?",
        }
    )

    assert record_id == "prod-001"
    assert input_data.event.source is not None
    assert input_data.research_context is not None


def test_build_input_requires_record_id() -> None:
    with pytest.raises(ValueError, match="record_id is required"):
        _build_input({"headline": "Missing id"})


def test_read_jsonl_tracks_line_number(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"record_id": "one", "headline": "Event"}) + "\n", encoding="utf-8")

    assert _read_jsonl(path)[0]["_line_number"] == 1
