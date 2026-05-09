"""Tests for memory_kit_mcp.archeo.file_summary.

Verifies per-language regex extractors capture the structural signals the
archive body uses to pre-fill Analyse technique. Extraction is mechanical
(regex-based), so tests assert exact captures on synthetic content.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from memory_kit_mcp.archeo.file_summary import (
    FileSummary,
    extract_file_summary,
    render_technical_section,
    summarize_files,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    )


@pytest.fixture
def cls_repo(tmp_path: Path) -> tuple[Path, str]:
    """Repo with one IRIS .cls file committed."""
    repo = tmp_path / "cls_repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    target = repo / "src" / "EcoSAV" / "Statut.cls"
    target.parent.mkdir(parents=True)
    target.write_text(
        "/// Statut DOSSIERDON pour EcoSAV.\n"
        "/// Géré par le processus de validation.\n"
        "Class src.EcoSAV.Statut Extends %Persistent\n"
        "{\n"
        "Property DOSSIERDON As %Boolean [InitialExpression = 0];\n"
        "Property Code As %String;\n"
        "ClassMethod ValidateDossier(pId As %Integer) As %Status\n"
        "{\n"
        "    Quit $$$OK\n"
        "}\n"
        "Method GetCode() As %String\n"
        "{\n"
        "    Quit ..Code\n"
        "}\n"
        "}\n",
        encoding="utf-8",
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "feat: Statut.cls"], repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    return repo, sha


def test_cls_extractor_captures_class_properties_methods(
    cls_repo: tuple[Path, str],
) -> None:
    repo, sha = cls_repo
    s = extract_file_summary(repo, sha, "src/EcoSAV/Statut.cls")
    assert s.language == "cls"
    assert s.error == ""
    assert any("Statut" in c and "Persistent" in c for c in s.classes)
    assert "DOSSIERDON : %Boolean" in s.properties
    assert "Code : %String" in s.properties
    assert "ValidateDossier" in s.methods
    assert "GetCode" in s.methods
    assert "DOSSIERDON" in s.top_doc


def test_py_extractor_captures_classes_and_defs(tmp_path: Path) -> None:
    repo = tmp_path / "py_repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "t@e.com"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "module.py").write_text(
        '"""Top docstring describing this module.\n'
        'Second line.\n"""\n'
        "import os\n\n"
        "class Foo:\n"
        "    def method_a(self): pass\n\n"
        "class Bar(Foo):\n"
        "    pass\n\n"
        "def helper(x):\n"
        "    return x * 2\n",
        encoding="utf-8",
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()

    s = extract_file_summary(repo, sha, "module.py")
    assert s.language == "py"
    assert "Foo" in s.classes
    assert "Bar" in s.classes
    assert "helper" in s.methods
    assert "Top docstring" in s.top_doc


def test_sql_extractor_captures_ddl(tmp_path: Path) -> None:
    repo = tmp_path / "sql_repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "t@e.com"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "schema.sql").write_text(
        "CREATE TABLE users (id INT);\n"
        "CREATE INDEX idx_users_id ON users(id);\n"
        "ALTER TABLE users ADD COLUMN email VARCHAR(255);\n",
        encoding="utf-8",
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()

    s = extract_file_summary(repo, sha, "schema.sql")
    assert s.language == "sql"
    assert "CREATE TABLE users" in s.schema_lines
    assert "CREATE INDEX idx_users_id" in s.schema_lines
    assert "ALTER TABLE users" in s.schema_lines


def test_extract_returns_error_on_missing_file(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "t@e.com"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "x.txt").write_text("x", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()

    s = extract_file_summary(repo, sha, "nonexistent.cls")
    assert s.error
    assert "unreadable" in s.error.lower()


def test_summarize_files_caps_at_max(cls_repo: tuple[Path, str]) -> None:
    """Beyond MAX_FILES_PER_CYCLE, files are listed as truncated."""
    from memory_kit_mcp.archeo.file_summary import MAX_FILES_PER_CYCLE

    repo, sha = cls_repo
    files = ["src/EcoSAV/Statut.cls"] * (MAX_FILES_PER_CYCLE + 5)
    summaries, truncated = summarize_files(repo, sha, files)
    assert len(summaries) == MAX_FILES_PER_CYCLE
    assert truncated == 5


def test_render_technical_section_groups_by_language() -> None:
    summaries = [
        FileSummary(path="a.cls", language="cls", classes=["Foo"]),
        FileSummary(path="b.cls", language="cls", methods=["bar"]),
        FileSummary(path="c.py", language="py", classes=["Baz"]),
    ]
    md = render_technical_section(summaries, truncated=0)
    assert "### cls (2 file(s))" in md
    assert "### py (1 file(s))" in md
    assert "`a.cls`" in md
    assert "`Foo`" in md
    assert "Mechanical extraction" in md


def test_render_technical_section_surfaces_truncated_count() -> None:
    md = render_technical_section(
        [FileSummary(path="a.cls", language="cls")], truncated=7
    )
    assert "+ 7 more not inspected" in md


def test_render_technical_section_handles_empty() -> None:
    md = render_technical_section([], truncated=0)
    assert "perimeter empty" in md
