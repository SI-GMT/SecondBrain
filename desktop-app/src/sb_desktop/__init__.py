"""SecondBrain Desktop — systray companion for the Memory Kit MCP server.

Thin consumer of the existing ``memory-kit-mcp`` engine. All heavy lifting
(vault audit, repair, version probe, deploy) is delegated to the engine via
subprocess; this package only orchestrates the user-facing surface.

The runtime version is resolved dynamically from the installed distribution
metadata so deploy / installer artifacts never embed a stale string.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sb-desktop")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
