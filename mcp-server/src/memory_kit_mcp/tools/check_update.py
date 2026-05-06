"""mem_check_update — Check if a newer SecondBrain release is available.

Spec: ``core/procedures/mem-check-update.md``.

Thin wrapper over the shared library ``memory_kit_mcp.update_check``. Lets
the LLM explicitly query update status (e.g. when the user asks "is the kit
up to date?"). The same library is also called passively at server startup
via ``server.main()`` to log a one-line stderr notification.

Read-only — never mutates the repo. Use ``deploy.ps1 -AutoUpdate`` (or
``deploy.sh --auto-update``) to actually pull and redeploy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.tools._models import UpdateCheckResult
from memory_kit_mcp.update_check import check_for_update


def _format_summary_md(
    current: str,
    latest: str | None,
    update_available: bool,
    last_checked_iso: str,
    error: str | None,
) -> str:
    lines = ["## Update check\n"]
    lines.append(f"- Current version: **v{current}**")
    if latest:
        lines.append(f"- Latest release: **v{latest}**")
    else:
        lines.append("- Latest release: **(unknown)**")
    lines.append(f"- Last checked: `{last_checked_iso}`")
    if error == "opt-out":
        lines.append("- Status: opt-out (`MEMORY_KIT_NO_UPDATE_CHECK=1`)")
    elif error:
        lines.append(f"- Status: check failed — `{error}`")
    elif update_available:
        lines.append("- Status: **update available**")
        lines.append("")
        lines.append(
            "Run `git pull && deploy.ps1 -RepairMcp` (or `deploy.sh --repair-mcp`) "
            "to upgrade. Or use `deploy.ps1 -AutoUpdate` / `deploy.sh --auto-update` "
            "for the combined fetch + pull + redeploy."
        )
    else:
        lines.append("- Status: up to date")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_check_update(
        force_refresh: bool = Field(
            False,
            description="Bypass the 24h cache and re-hit the GitHub API now.",
        ),
    ) -> UpdateCheckResult:
        """Check if a newer SecondBrain release is available on GitHub.

        Compares the running ``memory-kit-mcp`` version against the latest
        release tag of ``SI-GMT/SecondBrain``. Cached for 24h by default;
        pass ``force_refresh=True`` to bypass the cache.

        Read-only — does not mutate the repo or trigger an upgrade. Use
        ``deploy.ps1 -AutoUpdate`` (or ``deploy.sh --auto-update``) to do
        the fetch + pull + redeploy.

        Honors ``MEMORY_KIT_NO_UPDATE_CHECK=1`` env var (returns
        ``error="opt-out"`` and never hits the network).
        """
        info = check_for_update(force_refresh=force_refresh)
        last_checked_iso = (
            datetime.fromtimestamp(info.last_checked, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        return UpdateCheckResult(
            current_version=info.current_version,
            latest_version=info.latest_version,
            update_available=info.update_available,
            last_checked=info.last_checked,
            error=info.error,
            summary_md=_format_summary_md(
                info.current_version,
                info.latest_version,
                info.update_available,
                last_checked_iso,
                info.error,
            ),
        )
