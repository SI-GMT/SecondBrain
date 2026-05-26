"""Kit installer tests — pure Python V0.6 architecture."""

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
    kit_installer.ensure_vault_exists(target)
    assert target.is_dir()


def _isolate_filesystem_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every non-shutil detection source to an empty result.

    detect_llm_clis now also walks NPM globals and platform alt-dirs;
    tests want to control detection purely via the ``which`` mock and
    ``tmp_path`` home, so we silence the filesystem probes.
    """
    monkeypatch.setattr(kit_installer, "_npm_global_bin_dirs", lambda: [])
    monkeypatch.setattr(kit_installer, "_alt_install_dirs", lambda: [])


def test_detect_llm_clis_no_installs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    _isolate_filesystem_probes(monkeypatch)
    results = kit_installer.detect_llm_clis()
    identifiers = {r.identifier for r in results}
    assert {
        "claude-code",
        "claude-desktop",
        "codex",
        "gemini-cli",
        "mistral-vibe",
        "copilot-cli",
        "antigravity-cli",
        "antigravity-desktop",
    }.issubset(identifiers)
    assert all(not r.installed for r in results)


def test_detect_llm_clis_picks_up_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        kit_installer.shutil,
        "which",
        lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    _isolate_filesystem_probes(monkeypatch)
    results = {r.identifier: r for r in kit_installer.detect_llm_clis()}
    assert results["claude-code"].binary_on_path is True
    assert results["claude-code"].installed is True


def test_detect_llm_clis_picks_up_npm_global(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A CLI installed under NPM globals must be detected even when off PATH."""
    monkeypatch.setattr(kit_installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    # Mimic Windows-style npm-global drop: ``gemini.cmd`` shim alongside
    # other tools, none of which are on PATH.
    (npm_dir / "gemini.cmd").write_text("@echo gemini", encoding="utf-8")
    monkeypatch.setattr(kit_installer, "_npm_global_bin_dirs", lambda: [npm_dir])
    monkeypatch.setattr(kit_installer, "_alt_install_dirs", lambda: [])

    results = {r.identifier: r for r in kit_installer.detect_llm_clis()}
    assert results["gemini-cli"].binary_on_path is True
    assert results["gemini-cli"].binary_path == npm_dir / "gemini.cmd"


def test_detect_llm_clis_picks_up_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(kit_installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    _isolate_filesystem_probes(monkeypatch)
    (tmp_path / ".codex").mkdir()
    results = {r.identifier: r for r in kit_installer.detect_llm_clis()}
    assert results["codex"].config_present is True
    assert results["codex"].installed is True


def test_install_layout_roots_under_install_dir(tmp_path: Path):
    layout = kit_installer.InstallLayout.from_install_dir(tmp_path)
    assert layout.install_dir == tmp_path.resolve()
    assert layout.app_dir == tmp_path.resolve() / "app"
    assert layout.engine_dir == tmp_path.resolve() / "engine"
    assert layout.python_dir == tmp_path.resolve() / "engine" / "python"
    assert layout.wheels_dir == tmp_path.resolve() / "engine" / "wheels"
    assert layout.scripts_dir == tmp_path.resolve() / "engine" / "Scripts"
    assert layout.resources_dir == tmp_path.resolve() / "resources"


def test_bootstrap_no_python_exe(tmp_path: Path):
    layout = kit_installer.InstallLayout.from_install_dir(tmp_path)
    result = kit_installer.bootstrap_python_embeddable(layout)
    assert result.ok is False
    assert "python executable not found" in result.detail


def test_install_wheels_no_wheels_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = kit_installer.InstallLayout.from_install_dir(tmp_path)
    # python_exe exists but wheels dir does not
    layout.python_dir.mkdir(parents=True)
    (layout.python_exe).write_text("", encoding="utf-8")
    result = kit_installer.install_kit_wheels(layout)
    assert result.ok is False
    assert "wheels directory missing" in result.detail


def test_resolve_config_path_claude_desktop_windows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(kit_installer.sys, "platform", "win32")
    cli = next(
        c for c in kit_installer._cli_targets() if c.identifier == "claude-desktop"
    )
    path = kit_installer._resolve_config_path(cli)
    assert path is not None
    assert "claude_desktop_config.json" in str(path)
    assert "AppData" in str(path)


def test_resolve_config_path_codex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    cli = next(c for c in kit_installer._cli_targets() if c.identifier == "codex")
    path = kit_installer._resolve_config_path(cli)
    assert path == tmp_path / ".codex" / "config.toml"


def test_resolve_config_path_antigravity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(kit_installer.Path, "home", classmethod(lambda cls: tmp_path))
    
    cli_cli = next(c for c in kit_installer._cli_targets() if c.identifier == "antigravity-cli")
    path_cli = kit_installer._resolve_config_path(cli_cli)
    assert path_cli == tmp_path / ".gemini" / "antigravity-cli" / "mcp_config.json"

    cli_desktop = next(c for c in kit_installer._cli_targets() if c.identifier == "antigravity-desktop")
    path_desktop = kit_installer._resolve_config_path(cli_desktop)
    assert path_desktop == tmp_path / ".gemini" / "antigravity" / "mcp_config.json"



def test_install_plan_dataclass(tmp_path: Path):
    plan = kit_installer.InstallPlan(
        vault=tmp_path / "vault",
        language="en",
        install_dir=tmp_path / "install",
    )
    assert plan.selected_clis == []
    assert plan.language == "en"
