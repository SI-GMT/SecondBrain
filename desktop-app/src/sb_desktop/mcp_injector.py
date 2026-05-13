"""Per-CLI MCP server config injection — pure Python.

Port of ``deploy.ps1``'s ``Add-McpServerToJsonConfig`` /
``Add-McpServerToTomlConfig`` / ``Add-McpServerToVibeTomlConfig``
functions. Same semantics, same idempotence guarantees, but no
PowerShell required — runs in-process from the desktop app's
first-run wizard.

Three file formats handled, matching the three patterns the kit
already supports:

* **JSON `mcpServers.{name}`** — Claude Code, Claude Desktop, Copilot
  CLI, Gemini CLI. Edits ``config.json``-style files by adding a
  ``mcpServers`` key if absent, then a ``{name}`` entry pointing at
  ``command``. Legacy entry names (e.g. ``memory-kit`` before the
  rename to ``secondbrain-memory-kit``) are pruned on the way.
* **TOML `[mcp_servers.{name}]`** — Codex. Uses fenced markers
  ``# MEMORY-KIT:START`` / ``END`` to delimit the block we own, so
  re-runs update in place. Also purges orphan ``[mcp_servers.{name}]``
  sections from earlier non-fenced installs that would otherwise
  trigger a TOML parse error.
* **TOML `[[mcp_servers]]`** — Mistral Vibe (table-of-arrays style).
  Same fenced-marker idempotence.

All writes are UTF-8 without BOM and LF line endings — the convention
the kit enforces across the vault.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

START_MARKER = "# MEMORY-KIT:START"
END_MARKER = "# MEMORY-KIT:END"

DEFAULT_SERVER_NAME = "secondbrain-memory-kit"
DEFAULT_COMMAND = "memory-kit-mcp"
LEGACY_SERVER_NAMES = ("memory-kit",)


class InjectStatus(str, Enum):
    """Outcome flag returned by every injector."""

    CREATED = "created"   # config file did not exist, we created it
    ADDED = "added"       # config existed, our entry did not — added
    UPDATED = "updated"   # entry existed but command differed — updated
    UNCHANGED = "unchanged"  # entry already correct
    SKIPPED = "skipped"   # config unreadable or write failed
    PURGED_ORPHAN = "purged-orphan"  # cleaned up duplicate non-fenced section


@dataclass(frozen=True, slots=True)
class InjectResult:
    target_label: str
    config_path: Path
    status: InjectStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != InjectStatus.SKIPPED


def _atomic_write_text(path: Path, content: str) -> None:
    """Write UTF-8 LF, atomic via tmp file rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _toml_quote(value: str) -> str:
    """Render ``value`` as a TOML string safe for arbitrary paths.

    Windows absolute paths contain backslashes that TOML's basic
    strings (``"..."``) treat as escape characters; embedding
    ``C:\\Program Files\\…`` verbatim produces an invalid TOML file
    that Codex / Vibe refuse to parse. TOML literal strings (single
    quotes) preserve backslashes byte-for-byte — exactly what we want.
    A path that happens to carry a literal single quote falls back to
    a basic string with both quote and backslash escaped.
    """
    if "'" not in value:
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# JSON-style config: Claude Code, Claude Desktop, Copilot CLI, Gemini CLI.
# ---------------------------------------------------------------------------


def inject_json_mcp_server(
    config_path: Path,
    *,
    target_label: str,
    server_name: str = DEFAULT_SERVER_NAME,
    command: str = DEFAULT_COMMAND,
    legacy_names: tuple[str, ...] = LEGACY_SERVER_NAMES,
    extra_entry_fields: dict | None = None,
) -> InjectResult:
    """Add / update ``mcpServers.{server_name}`` in a JSON config file.

    ``extra_entry_fields`` is merged into the per-server entry alongside
    ``command`` + ``args``. Required by GitHub Copilot CLI which only
    activates servers carrying ``"type": "local"`` and a ``"tools"``
    allow-list — without those fields the entry parses but never
    surfaces in ``copilot mcp list``.
    """
    created = False
    existing: dict = {}
    if config_path.is_file():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as exc:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.SKIPPED,
                detail=f"unreadable: {exc}",
            )
    else:
        created = True

    if not isinstance(existing, dict):
        existing = {}

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        existing["mcpServers"] = servers

    purged_legacy: list[str] = []
    for legacy in legacy_names:
        if legacy != server_name and legacy in servers:
            servers.pop(legacy)
            purged_legacy.append(legacy)

    new_entry: dict = {"command": command, "args": []}
    if extra_entry_fields:
        for k, v in extra_entry_fields.items():
            new_entry[k] = v

    current = servers.get(server_name)
    if (
        isinstance(current, dict)
        and current.get("command") == command
        and all(
            current.get(k) == v for k, v in (extra_entry_fields or {}).items()
        )
    ):
        if purged_legacy:
            try:
                _atomic_write_text(
                    config_path,
                    json.dumps(existing, indent=2, ensure_ascii=False),
                )
            except OSError as exc:
                return InjectResult(
                    target_label=target_label,
                    config_path=config_path,
                    status=InjectStatus.SKIPPED,
                    detail=f"write failed: {exc}",
                )
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.UNCHANGED,
                detail=f"already present; pruned legacy: {','.join(purged_legacy)}",
            )
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.UNCHANGED,
            detail="already present",
        )

    status = InjectStatus.UPDATED if server_name in servers else InjectStatus.ADDED
    if created:
        status = InjectStatus.CREATED
    servers[server_name] = new_entry

    try:
        _atomic_write_text(
            config_path,
            json.dumps(existing, indent=2, ensure_ascii=False),
        )
    except OSError as exc:
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.SKIPPED,
            detail=f"write failed: {exc}",
        )

    detail = ""
    if purged_legacy:
        detail = f"pruned legacy: {','.join(purged_legacy)}"
    return InjectResult(
        target_label=target_label,
        config_path=config_path,
        status=status,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# TOML-style ``[mcp_servers.{section}]`` config: Codex.
# ---------------------------------------------------------------------------


def inject_codex_mcp_server(
    config_path: Path,
    *,
    target_label: str = "Codex",
    section_name: str = DEFAULT_SERVER_NAME,
    command: str = DEFAULT_COMMAND,
) -> InjectResult:
    """Add / update a Codex ``[mcp_servers.{section_name}]`` block."""
    block = (
        f"{START_MARKER}\n"
        f"[mcp_servers.{section_name}]\n"
        f"command = {_toml_quote(command)}\n"
        f"args = []\n"
        f"{END_MARKER}"
    )

    if not config_path.is_file():
        try:
            _atomic_write_text(config_path, block + "\n")
        except OSError as exc:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.SKIPPED,
                detail=f"write failed: {exc}",
            )
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.CREATED,
        )

    try:
        existing = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.SKIPPED,
            detail=f"unreadable: {exc}",
        )

    fenced = re.compile(
        re.escape(START_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER)
    )
    without_fenced = fenced.sub("", existing)
    orphan = re.compile(
        r"(?m)^[ \t]*\[mcp_servers\."
        + re.escape(section_name)
        + r"(\.[^\]\r\n]*)?\][\s\S]*?(?=(\r?\n[ \t]*\[)|\Z)"
    )
    cleaned = orphan.sub("", without_fenced).rstrip()
    had_orphan = cleaned != without_fenced.rstrip()

    if fenced.search(existing) and not had_orphan:
        replaced = fenced.sub(block, existing)
        if replaced == existing:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.UNCHANGED,
            )
        try:
            _atomic_write_text(config_path, replaced)
        except OSError as exc:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.SKIPPED,
                detail=f"write failed: {exc}",
            )
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.UPDATED,
        )

    sep = "\n\n" if cleaned else ""
    merged = cleaned + sep + block + "\n"
    try:
        _atomic_write_text(config_path, merged)
    except OSError as exc:
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.SKIPPED,
            detail=f"write failed: {exc}",
        )
    return InjectResult(
        target_label=target_label,
        config_path=config_path,
        status=(
            InjectStatus.PURGED_ORPHAN if had_orphan else InjectStatus.ADDED
        ),
    )


# ---------------------------------------------------------------------------
# TOML-style ``[[mcp_servers]]`` array-of-tables: Mistral Vibe.
# ---------------------------------------------------------------------------


def inject_vibe_mcp_server(
    config_path: Path,
    *,
    target_label: str = "Mistral Vibe",
    server_name: str = DEFAULT_SERVER_NAME,
    command: str = DEFAULT_COMMAND,
) -> InjectResult:
    """Add / update a Vibe ``[[mcp_servers]]`` array entry."""
    block = (
        f"{START_MARKER}\n"
        f"[[mcp_servers]]\n"
        f'name = "{server_name}"\n'
        f'transport = "stdio"\n'
        f"command = {_toml_quote(command)}\n"
        f"args = []\n"
        f"{END_MARKER}"
    )

    if not config_path.is_file():
        try:
            _atomic_write_text(config_path, block + "\n")
        except OSError as exc:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.SKIPPED,
                detail=f"write failed: {exc}",
            )
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.CREATED,
        )

    try:
        existing = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.SKIPPED,
            detail=f"unreadable: {exc}",
        )

    fenced = re.compile(
        re.escape(START_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER)
    )

    if fenced.search(existing):
        replaced = fenced.sub(block, existing)
        if replaced == existing:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.UNCHANGED,
            )
        try:
            _atomic_write_text(config_path, replaced)
        except OSError as exc:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.SKIPPED,
                detail=f"write failed: {exc}",
            )
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.UPDATED,
        )

    sep = "\n\n" if existing.rstrip() else ""
    merged = existing.rstrip() + sep + block + "\n"
    try:
        _atomic_write_text(config_path, merged)
    except OSError as exc:
        return InjectResult(
            target_label=target_label,
            config_path=config_path,
            status=InjectStatus.SKIPPED,
            detail=f"write failed: {exc}",
        )
    return InjectResult(
        target_label=target_label,
        config_path=config_path,
        status=InjectStatus.ADDED,
    )


# ---------------------------------------------------------------------------
# Kit config (~/.memory-kit/config.json) — the canonical engine config.
# ---------------------------------------------------------------------------


def write_kit_config(
    vault: Path,
    kit_repo: Path | None,
    language: str,
    *,
    config_path: Path | None = None,
    extras: dict | None = None,
) -> Path:
    """Write ``~/.memory-kit/config.json`` with the resolved values."""
    target = config_path or (Path.home() / ".memory-kit" / "config.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "vault": str(vault),
        "language": language,
    }
    if kit_repo is not None:
        payload["kit_repo"] = str(kit_repo)
    if extras:
        for k, v in extras.items():
            payload.setdefault(k, v)
    _atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=False))
    return target
