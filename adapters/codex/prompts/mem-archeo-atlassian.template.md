---
description: Retro-archive a Confluence page tree (root page + descendants, or a full space) into the memory vault, with automatic enrichment from the Jira tickets referenced in the pages. AUTO-TRIGGER (without waiting for /mem-archeo-atlassian) when the user says — 'archive the Confluence documentation of this project', 'do a retro on this Atlassian space', 'ingest this page and its children', 'archive this doc and the linked tickets'. Also invocable via /mem-archeo-atlassian {url} with options --depth, --skip-children, --since, --skip-jira, --project, --dry-run. Requires the Atlassian MCP on the client side. 1 archive per Confluence page, with content converted to Markdown + summary of each Jira ticket mentioned. Idempotent (skips pages already archived up-to-date via confluence_page_id + confluence_updated). Frontmatter source=archeo-atlassian.
---

{{PROCEDURE}}

## User input

```text
$ARGUMENTS
```
