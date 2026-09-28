from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel


def _canonicalize(value: Any, path: str = "$state") -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json", exclude_none=True), path)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"State contains a non-finite number at {path}")
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(child, f"{path}.{key}")
            for key, child in sorted(value.items(), key=lambda pair: str(pair[0]))
            if child is not None
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonicalize(child, f"{path}[{index}]") for index, child in enumerate(value)]
    raise TypeError(f"State contains unsupported value at {path}: {type(value).__name__}")


def build_state(value: Any) -> Any:
    return _canonicalize(value)


def stable_json(value: Any) -> str:
    return json.dumps(build_state(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_state(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()
