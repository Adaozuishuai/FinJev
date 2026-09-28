from pathlib import Path

import pytest

from finjev.core.gateway import resolve_api_key
from finjev.mcp_server import resolve_materiality_profile


def test_environment_key_takes_priority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key_file = tmp_path / "apikey"
    key_file.write_text("TYPESAFE_API_KEY=file-value", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "environment-value")
    monkeypatch.setenv("FINJEV_API_KEY_FILE", str(key_file))
    assert resolve_api_key() == "environment-value"


def test_key_file_accepts_assignment_without_exposing_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "apikey"
    key_file.write_text("TYPESAFE_API_KEY=file-value", encoding="utf-8")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("FINJEV_API_KEY_FILE", str(key_file))
    assert resolve_api_key() == "file-value"


def test_missing_credentials_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("FINJEV_API_KEY_FILE", raising=False)
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY or FINJEV_API_KEY_FILE"):
        resolve_api_key()


def test_mcp_defaults_to_materiality_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINJEV_MATERIALITY_PROFILE", raising=False)
    assert resolve_materiality_profile() == "v2"


def test_invalid_materiality_profile_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINJEV_MATERIALITY_PROFILE", "experimental")
    with pytest.raises(RuntimeError, match="must be 'v1' or 'v2'"):
        resolve_materiality_profile()
