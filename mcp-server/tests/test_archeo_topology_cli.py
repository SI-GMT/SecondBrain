"""Tests for the ``archeo-topology`` CLI entry point (memory_kit_mcp.archeo_topology).

Distinct from ``test_archeo_topology.py``, which exercises the underlying
``archeo.topology.enumerate_files`` library. Here we drive ``main(argv)``
directly (no subprocess) over a plain raw repo so the run needs no git.
"""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from memory_kit_mcp import archeo_topology


@pytest.fixture
def raw_repo(tmp_path: Path) -> Path:
    """Plain directory tree (no .git/) — raw mode enumerates it deterministically."""
    repo = tmp_path / "raw_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    (repo / "src" / "beta.py").write_text("print('beta')\n", encoding="utf-8")
    (repo / "README.md").write_text("# raw\n", encoding="utf-8")
    return repo


def test_main_md_to_stdout(raw_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = archeo_topology.main(["--repo", str(raw_repo), "--mode", "raw"])
    assert rc == 0
    out = capsys.readouterr().out
    # Atom frontmatter + inventory headers.
    assert out.startswith("---")
    assert "source: archeo-topology" in out
    assert f"project: {raw_repo.name}" in out
    assert "# raw_repo — repo topology" in out
    assert "## Inventory" in out
    # Enumerated files appear in the inventory block.
    assert "alpha.py" in out
    assert "README.md" in out


def test_main_json_to_out_file(raw_repo: Path, tmp_path: Path) -> None:
    out_file = tmp_path / "nested" / "topology.json"
    rc = archeo_topology.main(
        [
            "--repo",
            str(raw_repo),
            "--mode",
            "raw",
            "--project",
            "myproj",
            "--format",
            "json",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    assert out_file.is_file()  # parent dirs created
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["project"] == "myproj"
    assert data["source_mode"] == "raw"
    assert data["files_count"] == 3
    assert any(f.endswith("alpha.py") for f in data["files"])


def test_main_missing_repo_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    rc = archeo_topology.main(["--repo", str(missing), "--mode", "raw"])
    assert rc == 2
    assert "error:" in capsys.readouterr().err
