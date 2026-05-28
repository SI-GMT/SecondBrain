"""Phase E — mem_archive emits <repo>/... sigils at write time."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


def _set_repo_path(vault: Path, slug: str, repo_path: str) -> None:
    ctx = vault / "10-episodes" / "projects" / slug / "context.md"
    fm, body = frontmatter.read(ctx)
    fm["repo_path"] = repo_path
    frontmatter.write(ctx, fm, body)


async def test_full_archive_sigilizes_body_when_repo_path_set(
    client: Client, vault_tmp: Path
) -> None:
    repo = r"C:\_PROJETS\DEVOPS\Alpha"
    _set_repo_path(vault_tmp, "alpha", repo)

    await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": f"Touched `{repo}\\src\\main.py` this session.",
            "archive_subject": "sigil test",
            "archive_body_md": (
                f"# Session\n\nEdited `{repo}\\src\\foo.py` and "
                f"`{repo}\\tests\\test_foo.py`.\n"
            ),
        },
    )

    archives = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    arch = next(archives.glob("*-sigil-test.md"))
    _, body = frontmatter.read(arch)
    assert repo not in body
    assert "<repo>/src/foo.py" in body
    assert "<repo>/tests/test_foo.py" in body

    # context.md body also sigilized.
    ctx = vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    _, ctx_body = frontmatter.read(ctx)
    assert repo not in ctx_body
    assert "<repo>/src/main.py" in ctx_body


async def test_full_archive_noop_when_repo_path_unset(
    client: Client, vault_tmp: Path
) -> None:
    # alpha has no repo_path: absolute paths pass through unchanged.
    abs_path = r"C:\somewhere\else\file.py"
    await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "no repo_path here",
            "archive_subject": "noop test",
            "archive_body_md": f"# Session\n\nSaw `{abs_path}`.\n",
        },
    )
    archives = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    arch = next(archives.glob("*-noop-test.md"))
    _, body = frontmatter.read(arch)
    # Path left intact (no repo_path to anchor a sigil).
    assert abs_path.replace("\\", "/") in body.replace("\\", "/")


async def test_full_archive_leaves_foreign_paths_intact(
    client: Client, vault_tmp: Path
) -> None:
    repo = r"C:\_PROJETS\DEVOPS\Alpha"
    _set_repo_path(vault_tmp, "alpha", repo)
    foreign = r"D:\other\proj\lib.py"

    await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "ctx",
            "archive_subject": "mixed paths",
            "archive_body_md": (
                f"# Session\n\nIn-repo `{repo}\\a.py`, foreign `{foreign}`.\n"
            ),
        },
    )
    archives = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    arch = next(archives.glob("*-mixed-paths.md"))
    _, body = frontmatter.read(arch)
    assert "<repo>/a.py" in body
    # Foreign path (outside repo_path) untouched.
    assert foreign.replace("\\", "/") in body.replace("\\", "/")
