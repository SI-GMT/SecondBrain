"""Shared test doubles emulating ``memory_kit_mcp`` internals.

The desktop tests must not depend on the actual kit being importable in
the test environment — they mock the imports at the call sites where
``sb_desktop`` reaches into ``memory_kit_mcp.*``. These fakes mirror just
enough of the kit's public surface to drive the desktop logic
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeFinding:
    category: str
    severity: str = "info"
    path: str = "a.md"
    message: str = ""
    auto_fixable: bool = False


@dataclass
class FakeUpdateInfo:
    current_version: str = "0.12.1"
    latest_version: str | None = "0.13.0"
    update_available: bool = True
    last_checked: float = 0.0
    error: str | None = None
