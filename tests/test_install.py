import argparse
import json
import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from finjev import __version__
from finjev import install as installer


def options(key_file: Path, **changes) -> argparse.Namespace:
    values = dict(client="generic", key_file=str(key_file), model="jev-latest", source="local-wheel",
                  config=None, output=None, project_dir=str(key_file.parent), dry_run=False)
    values.update(changes)
    return argparse.Namespace(**values)


@pytest.fixture
def key_file(tmp_path):
    path = tmp_path / "apikey"
    path.write_text("test-only-not-a-real-key")
    return path


@pytest.fixture
def tool_runtime(tmp_path, monkeypatch):
    runtime = tmp_path / "tools"
    suffix = "Scripts/finjev-mcp.exe" if os.name == "nt" else "bin/finjev-mcp"
    executable = runtime / "finjev" / suffix
    executable.parent.mkdir(parents=True)
    executable.touch()
    calls = []

    def run(command):
        calls.append(command)
        return str(runtime) if command[1:] == ["tool", "dir"] else ""

    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(installer, "run_command", run)
    monkeypatch.setattr(installer, "check_server", AsyncMock(return_value={
        "server": {"name": "finjev", "version": __version__}, "model_call": "not_requested",
    }))
    return calls, executable


@pytest.mark.parametrize("vscode,section", [(False, "mcpServers"), (True, "servers")])
def test_merge_preserves_unrelated_config_and_private_backup(tmp_path, vscode, section):
    path = tmp_path / "mcp.json"
    original = {"theme": "dark", section: {"other": {"command": "keep-me", "env": {"KEY": "private"}}}}
    path.write_text(json.dumps(original))
    path.chmod(0o600)
    backup = installer.merge_json_config(path, {"command": "/absolute/finjev-mcp"}, vscode=vscode)
    assert json.loads(backup.read_text()) == original
    saved = json.loads(path.read_text())
    assert saved[section]["other"] == original[section]["other"]
    assert saved["theme"] == "dark"
    if os.name != "nt":
        assert stat.S_IMODE(backup.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert installer.merge_json_config(path, {"command": "/absolute/finjev-mcp"}, vscode=vscode) is None


@pytest.mark.parametrize("contents", ["{broken", "//comment\n{}", "[]", '{"mcpServers":[]}'])
def test_malformed_config_is_not_overwritten(tmp_path, contents):
    path = tmp_path / "mcp.json"
    path.write_text(contents)
    with pytest.raises(installer.InstallError):
        installer.merge_json_config(path, {"command": "finjev"})
    assert path.read_text() == contents
    assert list(tmp_path.glob("*.finjev-backup-*")) == []


def test_symlink_config_is_not_replaced(tmp_path):
    original = tmp_path / "target.json"
    original.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(original)
    with pytest.raises(installer.InstallError):
        installer.merge_json_config(link, {"command": "finjev"})
    assert link.is_symlink() and original.read_text() == "{}"


def test_dry_run_never_installs_or_reads_secret_contents(key_file, tool_runtime, tmp_path):
    calls, executable = tool_runtime
    output = tmp_path / "mcp.json"
    report = installer.install(options(key_file, dry_run=True, output=str(output)))
    assert report["dry_run"]
    assert "test-only-not-a-real-key" not in json.dumps(report)
    assert report["mcpServers"]["finjev"]["command"] == str(executable)
    assert not output.exists()
    assert calls == [["/bin/uv", "tool", "dir"]]


def test_generic_installs_then_checks_and_exports(key_file, tool_runtime):
    calls, executable = tool_runtime
    report = installer.install(options(key_file))
    entry = report["mcpServers"]["finjev"]
    assert entry["command"] == str(executable)
    assert entry["env"]["FINJEV_API_KEY_FILE"] == str(key_file)
    assert entry["env"]["TYPESAFE_API_KEY"] == ""
    assert "test-only-not-a-real-key" not in json.dumps(report)
    assert calls[1] == ["/bin/uv", "tool", "install", "--python", "3.12", "--reinstall-package", "finjev", "local-wheel"]


@pytest.mark.parametrize("client,section", [
    ("cursor", "mcpServers"), ("claude-code", "mcpServers"),
    ("claude-desktop", "mcpServers"), ("vscode", "servers"),
])
def test_client_config_shapes(client, section, key_file, tool_runtime, tmp_path):
    path = tmp_path / "config.json"
    report = installer.install(options(key_file, client=client, config=str(path)))
    assert report["installed"] is True
    entry = json.loads(path.read_text())[section]["finjev"]
    assert (entry.get("type") == "stdio") == (client in {"vscode", "claude-code"})
    assert report["check"]["model_call"] == "not_requested"


def test_failed_handshake_does_not_change_config(key_file, tool_runtime, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"mcpServers":{"other":{"command":"other"}}}')
    original = path.read_bytes()
    monkeypatch.setattr(installer, "check_server", AsyncMock(side_effect=RuntimeError("failed")))
    with pytest.raises(installer.InstallError, match="handshake"):
        installer.install(options(key_file, client="cursor", config=str(path)))
    assert path.read_bytes() == original


def test_mismatched_version_is_not_registered(key_file, tool_runtime, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setattr(installer, "check_server", AsyncMock(return_value={"server": {"version": "0.1.0"}}))
    with pytest.raises(installer.InstallError, match="version"):
        installer.install(options(key_file, client="cursor", config=str(path)))
    assert not path.exists()


def test_invalid_config_fails_before_install(key_file, tool_runtime, tmp_path):
    calls, _ = tool_runtime
    path = tmp_path / "config.json"
    path.write_text("broken")
    with pytest.raises(installer.InstallError):
        installer.install(options(key_file, client="cursor", config=str(path)))
    assert not calls


def test_missing_key_fails_before_install(tmp_path, tool_runtime):
    calls, _ = tool_runtime
    with pytest.raises(installer.InstallError, match="key-file"):
        installer.install(options(tmp_path / "nonexistent"))
    assert not calls


def test_codex_native_command_uses_argv_without_shell():
    entry = {"command": "/folder with spaces/finjev-mcp", "env": {"FINJEV_API_KEY_FILE": "/safe/apikey"}}
    assert installer.codex_add_command("/bin/codex", entry) == [
        "/bin/codex", "mcp", "add", "finjev", "--env", "FINJEV_API_KEY_FILE=/safe/apikey",
        "--", "/folder with spaces/finjev-mcp",
    ]


def test_codex_registration_backs_up_then_verifies(key_file, tool_runtime, tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('model = "keep-model"\n')
    calls, executable = tool_runtime
    original_runner = installer.run_command
    monkeypatch.setattr(installer, "config_path", lambda *_: path)

    def run(command):
        if command[0] == "/bin/codex":
            calls.append(command)
            # Model the native CLI's scoped TOML registration.
            entry_env = {pair.split("=", 1)[0]: pair.split("=", 1)[1]
                         for pair in command if pair.startswith(("FINJEV_", "TYPESAFE_"))}
            lines = ['model = "keep-model"', '[mcp_servers.finjev]',
                     f'command = {json.dumps(str(executable))}', '[mcp_servers.finjev.env]']
            lines += [f'{k} = {json.dumps(v)}' for k, v in entry_env.items()]
            path.write_text("\n".join(lines))
            return ""
        return original_runner(command)

    monkeypatch.setattr(installer, "run_command", run)
    report = installer.install(options(key_file, client="codex"))
    assert Path(report["backup_path"]).read_text() == 'model = "keep-model"\n'
    assert installer.read_config(path, toml=True)["model"] == "keep-model"


def test_client_default_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.Path, "home", lambda: tmp_path)
    assert installer.config_path("cursor", tmp_path) == tmp_path / ".cursor/mcp.json"
    assert installer.config_path("claude-code", tmp_path) == tmp_path / ".claude.json"
    assert installer.config_path("vscode", tmp_path) == tmp_path / ".vscode/mcp.json"
    assert installer.config_path("generic", tmp_path) is None
