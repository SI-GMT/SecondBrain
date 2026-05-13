"""SecondBrain Desktop — systray companion for the Memory Kit MCP server.

Thin consumer of the existing ``memory-kit-mcp`` engine. All heavy lifting
(vault audit, repair, version probe, deploy) is delegated to the engine via
subprocess; this package only orchestrates the user-facing surface.

Version resolution order:

1. ``sb_desktop._version`` — a generated file written at build time by
   ``build/build_windows.ps1`` from the canonical ``pyproject.toml``
   value. This is the authoritative source inside a PyInstaller bundle
   because the frozen .exe has no live access to ``pyproject.toml``
   and ``importlib.metadata`` can read a stale ``.dist-info`` left
   behind by a previous install on the same machine.
2. ``importlib.metadata.version("sb-desktop")`` — works for editable
   ``pip install -e .`` development checkouts where the wheel metadata
   tracks the current source. Fragile inside frozen bundles when an
   older install exists in user site-packages, hence the priority of
   step 1.
3. ``0.0.0+unknown`` as the universal fallback.

The generated ``_version.py`` is gitignored so dev checkouts always
flow through path 2; the file appears only inside a built bundle.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    from sb_desktop._version import __version__ as _baked_version  # type: ignore[import-not-found]

    __version__ = _baked_version
except ImportError:
    try:
        __version__ = version("sb-desktop")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
