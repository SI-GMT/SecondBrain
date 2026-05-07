"""Archeo v2 shared library — shell-delegated, deterministic, scope-bounded.

See ``core/procedures/_archeo-architecture-v2.md`` for the full doctrine.
This package replaces the v1 in-Python recursive scan (``vault.topology_scanner``)
with system-delegated enumeration via ``git`` (versioned mode) or
``os.scandir`` + a hard ignore-list (raw mode).
"""

from memory_kit_mcp.archeo.topology import (
    BATCH_SIZE_DEFAULT,
    DEFAULT_IGNORE_DIRS,
    DEFAULT_IGNORE_SUFFIXES,
    SOFT_CAP_BYTES_DEFAULT,
    SOFT_CAP_FILES_DEFAULT,
    EnumerateResult,
    ScopeOverflowError,
    detect_mode,
    enumerate_files,
)

__all__ = [
    "BATCH_SIZE_DEFAULT",
    "DEFAULT_IGNORE_DIRS",
    "DEFAULT_IGNORE_SUFFIXES",
    "EnumerateResult",
    "ScopeOverflowError",
    "SOFT_CAP_BYTES_DEFAULT",
    "SOFT_CAP_FILES_DEFAULT",
    "detect_mode",
    "enumerate_files",
]
