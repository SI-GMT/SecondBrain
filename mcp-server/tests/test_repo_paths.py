"""Tests for vault.repo_paths — sigil <repo>/... helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from memory_kit_mcp.vault import repo_paths as rp
from memory_kit_mcp.vault.repo_paths import (
    SIGIL,
    find_abs_paths_under_root,
    from_repo_relative,
    is_repo_relative,
    rewrite_abs_paths_to_sigil,
    to_repo_relative,
)

WIN = os.name == "nt"


class TestToRepoRelative:
    def test_simple_under_root(self):
        assert to_repo_relative("C:/foo/bar/baz.py", "C:/foo") == "<repo>/bar/baz.py"

    def test_equal_to_root(self):
        assert to_repo_relative("C:/foo", "C:/foo") == "<repo>"

    def test_equal_with_trailing_slash(self):
        assert to_repo_relative("C:/foo/", "C:/foo") == "<repo>"
        assert to_repo_relative("C:/foo", "C:/foo/") == "<repo>"

    def test_outside_root_returns_none(self):
        assert to_repo_relative("D:/other/x.py", "C:/foo") is None

    def test_prefix_collision_not_match(self):
        # "C:/foo-bar" must not match root "C:/foo".
        assert to_repo_relative("C:/foo-bar/x.py", "C:/foo") is None

    def test_backslash_input(self):
        assert to_repo_relative(r"C:\foo\bar\baz.py", r"C:\foo") == "<repo>/bar/baz.py"

    def test_mixed_separators(self):
        assert to_repo_relative(r"C:\foo/bar\baz.py", "C:/foo") == "<repo>/bar/baz.py"

    @pytest.mark.skipif(not WIN, reason="case-insensitive only on Windows")
    def test_case_insensitive_windows(self):
        assert to_repo_relative("c:/FOO/bar.py", "C:/foo") == "<repo>/bar.py"

    def test_tail_preserves_original_case(self):
        # Even on Windows, the tail should preserve the original casing.
        assert to_repo_relative("C:/foo/SubDir/File.py", "C:/foo") == "<repo>/SubDir/File.py"

    def test_path_input_type(self):
        assert to_repo_relative(Path("C:/foo/bar"), Path("C:/foo")) == "<repo>/bar"

    def test_root_is_subpath_of_other(self):
        # Root "/a/b" should match "/a/b/c" but not "/a/bcd".
        assert to_repo_relative("/a/b/c", "/a/b") == "<repo>/c"
        assert to_repo_relative("/a/bcd", "/a/b") is None


class TestFromRepoRelative:
    def test_simple(self):
        result = from_repo_relative("<repo>/src/foo.py", "C:/proj")
        assert result == Path("C:/proj/src/foo.py")

    def test_bare_sigil(self):
        result = from_repo_relative("<repo>", "C:/proj")
        assert result == Path("C:/proj")

    def test_bare_sigil_with_trailing_slash(self):
        result = from_repo_relative("<repo>/", "C:/proj")
        assert result == Path("C:/proj")

    def test_not_sigil_raises(self):
        with pytest.raises(ValueError, match="Not a repo-sigil"):
            from_repo_relative("src/foo.py", "C:/proj")
        with pytest.raises(ValueError):
            from_repo_relative("C:/abs/path", "C:/proj")

    def test_sigil_substring_inside_text_rejected(self):
        # Only matches if string STARTS with sigil.
        with pytest.raises(ValueError):
            from_repo_relative("prefix<repo>/x", "C:/proj")


class TestIsRepoRelative:
    @pytest.mark.parametrize(
        "s,expected",
        [
            ("<repo>", True),
            ("<repo>/", True),
            ("<repo>/src/foo.py", True),
            ("<repo>x", False),  # no slash after sigil
            ("src/<repo>/foo", False),
            ("src/foo.py", False),
            ("C:/abs/path", False),
            ("", False),
        ],
    )
    def test_cases(self, s, expected):
        assert is_repo_relative(s) is expected


class TestFindAbsPathsUnderRoot:
    def test_single_path_in_text(self):
        text = "See `C:/proj/src/foo.py` for details."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 1
        start, end, matched = matches[0]
        assert text[start:end] == "C:/proj/src/foo.py"
        assert matched == "C:/proj/src/foo.py"

    def test_multiple_paths(self):
        text = "Edited C:/proj/a.py and C:/proj/sub/b.py at the same time."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 2
        assert text[matches[0][0] : matches[0][1]] == "C:/proj/a.py"
        assert text[matches[1][0] : matches[1][1]] == "C:/proj/sub/b.py"

    def test_backslash_paths(self):
        text = r"Path: C:\proj\src\foo.py done."
        matches = find_abs_paths_under_root(text, r"C:\proj")
        assert len(matches) == 1
        assert matches[0][2] == r"C:\proj\src\foo.py"

    def test_root_specified_as_forward_slash_matches_backslash_text(self):
        text = r"Edit C:\proj\bar.py please."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 1
        assert matches[0][2] == r"C:\proj\bar.py"

    def test_bare_root_match(self):
        # "C:/proj" alone (no tail) is a valid match.
        text = "Open C:/proj in editor."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 1
        assert matches[0][2] == "C:/proj"

    def test_outside_root_not_matched(self):
        text = "Some D:/other/file.py path."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert matches == []

    def test_stops_at_quote_delimiter(self):
        # Path inside backticks should be matched up to the closing backtick.
        text = "Use `C:/proj/x.py` here."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 1
        assert matches[0][2] == "C:/proj/x.py"

    def test_empty_root_returns_empty(self):
        assert find_abs_paths_under_root("anything", "") == []

    @pytest.mark.skipif(not WIN, reason="case-insensitive only on Windows")
    def test_case_insensitive_windows(self):
        text = "Path c:/PROJ/file.py here."
        matches = find_abs_paths_under_root(text, "C:/proj")
        assert len(matches) == 1


class TestRewriteAbsPathsToSigil:
    def test_simple_rewrite(self):
        text = "See C:/proj/src/foo.py for context."
        new, n = rewrite_abs_paths_to_sigil(text, "C:/proj")
        assert n == 1
        assert new == "See <repo>/src/foo.py for context."

    def test_multiple_rewrites(self):
        text = "Files: C:/proj/a.py and C:/proj/b.py."
        new, n = rewrite_abs_paths_to_sigil(text, "C:/proj")
        assert n == 2
        assert new == "Files: <repo>/a.py and <repo>/b.py."

    def test_no_match_returns_original(self):
        text = "Nothing here matching D:/other."
        new, n = rewrite_abs_paths_to_sigil(text, "C:/proj")
        assert n == 0
        assert new == text

    def test_backslash_input_normalized_to_forward(self):
        text = r"Open C:\proj\src\foo.py please."
        new, n = rewrite_abs_paths_to_sigil(text, r"C:\proj")
        assert n == 1
        assert new == "Open <repo>/src/foo.py please."

    def test_mixed_inside_outside(self):
        text = "C:/proj/x.py and D:/other/y.py done."
        new, n = rewrite_abs_paths_to_sigil(text, "C:/proj")
        assert n == 1
        assert new == "<repo>/x.py and D:/other/y.py done."

    def test_bare_root_only(self):
        text = "Just C:/proj here."
        new, n = rewrite_abs_paths_to_sigil(text, "C:/proj")
        assert n == 1
        assert new == "Just <repo> here."


class TestRoundTrip:
    @pytest.mark.parametrize(
        "abs_path,root",
        [
            ("C:/proj/src/foo.py", "C:/proj"),
            ("C:/proj", "C:/proj"),
            ("/usr/share/proj/lib/x", "/usr/share/proj"),
        ],
    )
    def test_to_then_from(self, abs_path, root):
        sigil = to_repo_relative(abs_path, root)
        assert sigil is not None
        restored = from_repo_relative(sigil, root)
        assert restored == Path(abs_path)


class TestSigilExport:
    def test_sigil_constant(self):
        assert SIGIL == "<repo>"

    def test_module_reexports(self):
        # Smoke test that key symbols are accessible via the module path.
        assert callable(rp.to_repo_relative)
        assert callable(rp.from_repo_relative)
        assert callable(rp.is_repo_relative)
        assert callable(rp.find_abs_paths_under_root)
        assert callable(rp.rewrite_abs_paths_to_sigil)
