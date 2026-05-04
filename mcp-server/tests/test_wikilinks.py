"""Tests for memory_kit_mcp.vault.wikilinks — shared parsing + resolution."""

from __future__ import annotations

from pathlib import Path

from memory_kit_mcp.vault.wikilinks import (
    WIKILINK_RE,
    build_vault_index,
    find_dangling,
    find_wikilinks,
    resolve_wikilink,
    strip_code,
)


# ---------- regex ----------


def test_wikilink_regex_matches_plain() -> None:
    assert WIKILINK_RE.findall("see [[alpha]] and [[beta-gamma]]") == [
        "alpha", "beta-gamma",
    ]


def test_wikilink_regex_matches_with_alias() -> None:
    assert WIKILINK_RE.findall("see [[alpha|Alpha]]") == ["alpha"]


def test_wikilink_regex_skips_embeds() -> None:
    """Obsidian uses ![[X]] for image embeds — not a graph reference."""
    assert WIKILINK_RE.findall("![[image.png]] vs [[real-link]]") == ["real-link"]


# ---------- strip_code ----------


def test_strip_code_removes_fenced_blocks() -> None:
    body = "before\n```\n[[inside-fence]]\n```\nafter [[outside]]"
    out = strip_code(body)
    assert "[[inside-fence]]" not in out
    assert "[[outside]]" in out


def test_strip_code_removes_inline_spans() -> None:
    body = "doctrine: `[[example]]` and real [[reference]]"
    out = strip_code(body)
    assert "[[example]]" not in out
    assert "[[reference]]" in out


def test_find_wikilinks_filters_code() -> None:
    body = "real [[alpha]] then `[[fake]]` then\n```\n[[also-fake]]\n```\nand [[beta]]"
    assert find_wikilinks(body) == ["alpha", "beta"]


# ---------- vault index + resolution ----------


def test_build_vault_index_basenames_and_relpaths(tmp_path: Path) -> None:
    (tmp_path / "10-episodes" / "projects" / "alpha").mkdir(parents=True)
    (tmp_path / "10-episodes" / "projects" / "alpha" / "context.md").write_text("x")
    (tmp_path / "20-knowledge").mkdir()
    (tmp_path / "20-knowledge" / "concept.md").write_text("y")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "config.md").write_text("ignored")

    basenames, relpaths = build_vault_index(tmp_path)
    assert "context" in basenames
    assert "concept" in basenames
    # .obsidian excluded
    assert "config" not in basenames
    assert "10-episodes/projects/alpha/context" in relpaths


def test_resolve_by_basename(tmp_path: Path) -> None:
    (tmp_path / "20-knowledge").mkdir()
    (tmp_path / "20-knowledge" / "alpha.md").write_text("x")
    basenames, relpaths = build_vault_index(tmp_path)
    assert resolve_wikilink("alpha", basenames, relpaths) is True
    assert resolve_wikilink("nope", basenames, relpaths) is False


def test_resolve_by_full_relpath(tmp_path: Path) -> None:
    (tmp_path / "10-episodes").mkdir()
    (tmp_path / "10-episodes" / "alpha.md").write_text("x")
    basenames, relpaths = build_vault_index(tmp_path)
    assert resolve_wikilink("10-episodes/alpha", basenames, relpaths) is True
    assert resolve_wikilink("10-episodes/alpha.md", basenames, relpaths) is True


def test_resolve_index_always_true(tmp_path: Path) -> None:
    basenames, relpaths = build_vault_index(tmp_path)
    assert resolve_wikilink("index", basenames, relpaths) is True


# ---------- find_dangling ----------


def test_find_dangling_returns_unresolved_in_order(tmp_path: Path) -> None:
    (tmp_path / "20-knowledge").mkdir()
    (tmp_path / "20-knowledge" / "alpha.md").write_text("x")
    body = "Mention [[alpha]] (resolves), [[ghost-1]], [[ghost-2]], and [[alpha]] again."
    assert find_dangling(body, tmp_path) == ["ghost-1", "ghost-2"]


def test_find_dangling_skips_code(tmp_path: Path) -> None:
    body = "Real [[ghost]]; example `[[also-ghost]]`; fenced:\n```\n[[fenced-ghost]]\n```"
    assert find_dangling(body, tmp_path) == ["ghost"]


def test_find_dangling_returns_empty_when_clean(tmp_path: Path) -> None:
    (tmp_path / "20-knowledge").mkdir()
    (tmp_path / "20-knowledge" / "alpha.md").write_text("x")
    body = "Only [[alpha]] is mentioned."
    assert find_dangling(body, tmp_path) == []


def test_find_dangling_respects_exempt_set(tmp_path: Path) -> None:
    body = "Mention [[future-target]] which is intentional."
    assert find_dangling(body, tmp_path) == ["future-target"]
    assert find_dangling(body, tmp_path, exempt={"future-target"}) == []


def test_find_dangling_handles_no_wikilinks(tmp_path: Path) -> None:
    assert find_dangling("plain text with no links", tmp_path) == []
