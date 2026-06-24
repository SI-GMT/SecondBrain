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

# Tool-permission blocks live in their own fenced region, distinct from the
# server-declaration block above. Codex purges orphan ``[mcp_servers.X...]``
# sections on re-wire; the per-tool approval sub-tables sit inside this
# PERMS fence and must be protected from that purge (see
# ``inject_codex_mcp_server``). Mirrors deploy.ps1 / deploy.sh.
PERMS_START_MARKER = "# MEMORY-KIT-PERMS:START"
PERMS_END_MARKER = "# MEMORY-KIT-PERMS:END"

DEFAULT_SERVER_NAME = "secondbrain-memory-kit"
DEFAULT_COMMAND = "memory-kit-mcp"
LEGACY_SERVER_NAMES = ("memory-kit",)

# Canonical list of MCP tools exposed by the engine — kept in sync with
# deploy.ps1 ``Get-SecondbrainMcpToolNames`` / deploy.sh
# ``_secondbrain_mcp_tool_names``. Drives the per-tool auto-approve blocks.
SECONDBRAIN_MCP_TOOLS: tuple[str, ...] = (
    "mem", "mem_archeo", "mem_archeo_atlassian", "mem_archeo_context",
    "mem_archeo_context_finalize", "mem_archeo_git", "mem_archeo_index_files",
    "mem_archeo_plan", "mem_archeo_project_topology", "mem_archeo_stack",
    "mem_archive", "mem_archive_rewrite_paths", "mem_check_update",
    "mem_digest", "mem_doc", "mem_get_topology", "mem_goal",
    "mem_health_repair", "mem_health_scan", "mem_help", "mem_historize",
    "mem_init_project", "mem_list", "mem_merge", "mem_migrate", "mem_note",
    "mem_person", "mem_principle", "mem_promote_domain", "mem_read_archive",
    "mem_read_context", "mem_read_history", "mem_recall", "mem_reclass",
    "mem_relocate_project", "mem_rename", "mem_rollback_archive", "mem_search",
    "mem_update_phase", "mem_vault_migrate", "mem_worklog",
)


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
    # Preserve the MEMORY-KIT-PERMS block (auto-approve sub-tables) so the
    # orphan purge below — whose regex matches
    # ``[mcp_servers.<section>.tools.X]`` — neither eats it nor drops it on
    # reconstruction. Mirrors deploy.ps1 Add-McpServerToTomlConfig.
    perms_fenced = re.compile(
        re.escape(PERMS_START_MARKER) + r"[\s\S]*?" + re.escape(PERMS_END_MARKER)
    )
    perms_match = perms_fenced.search(existing)
    perms_block = perms_match.group(0) if perms_match else None
    without_fenced_search = without_fenced
    if perms_block:
        without_fenced_search = perms_fenced.sub("", without_fenced)
    orphan = re.compile(
        r"(?m)^[ \t]*\[mcp_servers\."
        + re.escape(section_name)
        + r"(\.[^\]\r\n]*)?\][\s\S]*?(?=(\r?\n[ \t]*\[)|\Z)"
    )
    cleaned = orphan.sub("", without_fenced_search).rstrip()
    had_orphan = cleaned != without_fenced_search.rstrip()

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
    if perms_block:
        merged += "\n" + perms_block + "\n"
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
# Per-tool auto-approve blocks — Codex + Mistral Vibe.
# ---------------------------------------------------------------------------
#
# Each CLI carries its OWN approval schema; the desktop must emit the exact
# one the CLI parses (a wrong schema is silently ignored, leaving prompts):
#
# * **Codex** — ``[mcp_servers.<server>.tools.<tool>]`` with
#   ``approval_mode = "auto"``.
# * **Mistral Vibe** — ``[tools.<server>_<tool>]`` with
#   ``permission = "always"``. The tool key is ``<server>_<tool>`` where the
#   server name is normalised (``[^A-Za-z0-9_-] -> _`` then strip ``_-``),
#   which PRESERVES the hyphens in ``secondbrain-memory-kit``. Vibe has no
#   ``[mcp.auto_approve]`` / ``[mcp.tools]`` table — those are ignored.
#
# Both share the fenced ``# MEMORY-KIT-PERMS`` region and the idempotent
# writer below. Mirrors deploy.ps1 / deploy.sh.


def _codex_perms_block(section_name: str, tools: tuple[str, ...]) -> str:
    lines = [PERMS_START_MARKER]
    for t in tools:
        lines.append(f"[mcp_servers.{section_name}.tools.{t}]")
        lines.append('approval_mode = "auto"')
        lines.append("")
    lines.append(PERMS_END_MARKER)
    return "\n".join(lines)


def _vibe_perms_block(server_name: str, tools: tuple[str, ...]) -> str:
    lines = [PERMS_START_MARKER]
    for t in tools:
        lines.append(f"[tools.{server_name}_{t}]")
        lines.append('permission = "always"')
        lines.append("")
    lines.append(PERMS_END_MARKER)
    return "\n".join(lines)


def _write_fenced_perms_block(
    config_path: Path, target_label: str, block: str
) -> InjectResult:
    """Idempotently write a ``# MEMORY-KIT-PERMS`` fenced block.

    Replaces the existing fenced region in place, recovers from an orphan
    START marker (END lost by an earlier cleanup), or appends a fresh block.
    """
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

    start = existing.find(PERMS_START_MARKER)
    if start >= 0:
        end_search = existing.find(PERMS_END_MARKER, start)
        if end_search < 0:
            # Orphan START (END lost by an earlier cleanup): drop the lone
            # START line, then append a clean block.
            cleaned = re.sub(
                r"(?m)^[ \t]*" + re.escape(PERMS_START_MARKER) + r"[ \t]*\r?\n?",
                "",
                existing,
            )
            if not cleaned.endswith("\n"):
                cleaned += "\n"
            merged = cleaned + "\n" + block + "\n"
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
                status=InjectStatus.UPDATED,
                detail="orphan START recovered",
            )
        end = end_search + len(PERMS_END_MARKER)
        new = existing[:start] + block + existing[end:]
        if new == existing:
            return InjectResult(
                target_label=target_label,
                config_path=config_path,
                status=InjectStatus.UNCHANGED,
            )
        try:
            _atomic_write_text(config_path, new)
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

    base = existing if existing.endswith("\n") else existing + "\n"
    merged = base + "\n" + block + "\n"
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


def inject_codex_tool_permissions(
    config_path: Path,
    *,
    target_label: str = "Codex",
    section_name: str = DEFAULT_SERVER_NAME,
    tools: tuple[str, ...] = SECONDBRAIN_MCP_TOOLS,
) -> InjectResult:
    """Auto-approve every MCP tool for Codex via per-tool sub-tables."""
    return _write_fenced_perms_block(
        config_path, target_label, _codex_perms_block(section_name, tools)
    )


def inject_vibe_tool_permissions(
    config_path: Path,
    *,
    target_label: str = "Mistral Vibe",
    server_name: str = DEFAULT_SERVER_NAME,
    tools: tuple[str, ...] = SECONDBRAIN_MCP_TOOLS,
) -> InjectResult:
    """Auto-approve every MCP tool for Vibe via ``[tools.X]`` permissions."""
    return _write_fenced_perms_block(
        config_path, target_label, _vibe_perms_block(server_name, tools)
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
