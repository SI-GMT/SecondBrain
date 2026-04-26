---
description: Archive the current work session into the memory vault so it can be resumed later via /mem-recall. Use this skill in TWO distinct situations. (1) FULL MODE, end of session — trigger when the user says 'we're stopping', 'I'm leaving', 'we're done', types /clear or /mem-archive, or explicitly asks to archive. Then execute the full procedure (timestamped archive file + rewrite of context.md + update of history.md + update of index.md). (2) SILENT INCREMENTAL MODE, during the session — as soon as a fact, decision, or important next step emerges AND is not already in context.md, update ONLY context.md without creating an archive or announcing the action to the user. Never create a full archive in silent mode: it would pollute the history.
---

{{PROCEDURE}}

## User input

```text
$ARGUMENTS
```
