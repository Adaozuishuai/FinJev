"""Local browser workbench for independent annotation, adjudication, and gold export."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import threading
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from jsonschema import Draft202012Validator, FormatChecker
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .domain.research.taxonomy import RISK_FLAG_VOCABULARY
from .evals.review_packets import TARGET_LABEL_FIELDS

EDITABLE_FIELDS = {
    "claim_review",
    "corrected_claim",
    "numeric_facts_review",
    "corrected_numeric_facts",
    "labels",
    "materiality_basis",
    "follow_up_questions",
    "reviewer_notes",
}
COMPARISON_FIELDS = ("claim_review", "claim", "numeric_facts_review", "numeric_facts", *TARGET_LABEL_FIELDS)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class ReviewAppConfig:
    review_root: Path
    dataset_root: Path
    gold_output: Path


class ReviewStore:
    def __init__(self, config: ReviewAppConfig) -> None:
        self.config = config
        self.lock = threading.RLock()
        self.review_manifest = _read_json(config.review_root / "manifest.json")
        self.dataset_manifest = _read_json(config.dataset_root / "manifest.json")
        self.annotation_schema = _read_json(config.dataset_root / "label_schema.json")
        self.reviewers = tuple(self.review_manifest["reviewer_ids"])
        self.base_records = {
            record["record_id"]: record
            for record in _read_jsonl(config.dataset_root / "annotations.jsonl")
        }
        expected_hash = self.review_manifest["source_annotations_sha256"]
        actual_hash = _sha256(config.dataset_root / "annotations.jsonl")
        if actual_hash != expected_hash:
            raise ValueError("Review packets no longer match the source annotation dataset")
        self.enums = {
            field: self.annotation_schema["properties"][field]["enum"]
            for field in TARGET_LABEL_FIELDS
            if field != "risk_flags"
        }
        self.source_paths = {
            record["source_document"]: Path(record["source_path"])
            for record in self.base_records.values()
        }
        self._validate_packet_sets()

    @property
    def completion_path(self) -> Path:
        return self.config.review_root / "completion.json"

    @property
    def adjudications_path(self) -> Path:
        return self.config.review_root / "adjudications.json"

    def _packet_path(self, reviewer: str) -> Path:
        if reviewer not in self.reviewers:
            raise HTTPException(404, "Unknown reviewer")
        return self.config.review_root / f"{reviewer}.jsonl"

    def _load_packet(self, reviewer: str) -> list[dict[str, Any]]:
        return _read_jsonl(self._packet_path(reviewer))

    def _validate_packet_sets(self) -> None:
        expected = set(self.base_records)
        for reviewer in self.reviewers:
            packet_ids = {record["record_id"] for record in self._load_packet(reviewer)}
            if packet_ids != expected:
                raise ValueError(f"Review packet {reviewer} does not match the source record set")

    def completion(self) -> dict[str, Any]:
        return _read_json(self.completion_path, {})

    def is_locked(self, reviewer: str) -> bool:
        return reviewer in self.completion()

    def _validate_labels(self, labels: Any, *, allow_null: bool) -> dict[str, Any]:
        if not isinstance(labels, dict) or set(labels) != set(TARGET_LABEL_FIELDS):
            raise HTTPException(422, "labels must contain every configured label field")
        validated: dict[str, Any] = {}
        for field in TARGET_LABEL_FIELDS:
            value = labels[field]
            if value is None and allow_null:
                validated[field] = None
                continue
            if field == "risk_flags":
                if not isinstance(value, list) or any(flag not in RISK_FLAG_VOCABULARY for flag in value):
                    raise HTTPException(422, "risk_flags contains an unknown value")
                validated[field] = sorted(set(value))
            elif value not in self.enums[field]:
                raise HTTPException(422, f"Invalid {field}: {value!r}")
            else:
                validated[field] = value
        return validated

    def record_errors(self, record: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if record.get("claim_review") not in {"ACCEPT", "EDIT", "REJECT"}:
            errors.append("claim_review")
        if record.get("claim_review") == "EDIT" and not str(record.get("corrected_claim") or "").strip():
            errors.append("corrected_claim")
        if record.get("numeric_facts_review") not in {"ACCEPT", "EDIT", "NOT_APPLICABLE"}:
            errors.append("numeric_facts_review")
        if record.get("numeric_facts_review") == "EDIT" and not isinstance(
            record.get("corrected_numeric_facts"), list
        ):
            errors.append("corrected_numeric_facts")
        labels = record.get("labels", {})
        for field in TARGET_LABEL_FIELDS:
            value = labels.get(field)
            if value is None or (field == "risk_flags" and not isinstance(value, list)):
                errors.append(f"labels.{field}")
        if not str(record.get("materiality_basis") or "").strip():
            errors.append("materiality_basis")
        return errors

    def list_records(self, reviewer: str) -> dict[str, Any]:
        records = self._load_packet(reviewer)
        items = [
            {
                "record_id": record["record_id"],
                "issuer": record.get("issuer"),
                "source_document": record["source_document"],
                "pdf_page": record["pdf_page"],
                "section": record.get("section"),
                "complete": not self.record_errors(record),
            }
            for record in records
        ]
        completed = sum(item["complete"] for item in items)
        return {
            "reviewer": reviewer,
            "items": items,
            "completed": completed,
            "total": len(items),
            "locked": self.is_locked(reviewer),
        }

    def get_record(self, reviewer: str, record_id: str) -> dict[str, Any]:
        for record in self._load_packet(reviewer):
            if record["record_id"] == record_id:
                return {**record, "validation_errors": self.record_errors(record)}
        raise HTTPException(404, "Unknown record")

    def save_record(self, reviewer: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.is_locked(reviewer):
                raise HTTPException(409, "This review packet is completed and locked")
            unexpected = set(payload) - EDITABLE_FIELDS
            if unexpected:
                raise HTTPException(422, f"Unexpected editable fields: {sorted(unexpected)}")
            records = self._load_packet(reviewer)
            target = next((record for record in records if record["record_id"] == record_id), None)
            if target is None:
                raise HTTPException(404, "Unknown record")
            for field in EDITABLE_FIELDS - {"labels"}:
                if field in payload:
                    target[field] = payload[field]
            if "labels" in payload:
                target["labels"] = self._validate_labels(payload["labels"], allow_null=True)
            if target.get("claim_review") not in {None, "ACCEPT", "EDIT", "REJECT"}:
                raise HTTPException(422, "Invalid claim_review")
            if target.get("numeric_facts_review") not in {
                None,
                "ACCEPT",
                "EDIT",
                "NOT_APPLICABLE",
            }:
                raise HTTPException(422, "Invalid numeric_facts_review")
            if not isinstance(target.get("follow_up_questions"), list):
                raise HTTPException(422, "follow_up_questions must be a list")
            errors = self.record_errors(target)
            target["reviewed_at"] = None if errors else _utc_now()
            _atomic_write_jsonl(self._packet_path(reviewer), records)
            return {**target, "validation_errors": errors}

    def complete_reviewer(self, reviewer: str) -> dict[str, Any]:
        with self.lock:
            records = self._load_packet(reviewer)
            incomplete = [record["record_id"] for record in records if self.record_errors(record)]
            if incomplete:
                raise HTTPException(
                    409,
                    f"{len(incomplete)} records are incomplete; first IDs: {incomplete[:5]}",
                )
            completion = self.completion()
            completion[reviewer] = {
                "completed_at": _utc_now(),
                "packet_sha256": _sha256(self._packet_path(reviewer)),
            }
            _atomic_write_json(self.completion_path, completion)
            return completion[reviewer]

    def unlock_reviewer(self, reviewer: str) -> None:
        with self.lock:
            completion = self.completion()
            completion.pop(reviewer, None)
            _atomic_write_json(self.completion_path, completion)
            if self.adjudications_path.exists():
                timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                stale_path = self.config.review_root / f"adjudications.stale-{timestamp}.json"
                os.replace(self.adjudications_path, stale_path)

    def all_completed(self) -> bool:
        return all(reviewer in self.completion() for reviewer in self.reviewers)

    def _decision(self, record: dict[str, Any]) -> dict[str, Any]:
        claim = (
            record.get("corrected_claim")
            if record.get("claim_review") == "EDIT"
            else record["proposed_claim"]
        )
        if record.get("numeric_facts_review") == "EDIT":
            numeric_facts = record.get("corrected_numeric_facts") or []
        elif record.get("numeric_facts_review") == "NOT_APPLICABLE":
            numeric_facts = []
        else:
            numeric_facts = record.get("proposed_numeric_facts", [])
        return {
            "claim_review": record["claim_review"],
            "claim": claim,
            "numeric_facts_review": record["numeric_facts_review"],
            "numeric_facts": numeric_facts,
            **record["labels"],
            "materiality_basis": record["materiality_basis"],
            "follow_up_questions": record.get("follow_up_questions", []),
            "reviewer_notes": record.get("reviewer_notes"),
        }

    @staticmethod
    def _cohen_kappa(values_a: list[Any], values_b: list[Any]) -> float | None:
        if not values_a:
            return None
        observed = sum(left == right for left, right in zip(values_a, values_b, strict=True)) / len(values_a)
        counts_a = Counter(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values_a)
        counts_b = Counter(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values_b)
        categories = set(counts_a) | set(counts_b)
        expected = sum(counts_a[key] * counts_b[key] for key in categories) / (len(values_a) ** 2)
        if expected == 1:
            return 1.0 if observed == 1 else None
        return round((observed - expected) / (1 - expected), 4)

    def comparison(self) -> dict[str, Any]:
        if not self.all_completed():
            raise HTTPException(409, "Both reviewers must complete and lock their packets first")
        packets = {
            reviewer: {record["record_id"]: record for record in self._load_packet(reviewer)}
            for reviewer in self.reviewers
        }
        left_id, right_id = self.reviewers[:2]
        adjudications = _read_json(self.adjudications_path, {})
        items: list[dict[str, Any]] = []
        metric_values: dict[str, tuple[list[Any], list[Any]]] = {
            field: ([], []) for field in COMPARISON_FIELDS
        }
        for record_id, base in self.base_records.items():
            left = self._decision(packets[left_id][record_id])
            right = self._decision(packets[right_id][record_id])
            conflict_fields: list[str] = []
            for field in COMPARISON_FIELDS:
                left_value = left[field]
                right_value = right[field]
                metric_values[field][0].append(left_value)
                metric_values[field][1].append(right_value)
                if left_value != right_value:
                    conflict_fields.append(field)
            items.append(
                {
                    "record_id": record_id,
                    "issuer": base.get("issuer"),
                    "source_document": base["source_document"],
                    "pdf_page": base["pdf_page"],
                    "claim": base["claim"],
                    "conflict_fields": conflict_fields,
                    "agreed": not conflict_fields,
                    "adjudicated": record_id in adjudications,
                    "reviewer_values": {left_id: left, right_id: right},
                }
            )
        metrics = {
            field: {
                "agreement": round(
                    sum(left == right for left, right in zip(values[0], values[1], strict=True))
                    / len(values[0]),
                    4,
                ),
                "cohen_kappa": self._cohen_kappa(values[0], values[1]),
            }
            for field, values in metric_values.items()
        }
        conflicts = sum(not item["agreed"] for item in items)
        return {
            "reviewers": list(self.reviewers),
            "items": items,
            "metrics": metrics,
            "conflicts": conflicts,
            "adjudicated_conflicts": sum(item["adjudicated"] for item in items if not item["agreed"]),
            "total": len(items),
        }

    def save_adjudication(self, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        comparison = self.comparison()
        item = next((candidate for candidate in comparison["items"] if candidate["record_id"] == record_id), None)
        if item is None:
            raise HTTPException(404, "Unknown record")
        if item["agreed"]:
            raise HTTPException(409, "This record has no reviewer conflict")
        resolution = payload.get("resolution")
        if resolution not in {*self.reviewers, "custom"}:
            raise HTTPException(422, "resolution must select a reviewer or custom")
        note = str(payload.get("conflict_resolution") or "").strip()
        adjudicator_id = str(payload.get("adjudicator_id") or "").strip()
        if not note or not adjudicator_id:
            raise HTTPException(422, "adjudicator_id and conflict_resolution are required")
        final = payload.get("final")
        if resolution == "custom":
            if not isinstance(final, dict):
                raise HTTPException(422, "custom adjudication requires a final decision")
            labels = {field: final.get(field) for field in TARGET_LABEL_FIELDS}
            self._validate_labels(labels, allow_null=False)
            for field in ("claim_review", "claim", "numeric_facts_review", "numeric_facts", "materiality_basis"):
                if final.get(field) in (None, ""):
                    raise HTTPException(422, f"custom final decision requires {field}")
        adjudications = _read_json(self.adjudications_path, {})
        adjudications[record_id] = {
            "resolution": resolution,
            "final": final if resolution == "custom" else None,
            "adjudicator_id": adjudicator_id,
            "conflict_resolution": note,
            "adjudicated_at": _utc_now(),
        }
        _atomic_write_json(self.adjudications_path, adjudications)
        return adjudications[record_id]

    def export_gold(self) -> dict[str, Any]:
        comparison = self.comparison()
        adjudications = _read_json(self.adjudications_path, {})
        unresolved = [
            item["record_id"]
            for item in comparison["items"]
            if not item["agreed"] and item["record_id"] not in adjudications
        ]
        if unresolved:
            raise HTTPException(409, f"{len(unresolved)} reviewer conflicts still require adjudication")
        output = self.config.gold_output
        if output.exists():
            raise HTTPException(409, f"Gold output already exists: {output}")

        packets = {
            reviewer: {record["record_id"]: record for record in self._load_packet(reviewer)}
            for reviewer in self.reviewers
        }
        first_reviewer = self.reviewers[0]
        gold_records: list[dict[str, Any]] = []
        for item in comparison["items"]:
            record_id = item["record_id"]
            adjudication = adjudications.get(record_id)
            if adjudication and adjudication["resolution"] == "custom":
                decision = adjudication["final"]
                resolution_note = adjudication["conflict_resolution"]
            else:
                reviewer = adjudication["resolution"] if adjudication else first_reviewer
                decision = self._decision(packets[reviewer][record_id])
                resolution_note = (
                    adjudication["conflict_resolution"]
                    if adjudication
                    else "Independent reviewers agreed on all compared fields."
                )
            gold = deepcopy(self.base_records[record_id])
            gold["claim"] = decision["claim"]
            gold["numeric_facts"] = decision["numeric_facts"]
            for field in TARGET_LABEL_FIELDS:
                gold[field] = decision[field]
            gold["materiality_basis"] = decision["materiality_basis"]
            gold["follow_up_questions"] = decision.get("follow_up_questions", [])
            gold["annotation_status"] = "adjudicated"
            gold["review_status"] = "adjudicated"
            gold["reviewed_by"] = list(self.reviewers)
            gold["reviewed_at"] = _utc_now()
            gold["conflict_resolution"] = resolution_note
            gold["label_version"] = "0.3-gold"
            gold_records.append(gold)

        validator = Draft202012Validator(self.annotation_schema, format_checker=FormatChecker())
        validation_errors = [
            f"{record['record_id']}: {error.message}"
            for record in gold_records
            for error in validator.iter_errors(record)
        ]
        if validation_errors:
            raise HTTPException(422, f"Gold validation failed: {validation_errors[:5]}")

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
        try:
            _atomic_write_jsonl(temporary / "annotations.jsonl", gold_records)
            for name in ("pages.jsonl", "label_schema.json", "labeling_rules.md"):
                shutil.copy2(self.config.dataset_root / name, temporary / name)
            manifest = deepcopy(self.dataset_manifest)
            manifest.update(
                {
                    "dataset_version": "0.3-gold",
                    "status": "adjudicated",
                    "parent_dataset": str(self.config.dataset_root.resolve()),
                    "annotation_count": len(gold_records),
                    "reviewed_by": list(self.reviewers),
                    "generated_at_utc": _utc_now(),
                }
            )
            _atomic_write_json(temporary / "manifest.json", manifest)
            _atomic_write_json(
                temporary / "validation_report.json",
                {
                    "status": "passed",
                    "annotation_count": len(gold_records),
                    "schema_error_count": 0,
                    "reviewer_conflicts": comparison["conflicts"],
                    "adjudicated_conflicts": comparison["conflicts"],
                },
            )
            os.replace(temporary, output)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return {"output": str(output.resolve()), "record_count": len(gold_records)}


def create_app(config: ReviewAppConfig | None = None) -> Starlette:
    root = Path.cwd()
    config = config or ReviewAppConfig(
        review_root=root / "data/reviews/v0.2",
        dataset_root=root / "data/annotation_set_v0.2",
        gold_output=root / "data/annotation_set_v0.3-gold",
    )
    store = ReviewStore(config)
    web_root = Path(__file__).parent / "review_web"

    async def index(_: Request) -> Response:
        return HTMLResponse((web_root / "index.html").read_text(encoding="utf-8"))

    async def api_config(_: Request) -> Response:
        return JSONResponse(
            {
                "reviewers": list(store.reviewers),
                "enums": store.enums,
                "risk_flags": sorted(RISK_FLAG_VOCABULARY),
                "completion": store.completion(),
                "all_completed": store.all_completed(),
            }
        )

    async def records(request: Request) -> Response:
        return JSONResponse(store.list_records(request.path_params["reviewer"]))

    async def record(request: Request) -> Response:
        reviewer = request.path_params["reviewer"]
        record_id = request.path_params["record_id"]
        if request.method == "PUT":
            payload = await request.json()
            return JSONResponse(store.save_record(reviewer, record_id, payload))
        return JSONResponse(store.get_record(reviewer, record_id))

    async def complete(request: Request) -> Response:
        return JSONResponse(store.complete_reviewer(request.path_params["reviewer"]))

    async def unlock(request: Request) -> Response:
        store.unlock_reviewer(request.path_params["reviewer"])
        return JSONResponse({"status": "unlocked"})

    async def export_reviewer(request: Request) -> Response:
        reviewer = request.path_params["reviewer"]
        return FileResponse(
            store._packet_path(reviewer),
            media_type="application/x-ndjson",
            filename=f"{reviewer}.jsonl",
        )

    async def pdf(request: Request) -> Response:
        document = request.path_params["document"]
        path = store.source_paths.get(document)
        if path is None or not path.is_file():
            raise HTTPException(404, "Source PDF is unavailable")
        return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")

    async def comparison(_: Request) -> Response:
        return JSONResponse(store.comparison())

    async def adjudicate(request: Request) -> Response:
        return JSONResponse(
            store.save_adjudication(request.path_params["record_id"], await request.json())
        )

    async def export_gold(_: Request) -> Response:
        return JSONResponse(store.export_gold())

    async def http_error(_: Request, exc: Exception) -> Response:
        assert isinstance(exc, HTTPException)
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    app = Starlette(
        debug=False,
        routes=[
            Route("/", index),
            Route("/api/config", api_config),
            Route("/api/reviewers/{reviewer:str}/records", records),
            Route(
                "/api/reviewers/{reviewer:str}/records/{record_id:str}",
                record,
                methods=["GET", "PUT"],
            ),
            Route("/api/reviewers/{reviewer:str}/complete", complete, methods=["POST"]),
            Route("/api/reviewers/{reviewer:str}/unlock", unlock, methods=["POST"]),
            Route("/api/reviewers/{reviewer:str}/export", export_reviewer),
            Route("/api/pdfs/{document:str}", pdf),
            Route("/api/comparison", comparison),
            Route("/api/adjudications/{record_id:str}", adjudicate, methods=["PUT"]),
            Route("/api/gold/export", export_gold, methods=["POST"]),
            Mount("/assets", StaticFiles(directory=web_root), name="assets"),
        ],
        exception_handlers={HTTPException: http_error},
    )
    app.state.store = store
    app.state.pdf_url = lambda document, page: f"/api/pdfs/{quote(document)}#page={page}"
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", type=Path, default=Path("data/reviews/v0.2"))
    parser.add_argument("--dataset-root", type=Path, default=Path("data/annotation_set_v0.2"))
    parser.add_argument("--gold-output", type=Path, default=Path("data/annotation_set_v0.3-gold"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            ReviewAppConfig(
                review_root=args.review_root.resolve(),
                dataset_root=args.dataset_root.resolve(),
                gold_output=args.gold_output.resolve(),
            )
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
