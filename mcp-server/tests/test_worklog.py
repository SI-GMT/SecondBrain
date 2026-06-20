"""Tests for mem_worklog."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

# Fixture archives:
#   alpha → 2026-04-30 (Thursday)
#   beta  → 2026-04-29 (Wednesday)
# Both fall in the ISO week Mon 2026-04-27 → Sun 2026-05-03.
_WEEK_OF = "2026-04-29"


async def test_worklog_resolves_monday_to_friday_window(client: Client) -> None:
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    d = res.data
    assert d.week_start == "2026-04-27"  # Monday
    assert d.week_end == "2026-05-01"  # Friday (weekend excluded by default)
    assert d.amplitude_hours == 7.0
    assert d.include_weekend is False


async def test_worklog_collects_across_all_projects(client: Client) -> None:
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    d = res.data
    assert d.sessions_total == 2
    assert set(d.projects) == {"alpha", "beta"}
    slugs = {s.slug for s in d.sessions}
    assert slugs == {"alpha", "beta"}


async def test_worklog_naive_proration_single_project_per_day(client: Client) -> None:
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    d = res.data
    # Each project is alone on its day → full amplitude that day.
    assert d.hours_by_project_total["alpha"] == 7.0
    assert d.hours_by_project_total["beta"] == 7.0


async def test_worklog_amplitude_override(client: Client) -> None:
    res = await client.call_tool(
        "mem_worklog", {"week_of": _WEEK_OF, "amplitude_hours": 8}
    )
    d = res.data
    assert d.amplitude_hours == 8.0
    assert d.hours_by_project_total["alpha"] == 8.0


async def test_worklog_days_span_full_week(client: Client) -> None:
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    days = res.data.days
    assert len(days) == 7  # Mon..Sun always present
    wed = next(x for x in days if x.date == "2026-04-29")
    assert wed.weekday == "Wed"
    assert wed.sessions == 1
    assert wed.projects == ["beta"]


async def test_worklog_weekend_flag_extends_window(client: Client) -> None:
    res = await client.call_tool(
        "mem_worklog", {"week_of": _WEEK_OF, "include_weekend": True}
    )
    assert res.data.week_end == "2026-05-03"  # Sunday
    assert res.data.include_weekend is True


async def test_worklog_summary_md_renders_table(client: Client) -> None:
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    md = res.data.summary_md
    assert "Worklog — semaine 2026-04-27" in md
    assert "| Jour |" in md
    assert "alpha" in md and "beta" in md


async def test_worklog_seeds_default_template_on_first_use(
    client: Client, vault_tmp
) -> None:
    # First call seeds the default format-only template.
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    assert res.data.template_seeded is True
    assert res.data.template_exists is True
    tpl = vault_tmp / "99-meta" / "worklog-template.md"
    assert tpl.exists()
    text = tpl.read_text(encoding="utf-8")
    assert "Worklog template" in text
    # Format-only: it must NOT carry a project→category referential.
    assert "Mapping projet" not in text
    # The four email blocks (no time stats) are the canonical structure.
    assert "LISTE DES TACHES" in text
    assert "FAITS MARQUANTS" in text
    assert "[project or perimeter]" in text
    # Second call is idempotent — does not re-seed.
    res2 = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    assert res2.data.template_seeded is False
    assert res2.data.template_exists is True


async def test_worklog_empty_week_returns_zero(client: Client) -> None:
    # A week with no archives → empty but well-formed.
    res = await client.call_tool("mem_worklog", {"week_of": "2025-01-06"})
    d = res.data
    assert d.sessions_total == 0
    assert d.projects == []
    assert d.hours_by_project_total == {}
    assert "(aucune session" in d.summary_md


async def test_worklog_invalid_date_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_worklog", {"week_of": "not-a-date"})


# ---------------------------------------------------------------------------
# persist phase
# ---------------------------------------------------------------------------

_PERSIST_ARGS = {
    "week_of": _WEEK_OF,
    "phase": "persist",
    "brief_md": "- alpha : avancé X\n- beta : avancé Y",
    "digest_md": "## Heures\nalpha 7h, beta 7h\n\nFAIT MARQUANT : X livré.",
    "detailed_md": "LISTE DES TACHES\n- [ALPHA] ...\n\nSEMAINE PROCHAINE\n- P0 finir X",
    "hours_by_project": {"alpha": 7.0, "beta": 7.0},
}


async def test_worklog_persist_creates_domain_and_archive(
    client: Client, vault_tmp
) -> None:
    res = await client.call_tool("mem_worklog", _PERSIST_ARGS)
    d = res.data
    assert d.persisted is True
    assert d.week_number == 18  # ISO week of 2026-04-27
    assert d.archive_path == "10-episodes/domains/worklogs/archives/2026-04-27-worklog-S18.md"
    archive = vault_tmp / d.archive_path
    assert archive.exists()
    text = archive.read_text(encoding="utf-8")
    assert "## Brief" in text
    assert "## Digest (courriel)" in text
    assert "## Détaillé (réunion)" in text
    assert "week_number: 18" in text
    # Domain skeleton created.
    assert (vault_tmp / "10-episodes/domains/worklogs/context.md").exists()
    assert (vault_tmp / "10-episodes/domains/worklogs/history.md").exists()


async def test_worklog_persist_idempotent_same_week(client: Client, vault_tmp) -> None:
    await client.call_tool("mem_worklog", _PERSIST_ARGS)
    res2 = await client.call_tool("mem_worklog", _PERSIST_ARGS)
    # Second run is an update, not a duplicate.
    assert "10-episodes/domains/worklogs/archives/2026-04-27-worklog-S18.md" in (
        res2.data.files_modified
    )
    history = (vault_tmp / "10-episodes/domains/worklogs/history.md").read_text(
        encoding="utf-8"
    )
    # History line appears exactly once.
    assert history.count("2026-04-27-worklog-S18.md") == 1


async def test_worklog_persist_requires_all_sections(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_worklog",
            {"week_of": _WEEK_OF, "phase": "persist", "brief_md": "x"},
        )


async def test_worklog_persisted_archive_excluded_from_collection(
    client: Client,
) -> None:
    # Persist a worklog, then collect the same week — the worklog archive must
    # NOT be counted as a session.
    await client.call_tool("mem_worklog", _PERSIST_ARGS)
    res = await client.call_tool("mem_worklog", {"week_of": _WEEK_OF})
    assert res.data.sessions_total == 2
    assert "worklogs" not in res.data.projects


async def test_worklog_unknown_phase_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_worklog", {"week_of": _WEEK_OF, "phase": "bogus"}
        )
