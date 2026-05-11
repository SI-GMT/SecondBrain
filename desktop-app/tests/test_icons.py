"""Icon rendering tests — verify produced images have expected size + mode."""

from __future__ import annotations

from pathlib import Path

from sb_desktop import icons
from sb_desktop.status import StatusLevel


def test_render_icon_returns_image_at_requested_size():
    for size in (16, 32, 48):
        img = icons.render_icon(StatusLevel.OK, size=size)
        assert img.size == (size, size)
        assert img.mode == "RGBA"


def test_render_icon_distinct_per_state():
    a = icons.render_icon(StatusLevel.OK, size=64)
    b = icons.render_icon(StatusLevel.ERROR, size=64)
    assert list(a.tobytes()) != list(b.tobytes())


def test_render_app_icon_no_status_disc():
    app = icons.render_app_icon(128)
    assert app.size == (128, 128)


def test_export_static_icons_writes_expected_files(tmp_path: Path):
    written = icons.export_static_icons(tmp_path)
    names = {p.name for p in written}
    assert "app.ico" in names
    assert any("tray-ok-" in n and n.endswith(".png") for n in names)
    assert any("app-256.png" == n for n in names)
