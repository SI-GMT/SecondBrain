"""Tests for vault primitives — atomic_io, frontmatter, scanner, paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_kit_mcp.vault import atomic_io, frontmatter, paths, scanner


# ---------- atomic_io ----------


def test_write_atomic_creates_file_with_lf_and_no_bom(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "file.md"
    atomic_io.write_atomic(target, "line1\r\nline2\r\nline3\n")
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM must not be written"
    assert b"\r" not in raw, "CRLF must be normalized to LF"
    assert raw == b"line1\nline2\nline3\n"


def test_write_atomic_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "f.md"
    atomic_io.write_atomic(target, "first")
    atomic_io.write_atomic(target, "second")
    assert target.read_text(encoding="utf-8") == "second"


def test_hash_content_and_file_match(tmp_path: Path) -> None:
    target = tmp_path / "h.md"
    content = "hello\nworld\n"
    atomic_io.write_atomic(target, content)
    assert atomic_io.hash_content(content) == atomic_io.hash_file(target)


def test_hash_file_returns_none_when_missing(tmp_path: Path) -> None:
    assert atomic_io.hash_file(tmp_path / "nope.md") is None


def test_write_with_hash_check_succeeds_when_match(tmp_path: Path) -> None:
    target = tmp_path / "f.md"
    atomic_io.write_atomic(target, "v1")
    h = atomic_io.hash_file(target)
    atomic_io.write_with_hash_check(target, "v2", expected_hash=h)
    assert target.read_text(encoding="utf-8") == "v2"


def test_write_with_hash_check_raises_on_concurrent_modification(tmp_path: Path) -> None:
    target = tmp_path / "f.md"
    atomic_io.write_atomic(target, "v1")
    with pytest.raises(atomic_io.ConcurrentModificationError):
        atomic_io.write_with_hash_check(target, "v2", expected_hash="wrong-hash")


def test_write_with_hash_check_create_only(tmp_path: Path) -> None:
    target = tmp_path / "new.md"
    atomic_io.write_with_hash_check(target, "fresh", expected_hash=None)
    assert target.read_text(encoding="utf-8") == "fresh"


# ---------- frontmatter ----------


def test_frontmatter_parse_roundtrip() -> None:
    src = "---\nname: foo\nphase: in-progress\n---\n\nbody here\n"
    fm, body = frontmatter.parse(src)
    assert fm == {"name": "foo", "phase": "in-progress"}
    assert body.strip() == "body here"


def test_frontmatter_parse_no_block_returns_empty_dict() -> None:
    fm, body = frontmatter.parse("just body, no frontmatter")
    assert fm == {}
    assert body == "just body, no frontmatter"


def test_frontmatter_parse_invalid_yaml_raises() -> None:
    with pytest.raises(ValueError):
        frontmatter.parse("---\n: invalid: yaml:\n  - bad\n :\n---\nbody")


def test_frontmatter_serialize_emits_block_style() -> None:
    out = frontmatter.serialize({"name": "foo", "tags": ["a", "b"]}, "body")
    assert out.startswith("---\n")
    assert "name: foo\n" in out
    assert "tags:\n- a\n- b\n" in out
    assert out.rstrip().endswith("body")


def test_frontmatter_write_uses_atomic_io(tmp_path: Path) -> None:
    target = tmp_path / "x.md"
    frontmatter.write(target, {"slug": "x"}, "body line\n")
    parsed_fm, parsed_body = frontmatter.read(target)
    assert parsed_fm == {"slug": "x"}
    assert parsed_body.strip() == "body line"


# ---------- paths ----------


def test_resolve_slug_finds_active_project(vault_tmp: Path) -> None:
    folder, kind, archived = paths.resolve_slug(vault_tmp, "alpha")
    assert folder.name == "alpha"
    assert kind == "project"
    assert archived is False


def test_resolve_slug_finds_archived_project(vault_tmp: Path) -> None:
    folder, kind, archived = paths.resolve_slug(vault_tmp, "legacy-app")
    assert folder.name == "legacy-app"
    assert kind == "project"
    assert archived is True


def test_resolve_slug_finds_domain(vault_tmp: Path) -> None:
    folder, kind, archived = paths.resolve_slug(vault_tmp, "shared-infra")
    assert kind == "domain"
    assert archived is False


def test_resolve_slug_returns_none_for_unknown(vault_tmp: Path) -> None:
    assert paths.resolve_slug(vault_tmp, "nothing") is None


def test_list_helpers_match_fixture(vault_tmp: Path) -> None:
    assert paths.list_projects(vault_tmp) == ["alpha", "beta"]
    assert paths.list_domains(vault_tmp) == ["shared-infra"]
    assert paths.list_archived(vault_tmp) == ["legacy-app"]


# ---------- scanner ----------


def test_scan_projects_loads_metadata(vault_tmp: Path) -> None:
    summaries = scanner.scan_projects(vault_tmp)
    by_slug = {s.slug: s for s in summaries}
    assert set(by_slug) == {"alpha", "beta"}
    assert by_slug["alpha"].phase == "in-progress (demo fixture)"
    assert by_slug["alpha"].last_session == "2026-04-30"
    assert by_slug["alpha"].scope == "work"
    assert by_slug["alpha"].archives_count == 1
    # beta has no context.md → metadata empty but archives_count counts the one archive
    assert by_slug["beta"].phase is None
    assert by_slug["beta"].archives_count == 1


def test_scan_archived(vault_tmp: Path) -> None:
    archived = scanner.scan_archived(vault_tmp)
    assert len(archived) == 1
    assert archived[0].slug == "legacy-app"
    assert archived[0].archived is True
    assert archived[0].archived_at == "2026-01-15"


def test_scan_domains(vault_tmp: Path) -> None:
    domains = scanner.scan_domains(vault_tmp)
    assert [d.slug for d in domains] == ["shared-infra"]
    assert domains[0].kind == "domain"
