"""Shared console-encoding helper.

Default Python on Windows uses cp1252 for stdout/stderr, which crashes on any
character outside that codepage (``→``, accented French in error messages,
arrows in trace output, etc.). Reconfiguring at process entry — supported
since Python 3.7 — with ``errors='replace'`` makes unexpected characters
degrade to ``?`` rather than raise ``UnicodeEncodeError`` and bring the
process down.

No-op on systems already running UTF-8. Best-effort: if ``reconfigure`` is
not available (older Python, piped through a wrapper that strips it), the
helper falls through silently rather than masking the actual failure.

Used by every console entry point of the package:

- ``server.py`` (the MCP server, stderr is the log channel for clients)
- ``migrate.py`` (``memory-kit-migrate`` CLI)
- ``archeo_topology.py`` (``archeo-topology`` CLI)

When adding a new entry point, call :func:`force_utf8_console` as the first
statement of ``main()``.
"""

from __future__ import annotations

import sys


def force_utf8_console() -> None:
    """Reconfigure stdout and stderr to UTF-8 with replacement on errors."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
