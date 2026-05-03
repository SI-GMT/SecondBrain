"""Tests for memory_kit_mcp.sync — spec-drift manifest module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_kit_mcp.sync import (
    ManifestEntry,
    compute_current_hashes,
    compute_procedure_hash,
    load_manifest,
    main,
    save_manifest,
    update,
)


# ---------- compute_procedure_hash ----------


def test_hash_strips_frontmatter(tmp_path: Path) -> None:
    body = "# Procedure\n\nDo the thing carefully.\n"
    with_fm = tmp_path / "with_fm.md"
    with_fm.write_text(
        "---\nname: foo\ndescription: anything\n---\n" + body, encoding="utf-8"
    )
    no_fm = tmp_path / "no_fm.md"
    no_fm.write_text(body, encoding="utf-8")
    assert compute_procedure_hash(with_fm) == compute_procedure_hash(no_fm)


def test_hash_normalizes_line_endings(tmp_path: Path) -> None:
    body = "# Procedure\n\nLine one.\nLine two.\n"
    lf = tmp_path / "lf.md"
    lf.write_bytes(body.encode("utf-8"))
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    assert compute_procedure_hash(lf) == compute_procedure_hash(crlf)


def test_hash_changes_when_body_changes(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    a.write_text("# A\nfirst\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# A\nsecond\n", encoding="utf-8")
    assert compute_procedure_hash(a) != compute_procedure_hash(b)


def test_hash_handles_utf8_bom(tmp_path: Path) -> None:
    body = "# Procedure\n\nbody\n"
    plain = tmp_path / "plain.md"
    plain.write_bytes(body.encode("utf-8"))
    bom = tmp_path / "bom.md"
    bom.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert compute_procedure_hash(plain) == compute_procedure_hash(bom)


# ---------- load_manifest / save_manifest ----------


def test_load_manifest_returns_empty_when_absent(tmp_path: Path) -> None:
    assert load_manifest(tmp_path / "missing.json") == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sync.json"
    entries = {
        "mem_alpha": ManifestEntry(procedure="mem-alpha.md", last_synced_hash="aaa"),
        "mem_beta": ManifestEntry(procedure="mem-beta.md", last_synced_hash="bbb"),
    }
    save_manifest(entries, manifest_path)
    loaded = load_manifest(manifest_path)
    assert loaded == entries


def test_save_writes_documented_payload(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sync.json"
    save_manifest({"mem_x": ManifestEntry("mem-x.md", "deadbeef")}, manifest_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "_doc" in raw
    assert raw["tools"]["mem_x"] == {
        "procedure": "mem-x.md",
        "last_synced_hash": "deadbeef",
    }


# ---------- compute_current_hashes / update ----------


def _make_kit_stub(root: Path, procedures: dict[str, str]) -> Path:
    """Create a minimal SecondBrain repo skeleton with the given procedures."""
    proc_dir = root / "core" / "procedures"
    proc_dir.mkdir(parents=True, exist_ok=True)
    for name, body in procedures.items():
        (proc_dir / name).write_text(body, encoding="utf-8")
    return root


def test_compute_current_hashes_skips_missing_procedures(tmp_path: Path) -> None:
    kit = _make_kit_stub(
        tmp_path / "kit",
        {
            "mem-recall.md": "# recall\n",
            "mem-archive.md": "# archive\n",
        },
    )
    out = compute_current_hashes(kit)
    assert "mem_recall" in out
    assert "mem_archive" in out
    # Only those two of the 24 are present.
    assert len(out) == 2


def test_update_writes_manifest_and_warns_on_missing(tmp_path: Path) -> None:
    kit = _make_kit_stub(
        tmp_path / "kit", {"mem-recall.md": "# recall body\n"}
    )
    manifest_path = tmp_path / "sync.json"
    count, warnings = update(kit, manifest_path)
    assert count == 1
    assert any("mem_archive" in w for w in warnings)
    loaded = load_manifest(manifest_path)
    assert "mem_recall" in loaded
    assert loaded["mem_recall"].last_synced_hash == compute_procedure_hash(
        kit / "core" / "procedures" / "mem-recall.md"
    )


def test_update_raises_when_procedures_dir_absent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        update(tmp_path / "no-kit", tmp_path / "sync.json")


# ---------- CLI ----------


def test_cli_update_with_explicit_kit_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = _make_kit_stub(tmp_path / "kit", {"mem-recall.md": "# recall\n"})
    manifest = tmp_path / "out.json"
    rc = main(["update", "--kit-repo", str(kit), "--manifest", str(manifest)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Wrote 1 entries" in out
    assert manifest.exists()
