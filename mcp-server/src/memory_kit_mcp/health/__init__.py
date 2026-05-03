"""Vault hygiene audit — shared library.

The 8-category scan logic used by:
- tools.health_scan.mem_health_scan (MCP tool wrapper)
- scripts/mem-health-scan.py (versioned standalone CLI; maintains its own
  copy by deliberate decoupling — see CLAUDE.md "Discipline de cohérence
  scripts/mem-health-scan.py ↔ memory_kit_mcp.health.scan").
"""

from memory_kit_mcp.health.scan import (
    CATEGORIES,
    ZONES,
    scan_vault,
)

__all__ = ["CATEGORIES", "ZONES", "scan_vault"]
