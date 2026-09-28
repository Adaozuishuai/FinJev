"""Install a persistent FinJev MCP and safely register it with a selected client."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from . import __version__
from .doctor import check_server

DEFAULT_SOURCE = f"git+https://github.com/Adaozuishuai/FinJev.git@v{__version__}"
CLIENTS = ("codex", "claude-code", "claude-desktop", "cursor", "vscode", "generic")


class InstallError(RuntimeError):
    pass


def config_path(client: str, project_dir: Path) -> Path | None:
    user_dir = Path.home()
    if client == "codex":
        return Path(os.getenv("CODEX_HOME", str(user_dir / ".codex"))) / "config.toml"
    if client == "claude-code":
        return user_dir / ".claude.json"
    if client == "cursor":
        return user_dir / ".cursor" / "mcp.json"
    if client == "vscode":
        return project_dir / ".vscode" / "mcp.json"
    if client == "claude-desktop":
        if sys.platform == "darwin":
            return user_dir / "Library/Application Support/Claude/claude_desktop_config.json"
        if sys.platform == "win32" and os.getenv("APPDATA"):
            return Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json"
        raise InstallError("Claude Desktop default path is supported on macOS/Windows only; use --config.")
    return None


def read_config(path: Path, *, toml: bool = False) -> dict[str, Any]:
    if path.is_symlink():
        raise InstallError("Config is a symlink; use an explicit regular-file target instead.")
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text) if toml else json.loads(text)
    except (ValueError, OSError) as exc:
        raise InstallError("Cannot parse/read existing config. JSONC is not supported; no config changed.") from exc
    if not isinstance(data, dict):
        raise InstallError("Client config must be an object; no config changed.")
    return data


def backup_config(path: Path) -> Path | None:
    if not path.exists():
        return None
    # Backup can contain unrelated clients' secrets; never print its contents.
    with tempfile.NamedTemporaryFile(prefix=path.name + ".finjev-backup-", dir=path.parent, delete=False) as f:
        f.write(path.read_bytes())
        return Path(f.name)


def merge_json_config(path: Path, entry: dict, *, vscode: bool = False) -> Path | None:
    data = read_config(path)
    section = "servers" if vscode else "mcpServers"
    servers = data.setdefault(section, {})
    if not isinstance(servers, dict):
        raise InstallError(f"Existing {section} must be an object; no config changed.")
    if servers.get("finjev") == entry:
        return None
    servers["finjev"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_config(path)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temp_path = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    return backup


def codex_add_command(cli: str, entry: dict) -> list[str]:
    command = [cli, "mcp", "add", "finjev"]
    for key, value in entry["env"].items():
        command.extend(["--env", f"{key}={value}"])
    return [*command, "--", entry["command"]]


def run_command(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, timeout=300, check=False)
    if result.returncode:
        # Avoid echoing stderr: client tools can dump existing secret-bearing configs.
        raise InstallError(f"{Path(command[0]).name} failed (exit {result.returncode}); config registration not confirmed.")
    return result.stdout.strip()


def install(args: argparse.Namespace) -> dict:
    uv = shutil.which("uv")
    if not uv:
        raise InstallError("uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/")
    cli = shutil.which("codex") if args.client == "codex" else None
    if args.client == "codex" and not cli:
        raise InstallError("Codex CLI is required for --client codex; use --client generic to export config.")
    if args.client == "codex" and args.config:
        raise InstallError("--config is not supported for Codex; the native CLI uses its active config.")
    if args.client != "generic" and args.output:
        raise InstallError("--output is only supported with --client generic; use --config for JSON clients.")
    if args.client == "generic" and args.config:
        raise InstallError("Use --output, not --config, for generic config export.")
    key_file = Path(args.key_file).expanduser().resolve() if args.key_file else None
    if not key_file or not key_file.is_file():
        raise InstallError("Provide --key-file pointing to an existing Jev credential file (never paste the key).")
    if key_file.stat().st_size == 0:
        raise InstallError("Credential file is empty.")
    path = (
        Path(args.config).expanduser().absolute() if args.config else
        config_path(args.client, Path(args.project_dir).expanduser().resolve())
    )
    if args.client == "generic" and args.output:
        path = Path(args.output).expanduser().absolute()
    if path:
        existing = read_config(path, toml=args.client == "codex")
        section = "mcp_servers" if args.client == "codex" else ("servers" if args.client == "vscode" else "mcpServers")
        if section in existing and not isinstance(existing[section], dict):
            raise InstallError(f"Existing {section} must be an object; no config changed.")
    # Private tool-runtime path: no dependency on a GUI application's shell PATH.
    runtime_dir = Path(run_command([uv, "tool", "dir"])).resolve() / "finjev"
    executable = runtime_dir / ("Scripts/finjev-mcp.exe" if sys.platform == "win32" else "bin/finjev-mcp")
    entry: dict[str, Any] = {
        "command": str(executable), "args": [],
        "env": {
            "FINJEV_API_KEY_FILE": str(key_file),
            # Explicit empty override prevents stale inherited shell keys winning.
            "TYPESAFE_API_KEY": "",
            "FINJEV_MATERIALITY_PROFILE": "v2", "TYPESAFE_MODEL": args.model,
        },
    }
    if args.client in {"claude-code", "vscode"}:
        entry["type"] = "stdio"
    if args.dry_run:
        return {"dry_run": True, "client": args.client, "config_path": str(path) if path else None,
                "source": args.source, "mcpServers": {"finjev": entry}}
    run_command([uv, "tool", "install", "--python", "3.12", "--reinstall-package", "finjev", args.source])
    if not executable.is_file():
        raise InstallError("Installed executable not found; client configuration was not changed.")
    try:
        check = asyncio.run(check_server(str(executable), entry["env"]))
    except Exception as exc:
        raise InstallError("Installed server failed MCP handshake; client configuration was not changed.") from exc
    if check["server"]["version"] != __version__:
        raise InstallError("Installed version differs from installer version; client configuration was not changed.")
    backup = None
    if args.client == "codex":
        assert path is not None and cli is not None
        backup = backup_config(path)
        run_command(codex_add_command(cli, entry))
        saved = read_config(path, toml=True).get("mcp_servers", {}).get("finjev", {})
        if saved.get("command") != str(executable) or saved.get("env") != entry["env"]:
            raise InstallError("Codex CLI returned success but saved configuration did not match.")
    elif path:
        backup = merge_json_config(path, entry, vscode=args.client == "vscode")
    if args.client == "generic" and not path:
        return {"mcpServers": {"finjev": entry}}
    return {
        "installed": True, "client": args.client, "version": __version__,
        "config_path": str(path), "backup_path": str(backup) if backup else None,
        "check": check, "next": "Restart/reload your Agent and approve the MCP if requested.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=CLIENTS, required=True)
    parser.add_argument("--key-file", default=os.getenv("FINJEV_API_KEY_FILE"))
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Pinned Git source or a local matching-version wheel")
    parser.add_argument("--config", help="Explicit JSON config path; not supported for Codex")
    parser.add_argument("--output", help="Save generic mcpServers JSON instead of printing it")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Workspace root for VS Code")
    parser.add_argument("--dry-run", action="store_true", help="Show planned config; do not install or write")
    args = parser.parse_args()
    try:
        report = install(args)
    except (InstallError, OSError, subprocess.TimeoutExpired) as exc:
        message = str(exc) if isinstance(exc, InstallError) else "Filesystem/process error; installation not confirmed."
        print(message, file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
