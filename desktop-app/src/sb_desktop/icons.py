"""Programmatic icon generation.

Tray icons are built on-the-fly with Pillow so we don't have to ship a
fan of pre-rendered PNGs at every DPI. Build-time helpers in
:func:`export_static_icons` write out the static PNG/ICO/ICNS variants
that the installer and the macOS bundle require.

Design grammar:

* Square canvas, transparent background.
* A central "brain" glyph — two interlocking rounded squares — in
  desaturated indigo, drawn at every state.
* A 35 %-radius status disc in the bottom-right corner. Its colour
  encodes the :class:`StatusLevel`:
    * green  — OK
    * amber  — WARNING
    * red    — ERROR
    * grey   — UNKNOWN
* Anti-aliased via 4× supersampling so the icon stays crisp at 16 px.

The palette is intentionally narrow and deliberately unfun — readability
on dark and light system trays beats branding flair at 16 px.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from .status import StatusLevel

_BG = (0, 0, 0, 0)
_BRAIN = (66, 80, 156, 255)
_BRAIN_ACCENT = (120, 134, 200, 255)
_OUTLINE = (28, 32, 64, 255)

_STATUS_COLOURS: dict[StatusLevel, tuple[int, int, int, int]] = {
    StatusLevel.OK: (45, 168, 90, 255),
    StatusLevel.WARNING: (217, 153, 33, 255),
    StatusLevel.ERROR: (200, 55, 55, 255),
    StatusLevel.UNKNOWN: (120, 120, 130, 255),
}

_SUPERSAMPLE = 4


def _draw_brain(draw: ImageDraw.ImageDraw, size: int) -> None:
    pad = size // 8
    inner = size - 2 * pad
    radius = inner // 4
    half = inner // 2 + pad // 2

    # Left lobe
    left_box = (pad, pad, pad + half, pad + inner)
    draw.rounded_rectangle(left_box, radius=radius, fill=_BRAIN, outline=_OUTLINE, width=size // 24)
    # Right lobe (offset, slightly lighter for the parting)
    right_box = (size - pad - half, pad, size - pad, pad + inner)
    draw.rounded_rectangle(
        right_box, radius=radius, fill=_BRAIN_ACCENT, outline=_OUTLINE, width=size // 24
    )
    # Vertical seam
    seam_x = size // 2
    draw.line(
        [(seam_x, pad + size // 16), (seam_x, pad + inner - size // 16)],
        fill=_OUTLINE,
        width=size // 32,
    )


def _draw_status_disc(
    draw: ImageDraw.ImageDraw, size: int, level: StatusLevel
) -> None:
    radius = size * 35 // 100
    centre_x = size - radius // 2 - size // 24
    centre_y = size - radius // 2 - size // 24
    box = (
        centre_x - radius // 2,
        centre_y - radius // 2,
        centre_x + radius // 2,
        centre_y + radius // 2,
    )
    halo_box = (box[0] - size // 32, box[1] - size // 32, box[2] + size // 32, box[3] + size // 32)
    draw.ellipse(halo_box, fill=(255, 255, 255, 220))
    draw.ellipse(box, fill=_STATUS_COLOURS[level], outline=_OUTLINE, width=size // 32)


def render_icon(level: StatusLevel, size: int = 64) -> Image.Image:
    """Render a tray icon at the requested pixel size with the given state.

    Returns a fresh ``PIL.Image.Image`` each call so callers can attach it
    to ``pystray.Icon`` without sharing mutable state.
    """
    base_size = max(size * _SUPERSAMPLE, 64)
    img = Image.new("RGBA", (base_size, base_size), _BG)
    draw = ImageDraw.Draw(img)
    _draw_brain(draw, base_size)
    _draw_status_disc(draw, base_size, level)
    if base_size != size:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def render_app_icon(size: int = 256) -> Image.Image:
    """Square brand icon without the status disc — for window titles, dialogs,
    and the installer hero image.
    """
    base_size = max(size * _SUPERSAMPLE, 256)
    img = Image.new("RGBA", (base_size, base_size), _BG)
    draw = ImageDraw.Draw(img)
    _draw_brain(draw, base_size)
    if base_size != size:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def export_static_icons(target_dir: Path, *, levels: Iterable[StatusLevel] = ()) -> list[Path]:
    """Write static PNG / ICO / ICNS variants under ``target_dir``.

    Called from ``python -m sb_desktop.icons --export <dir>`` at build time
    so the installer and the macOS bundle pick up canonical artwork. Returns
    the list of paths written.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for level in levels or list(StatusLevel):
        for size in (16, 24, 32, 48, 64, 128, 256):
            png_path = target_dir / f"tray-{level.value}-{size}.png"
            render_icon(level, size).save(png_path, format="PNG", optimize=True)
            written.append(png_path)

    app_sizes = (16, 32, 48, 64, 128, 256, 512)
    app_images = [render_app_icon(size) for size in app_sizes]
    for size, img in zip(app_sizes, app_images, strict=False):
        path = target_dir / f"app-{size}.png"
        img.save(path, format="PNG", optimize=True)
        written.append(path)

    ico_path = target_dir / "app.ico"
    app_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in app_sizes if s <= 256],
    )
    written.append(ico_path)

    return written


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export sb-desktop icons")
    parser.add_argument("--export", type=Path, required=True, help="Target directory")
    args = parser.parse_args(argv)
    paths = export_static_icons(args.export)
    for p in paths:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
