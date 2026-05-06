"""memory-kit-mcp — Persistent Markdown vault MCP server for SecondBrain."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("memory-kit-mcp")
except PackageNotFoundError:
    # Source tree without an installed package (e.g. early dev tree).
    __version__ = "0.0.0+unknown"
