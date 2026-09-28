from __future__ import annotations

import json
import sys
import uuid
from typing import Any

from .core.models import JudgmentBatch


def create_request_id() -> str:
    return str(uuid.uuid4())


def redact(value: Any) -> Any:
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in key.lower() for part in ("password", "secret", "token"))
            else redact(child)
            for key, child in value.items()
        }
    return value


def emit_judgment_telemetry(batch: JudgmentBatch) -> None:
    record = {
        "event": "judgment.completed",
        "request_id": batch.request_id,
        "domain": batch.domain,
        "judgment": batch.judgment,
        "state_hash": batch.state_hash,
        "model": batch.model,
        "rubric_versions": batch.rubric_versions,
        "policy_versions": batch.policy_versions,
        "latency_ms": batch.latency_ms,
    }
    if batch.usage is not None:
        record["input_tokens"] = batch.usage.input_tokens
        record["output_tokens"] = batch.usage.output_tokens
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)
