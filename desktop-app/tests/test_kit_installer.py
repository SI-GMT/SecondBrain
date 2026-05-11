"""Kit installer tests — primitives, plan, install subprocess mock."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sb_desktop import kit_installer


def test_default_vault_path_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    assert kit_installer.default_vault_path() == tmp_path / "Documents" / "SecondBrain"


def test_ensure_vault_creates_dir(tmp_path: Path):
    target = tmp_path / "vault"
    kit_installer.ensure_vault_exists(target)
    assert target.is_dir()
    # idempotent
    kit_installer.ensure_vault_exists(target)
    assert target.is_dir()


def test_detect_llm_clis_returns_known_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    results = kit_installer.detect_llm_clis()
    identifiers = {r.identifier for r in results}
    assert {"claude-code", "claude-desktop", "codex", "gemini-cli", "mistral-vibe", "copilot-cli"}.issubset(
        identifiers
    )
    # None installed in a fresh tmp home.
    assert all(not r.installed for r in results)


def test_detect_llm_clis_picks_up_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))

    def fake_which(name):
        return "/usr/bin/claude" if name == "claude" else None

    monkeypatch.setattr(kit_installer.shutil, "which", fake_which)
    results = {r.identifier: r for r in kit_installer.detect_llm_clis()}
    assert results["claude-code"].binary_on_path is True
    assert results["claude-code"].installed is True


def test_detect_llm_clis_picks_up_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(kit_installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    results = {r.identifier: r for r in kit_installer.detect_llm_clis()}
    assert results["codex"].config_present is True
    assert results["codex"].installed is True


def test_find_bundled_kit_repo_returns_none_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv("MEMORY_KIT_REPO", raising=False)
    monkeypatch.setattr(kit_installer.sys, "executable", str(tmp_path / "exe"))
    # tests/ is alongside the actual repo, so the source-checkout fallback
    # may still find a real script — force-isolate by repointing __file__.
    monkeypatch.setattr(
        kit_installer,
        "__file__",
        str(tmp_path / "nested" / "deeper" / "deepest" / "fake.py"),
    )
    assert kit_installer.find_bundled_kit_repo() is None


def test_find_bundled_kit_repo_respects_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    repo = tmp_path / "kit"
    repo.mkdir()
    (repo / "deploy.ps1").write_text("# fake", encoding="utf-8")
    monkeypatch.setenv("MEMORY_KIT_REPO", str(repo))
    assert kit_installer.find_bundled_kit_repo() == repo


def test_run_install_no_script(tmp_path: Path):
    plan = kit_installer.InstallPlan(
        vault=tmp_path / "vault",
        language="en",
        kit_repo=tmp_path / "kit-missing",
    )
    report = kit_installer.run_install(plan)
    assert report.ok is False
    assert "deploy script not found" in (report.error or "")


def test_run_install_streams_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# fake", encoding="utf-8")

    monkeypatch.setattr(kit_installer.shutil, "which", lambda name: f"/usr/bin/{name}")

    class FakeProc:
        def __init__(self, *args, **kwargs):
            import io

            self.stdout = io.StringIO("hello\nworld\n")
            self.returncode = 0

        def wait(self, timeout: int = 0):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(kit_installer.subprocess, "Popen", FakeProc)

    seen: list[str] = []
    plan = kit_installer.InstallPlan(
        vault=tmp_path / "vault", language="en", kit_repo=repo
    )
    report = kit_installer.run_install(plan, on_line=seen.append)
    assert report.ok is True
    assert "hello" in seen and "world" in seen
