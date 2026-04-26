---
description: "Reconstruct the history of an existing Git repo as multiple dated archives in the memory vault (1 archive per tag, release, merge, or commit window). AUTO-TRIGGER (without waiting for /mem-archeo) when the user says — 'do a Git retro of this project', 'reconstruct the history of this repo', 'archeo on this repo', 'analyze the version tags and archive them'. Also invocable via /mem-archeo [repo-path] with options --level, --project, --since, --until, --window, --dry-run. Auto-detects granularity (tags → releases → merges → commit windows) with interactive confirmation before writing. Idempotent: skips archives already created for the same milestone. Never overwrites a lived archive."
---

{{PROCEDURE}}

## User input

```text
$ARGUMENTS
```
