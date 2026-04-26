## Atomic writes and protection against concurrent access

The vault may experience concurrent access — two parallel LLM sessions (e.g., Claude Code + Codex), or an LLM session writing while Obsidian manually edits the same file. Without protection, last-write-wins corrupts or loses entries.

### Pattern 1 — Atomic rename (for all writes)

Every file written or rewritten follows this sequence:

1. Write the new content to `{file}.tmp` (same directory as the target).
2. Atomic rename `{file}.tmp` → `{file}`. On POSIX, `rename()` is atomic and silently replaces. On Windows, `Move-Item -Force` (PowerShell) or equivalent (`MoveFileEx` with `MOVEFILE_REPLACE_EXISTING`).
3. If the rename fails, delete the `.tmp` and surface the error to the user.

Concrete commands:

| Shell | Sequence |
|---|---|
| bash / POSIX | `printf '%s' "$content" > "$target.tmp" && mv -f "$target.tmp" "$target"` |
| PowerShell 7+ | `Set-Content -Path "$target.tmp" -Value $content -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$target.tmp" -Destination $target -Force` |
| Python | `Path(f"{target}.tmp").write_text(content, encoding='utf-8', newline=''); Path(f"{target}.tmp").replace(target)` (`replace` is atomic cross-platform) |

### Pattern 2 — Hash check read-before-write (for shared files)

Shared files (modifiable by multiple procedures or by Obsidian in parallel — typically `index.md`, `history.md`, `context.md`) require a hash check before any rewrite:

1. **Operation start**: read the file, compute its SHA-256, store it (`hash_initial`).
2. **Just before writing**: re-read the target file, recompute its SHA-256 (`hash_before`).
3. If `hash_before != hash_initial` → the file was modified meanwhile by another actor. **Do not overwrite**. Re-read the current content, merge the changes you wanted to apply, then resume at step 2 (loop up to 3 attempts).
4. If `hash_before == hash_initial` → proceed with atomic rename (pattern 1).
5. If after 3 attempts the hash keeps diverging → stop, display a warning to the user: "File `{target}` modified by an external actor during the operation. Check manually, then re-run the command."

**Timestamped and new** files (typically archives under `archives/` or under `{zone}/{...}/archives/`) are exempt from the hash check: no conflict possible on a unique name. But they must still use atomic rename (pattern 1).

### Known limit

These patterns strongly reduce the race window but do not eliminate it completely. A race remains theoretically possible between computing `hash_before` and the rename. For strict protection, the memory-kit MCP (Phase 3) will use an application-level lock via `asyncio.Lock`.
