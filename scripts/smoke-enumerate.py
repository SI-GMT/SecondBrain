"""Direct timing of enumerate_files() — no MCP, no Gemini, no transport.

Usage:
    mcp-server\.venv\Scripts\python.exe scripts\smoke-enumerate.py [repo_path]

Default repo_path: C:/_PROJETS/IRIS/PROD/USER (the case study repo).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from memory_kit_mcp.archeo import enumerate_files

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/_PROJETS/IRIS/PROD/USER")
print(f"repo = {repo}")

t0 = time.perf_counter()
r = enumerate_files(repo)
elapsed = time.perf_counter() - t0

print(f"enumerate_files: {elapsed:.2f}s")
print(f"  files       : {r.files_count}")
print(f"  bytes       : {r.files_bytes // 1024} KiB")
print(f"  source_mode : {r.source_mode}")
print(f"  warnings    : {len(r.warnings)}")
for w in r.warnings:
    print(f"    - {w}")
print("trace:")
for line in r.trace:
    print(f"  {line}")
