"""Atomic write helpers — UTF-8 without BOM, LF line endings, rename atomique.

Per core/procedures/_encoding.md and _concurrence.md doctrines:
- All vault files MUST be UTF-8 without BOM.
- Line endings MUST be LF (no CRLF, even on Windows).
- Writes MUST be atomic (write to temp + rename) to survive interrupts.
- Concurrent writes MUST use a hash check (read-before-write Pattern 2).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def hash_content(content: str) -> str:
    """SHA-256 hex of the UTF-8 bytes of content. Used for read-before-write checks."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str | None:
    """Hash the current contents of a file on disk. Returns None if file does not exist."""
    if not path.exists():
        return None
    return hash_content(path.read_text(encoding="utf-8"))


def write_atomic(path: Path, content: str) -> None:
    """Write content to path atomically.

    Steps:
    1. Normalize content to LF line endings.
    2. Ensure parent directory exists.
    3. Write to a temp file in the same directory (so rename is atomic on the
       same filesystem).
    4. os.replace() the temp file onto the target path (atomic on POSIX,
       atomic on Windows since Python 3.3 if target exists).

    Encoding: UTF-8 without BOM. Newline: LF. No trailing newline added beyond
    what content provides — caller controls this.
    """
    # Normalize line endings to LF
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")

    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in the same directory for atomic rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(normalized)
        os.replace(tmp_path, path)
    except Exception:
        # Cleanup temp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_with_hash_check(path: Path, content: str, expected_hash: str | None) -> None:
    """Write atomically only if the current file hash matches expected_hash.

    Prevents lost updates when two MCP sessions modify the same file concurrently.
    expected_hash=None means "the file should not exist yet" (create-only).

    Raises ConcurrentModificationError if the on-disk hash differs from expected.
    """
    current = hash_file(path)
    if current != expected_hash:
        raise ConcurrentModificationError(
            f"File {path} has been modified since the last read "
            f"(expected hash {expected_hash}, found {current}). "
            "Re-read the file before writing."
        )
    write_atomic(path, content)


class ConcurrentModificationError(RuntimeError):
    """Raised when an on-disk hash check fails before a write."""
