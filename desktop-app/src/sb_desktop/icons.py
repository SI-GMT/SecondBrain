"""Icon assets — bundled brand artwork + runtime status overlay.

The SecondBrain brand glyph lives as raster PNG assets shipped under
``src/sb_desktop/icons/png/`` (rendered offline from the SVG masters in
``src/sb_desktop/icons/secondbrain-*.svg``). Runtime loads the closest
size and composes a status disc over it for the tray icon.

Why PNG-not-SVG at runtime: rendering SVG on Windows requires native
libraries (libcairo, librsvg, …) that PyInstaller bundling is fragile
around. Pre-rasterising at every common size yields ~50 KB of assets
and zero runtime dependency on a vector library.

Re-rasterise the assets with ``python -m sb_desktop.icons --rerender``
after any update to the source SVGs (build venv only; needs
``resvg-py`` which is NOT a runtime dep).
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from .status import StatusLevel

log = logging.getLogger(__name__)

_BG = (0, 0, 0, 0)
_OUTLINE = (28, 32, 64, 255)

_STATUS_COLOURS: dict[StatusLevel, tuple[int, int, int, int]] = {
    StatusLevel.OK: (45, 168, 90, 255),
    StatusLevel.WARNING: (217, 153, 33, 255),
    StatusLevel.ERROR: (200, 55, 55, 255),
    StatusLevel.UNKNOWN: (120, 120, 130, 255),
}

_APP_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
_FAVICON_SIZES = (16, 24, 32)


def _asset_dir() -> Path:
    return Path(__file__).resolve().parent / "icons" / "png"


def _load_brand_png(size: int, *, prefer_favicon: bool) -> Image.Image:
    """Return the bundled SecondBrain monogram closest to ``size``.

    Below 32 px we prefer the simplified favicon variant (thicker
    strokes, cleaner at 16 px) when available; above we use the
    full monogram.
    """
    asset_dir = _asset_dir()
    candidates: list[int] = []
    if prefer_favicon and size <= 32:
        candidates = [s for s in _FAVICON_SIZES if s >= size] or list(_FAVICON_SIZES)
        for s in candidates:
            path = asset_dir / f"secondbrain-favicon-{s}.png"
            if path.is_file():
                img = Image.open(path).convert("RGBA")
                if img.size != (size, size):
                    img = img.resize((size, size), Image.Resampling.LANCZOS)
                return img
    candidates = [s for s in _APP_SIZES if s >= size] or list(_APP_SIZES)
    for s in candidates:
        path = asset_dir / f"secondbrain-monogram-{s}.png"
        if path.is_file():
            img = Image.open(path).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            return img
    raise FileNotFoundError(
        f"No SecondBrain PNG asset found for size {size}px under {asset_dir}"
    )


def _draw_status_disc(
    base: Image.Image, level: StatusLevel
) -> None:
    """Composite a coloured status disc onto the bottom-right of ``base``."""
    size = base.size[0]
    draw = ImageDraw.Draw(base)
    radius = size * 35 // 100
    centre_x = size - radius // 2 - size // 24
    centre_y = size - radius // 2 - size // 24
    box = (
        centre_x - radius // 2,
        centre_y - radius // 2,
        centre_x + radius // 2,
        centre_y + radius // 2,
    )
    halo_box = (
        box[0] - size // 32,
        box[1] - size // 32,
        box[2] + size // 32,
        box[3] + size // 32,
    )
    draw.ellipse(halo_box, fill=(255, 255, 255, 220))
    draw.ellipse(
        box,
        fill=_STATUS_COLOURS[level],
        outline=_OUTLINE,
        width=max(1, size // 32),
    )


def render_icon(level: StatusLevel, size: int = 64) -> Image.Image:
    """Render the SecondBrain tray icon at ``size`` px with status overlay."""
    img = _load_brand_png(size, prefer_favicon=True).copy()
    _draw_status_disc(img, level)
    return img


def render_app_icon(size: int = 256) -> Image.Image:
    """Square brand icon WITHOUT the status disc — for window titles, dialogs,
    and the installer hero image.
    """
    return _load_brand_png(size, prefer_favicon=False).copy()


def export_static_icons(
    target_dir: Path, *, levels: Iterable[StatusLevel] = ()
) -> list[Path]:
    """Write static PNG / ICO variants under ``target_dir`` (build-time)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for level in levels or list(StatusLevel):
        for size in (16, 24, 32, 48, 64, 128, 256):
            png_path = target_dir / f"tray-{level.value}-{size}.png"
            render_icon(level, size).save(png_path, format="PNG", optimize=True)
            written.append(png_path)

    for size in (16, 32, 48, 64, 128, 256, 512):
        path = target_dir / f"app-{size}.png"
        render_app_icon(size).save(path, format="PNG", optimize=True)
        written.append(path)

    bundled_ico = _asset_dir() / "secondbrain-app.ico"
    ico_path = target_dir / "app.ico"
    if bundled_ico.is_file():
        ico_path.write_bytes(bundled_ico.read_bytes())
    else:
        # Fallback: rebuild from the PNG sizes we just rendered.
        render_app_icon(256).save(
            ico_path,
            format="ICO",
            sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)],
        )
    written.append(ico_path)

    return written


def _rerender_from_svg(target: Path | None = None) -> int:
    """Re-rasterise the bundled SecondBrain SVGs into ``png/`` assets.

    Build-time helper. Requires ``resvg-py`` (not a runtime dep). Call
    once after updating the master SVGs under ``src/sb_desktop/icons/``.
    """
    import resvg_py  # noqa: PLC0415 — optional build dep

    src_dir = Path(__file__).resolve().parent / "icons"
    out_dir = target or (src_dir / "png")
    out_dir.mkdir(parents=True, exist_ok=True)

    mono = (src_dir / "secondbrain-monogram.svg").read_text(encoding="utf-8")
    for size in _APP_SIZES:
        data = resvg_py.svg_to_bytes(svg_string=mono, width=size, height=size)
        (out_dir / f"secondbrain-monogram-{size}.png").write_bytes(bytes(data))

    fav = (src_dir / "secondbrain-favicon.svg").read_text(encoding="utf-8")
    for size in _FAVICON_SIZES:
        data = resvg_py.svg_to_bytes(svg_string=fav, width=size, height=size)
        (out_dir / f"secondbrain-favicon-{size}.png").write_bytes(bytes(data))

    base = Image.open(out_dir / "secondbrain-monogram-256.png").convert("RGBA")
    base.save(
        out_dir / "secondbrain-app.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return len(_APP_SIZES) + len(_FAVICON_SIZES) + 1


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SecondBrain icon helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_export = sub.add_parser("export", help="Export tray + app PNG/ICO variants")
    p_export.add_argument("--target", type=Path, required=True)
    p_rerender = sub.add_parser("rerender", help="Re-rasterise bundled SVG masters")
    p_rerender.add_argument("--target", type=Path, default=None)

    # Back-compat: accept `--export <dir>` as a flat invocation.
    if argv is None:
        import sys
        argv = sys.argv[1:]
    if argv and argv[0] == "--export" and len(argv) >= 2:
        from sb_desktop import icons as _self  # type: ignore[no-redef]
        paths = _self.export_static_icons(Path(argv[1]))
        for p in paths:
            print(p)
        return 0

    args = parser.parse_args(argv)
    if args.cmd == "export":
        paths = export_static_icons(args.target)
        for p in paths:
            print(p)
        return 0
    if args.cmd == "rerender":
        count = _rerender_from_svg(args.target)
        print(f"Re-rendered {count} assets")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())


# Keep the importlib.resources hook quiet — used in case a future caller
# wants to read the raw SVG masters (eg. wizard "About" panel).
def svg_path(name: str) -> Path:
    """Return the absolute path of one of the bundled SecondBrain SVGs.

    ``name`` is one of: ``"monogram"``, ``"monogram-mono"``, ``"favicon"``,
    ``"lockup-horizontal"``, ``"wordmark"``.
    """
    base = Path(__file__).resolve().parent / "icons"
    return base / f"secondbrain-{name}.svg"


_ = resources  # keep importlib.resources reference for future use
