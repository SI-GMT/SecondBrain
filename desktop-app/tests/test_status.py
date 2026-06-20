"""Status snapshot tests — in-process model."""

from __future__ import annotations

from pathlib import Path

import pytest

from sb_desktop import status


@pytest.fixture(autouse=True)
def _reset_pipx_cache():
    """Each test starts with a clean session-level cache."""
    status.invalidate_pipx_cache()
    yield
    status.invalidate_pipx_cache()


def test_bundled_engine_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: (None, "fake error"))
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.ERROR
    assert "missing" in snap.summary.lower()


def test_pipx_absent_yields_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(status, "_probe_pipx_once", lambda: (None, None))
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert "not on PATH" in snap.summary
    assert snap.bundled_version == "0.12.1"


def test_venv_root_accepts_secondbrain_engine_layout(tmp_path: Path):
    """SecondBrain bundled engine has Lib/site-packages but no pyvenv.cfg."""
    engine = tmp_path / "engine"
    scripts = engine / "Scripts"
    sp = engine / "Lib" / "site-packages"
    scripts.mkdir(parents=True)
    sp.mkdir(parents=True)
    binary = scripts / "memory-kit-mcp.exe"
    binary.write_text("")
    assert status._venv_root_from_binary(binary) == engine


def test_venv_root_accepts_classic_pipx_layout(tmp_path: Path):
    venv = tmp_path / "venvs" / "memory-kit-mcp"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = ...", encoding="utf-8")
    binary = venv / "Scripts" / "memory-kit-mcp.exe"
    binary.write_text("")
    assert status._venv_root_from_binary(binary) == venv


def test_venv_root_resolves_local_bin_symlink(tmp_path: Path):
    venv = tmp_path / ".local" / "pipx" / "venvs" / "memory-kit-mcp"
    bin_dir = venv / "bin"
    shim_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    shim_dir.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = ...", encoding="utf-8")
    binary = bin_dir / "memory-kit-mcp"
    binary.write_text("")
    shim = shim_dir / "memory-kit-mcp"
    shim.symlink_to(binary)
    assert status._venv_root_from_binary(shim) == venv


def test_versions_aligned_yields_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", "0.12.1")
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.OK
    assert snap.versions_match is True


def test_versions_drift_yields_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", "0.11.0")
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert snap.versions_match is False
    assert "0.11" in snap.summary


def test_pipx_version_probe_failed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", None)
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert "--version probe failed" in snap.summary


def test_render_text_includes_all_fields():
    snap = status.StatusSnapshot(
        level=status.StatusLevel.OK,
        summary="Engine v0.12.1 ready.",
        bundled_version="0.12.1",
        pipx_binary_path=Path("C:/x/memory-kit-mcp.exe"),
        pipx_version="0.12.1",
        versions_match=True,
    )
    text = snap.render_text()
    assert "Bundled engine: v0.12.1" in text
    assert "pipx version:  v0.12.1" in text


def test_render_text_drift_and_error():
    snap = status.StatusSnapshot(
        level=status.StatusLevel.WARNING,
        summary="drift",
        versions_match=False,
        error="boom",
    )
    text = snap.render_text()
    assert "versions differ" in text
    assert "Error: boom" in text


# ---------------------------------------------------------------------------
# _looks_like_install_root
# ---------------------------------------------------------------------------


def test_looks_like_install_root_pyvenv(tmp_path: Path):
    (tmp_path / "pyvenv.cfg").write_text("x", encoding="utf-8")
    assert status._looks_like_install_root(tmp_path) is True


def test_looks_like_install_root_win_site_packages(tmp_path: Path):
    (tmp_path / "Lib" / "site-packages").mkdir(parents=True)
    assert status._looks_like_install_root(tmp_path) is True


def test_looks_like_install_root_posix_lib_python(tmp_path: Path):
    (tmp_path / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    assert status._looks_like_install_root(tmp_path) is True


def test_looks_like_install_root_false(tmp_path: Path):
    assert status._looks_like_install_root(tmp_path) is False


# ---------------------------------------------------------------------------
# _venv_root_from_binary fallback
# ---------------------------------------------------------------------------


def test_venv_root_fallback_to_pipx_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    default = tmp_path / "pipx-venv"
    default.mkdir()
    monkeypatch.setattr(status, "_pipx_default_venv", lambda: default)
    # binary sits in a non-scripts dir → fall back to the pipx default.
    binary = tmp_path / "somewhere" / "memory-kit-mcp"
    assert status._venv_root_from_binary(binary) == default


def test_venv_root_none_when_no_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(
        status, "_pipx_default_venv", lambda: tmp_path / "does-not-exist"
    )
    binary = tmp_path / "x" / "memory-kit-mcp"
    assert status._venv_root_from_binary(binary) is None


# ---------------------------------------------------------------------------
# _read_version_from_metadata (Windows layout)
# ---------------------------------------------------------------------------


def _make_dist_info(venv_root: Path, version: str) -> None:
    sp = venv_root / "Lib" / "site-packages"
    dist = sp / "memory_kit_mcp-0.0.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: memory-kit-mcp\nVersion: {version}\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="Windows site-packages layout"
)
def test_read_version_from_metadata_happy(tmp_path: Path):
    _make_dist_info(tmp_path, "0.14.0")
    assert status._read_version_from_metadata(tmp_path) == "0.14.0"


@pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="Windows site-packages layout"
)
def test_read_version_no_site_packages(tmp_path: Path):
    assert status._read_version_from_metadata(tmp_path) is None


@pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="Windows site-packages layout"
)
def test_read_version_no_dist_info(tmp_path: Path):
    (tmp_path / "Lib" / "site-packages").mkdir(parents=True)
    assert status._read_version_from_metadata(tmp_path) is None


@pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="Windows site-packages layout"
)
def test_read_version_no_version_line(tmp_path: Path):
    sp = tmp_path / "Lib" / "site-packages"
    dist = sp / "memory_kit_mcp-0.0.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Name: memory-kit-mcp\n", encoding="utf-8")
    assert status._read_version_from_metadata(tmp_path) is None


# ---------------------------------------------------------------------------
# _probe_pipx_once
# ---------------------------------------------------------------------------


def test_probe_pipx_once_no_binary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status.shutil, "which", lambda name: None)
    assert status._probe_pipx_once() == (None, None)
    # Cached: a second call returns the same tuple without re-probing.
    monkeypatch.setattr(
        status.shutil,
        "which",
        lambda name: (_ for _ in ()).throw(AssertionError("re-probed")),
    )
    assert status._probe_pipx_once() == (None, None)


def test_probe_pipx_once_happy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    binary = tmp_path / "Scripts" / "memory-kit-mcp.exe"
    monkeypatch.setattr(status.shutil, "which", lambda name: str(binary))
    monkeypatch.setattr(status, "_venv_root_from_binary", lambda b: tmp_path)
    monkeypatch.setattr(status, "_read_version_from_metadata", lambda r: "0.14.0")
    assert status._probe_pipx_once() == (str(binary), "0.14.0")


def test_probe_pipx_once_venv_unresolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    binary = tmp_path / "bin" / "memory-kit-mcp"
    monkeypatch.setattr(status.shutil, "which", lambda name: str(binary))
    monkeypatch.setattr(status, "_venv_root_from_binary", lambda b: None)
    assert status._probe_pipx_once() == (str(binary), None)


def test_bundled_version_import_error(monkeypatch: pytest.MonkeyPatch):
    import sys

    monkeypatch.setitem(sys.modules, "memory_kit_mcp", None)
    version, err = status._bundled_version()
    assert version is None
    assert "import failed" in (err or "")
