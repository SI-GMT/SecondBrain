# Procedure: Archeo Atlassian (v0.5 brain-centric)

Goal: **retro-archive a Confluence tree** (root page + descendants, or full space) with enrichment from referenced Jira tickets. Delegates to the router for segmentation into multi-zone atoms.

**Prerequisite: client-side Atlassian MCP.** Claude-only de facto (Atlassian has not shipped a proper MCP connector for Gemini/Codex/Vibe to date). If invoked from a client without Atlassian MCP, display a clear message and stop.

## Trigger

The user types `/mem-archeo-atlassian {confluence-url}` or expresses intent in natural language: "archive this Confluence page and its children", "Atlassian retro on this space", "ingest this Confluence doc".

Arguments:
- `{confluence-url}` (**required**): URL of a Confluence page or space.
- `--project {slug}` or `--domain {slug}`: forces attachment.
- `--depth N`: limits descendants (default unlimited).
- `--skip-children`: ingests only the root page.
- `--since YYYY-MM-DD`: only processes pages updated after this date.
- `--skip-jira`: disables enrichment from Jira tickets.
- `--dry-run`: lists pages that would be processed without writing.
- `--no-confirm`: passes through to the router in fluent mode.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Atlassian MCP check

Before any processing, verify Atlassian MCP availability on the client side. If unavailable, display:

> Skill `/mem-archeo-atlassian` unavailable: Atlassian MCP not detected.
> This skill requires the Atlassian MCP connector, currently only available on the Claude side (Desktop / Code). See Atlassian documentation for installation.

Then stop.

## Procedure

### 1. Identify scope (single page, page+descendants, space)

Parse the URL to extract:
- `space_key`
- `page_id` (if URL points to a page) or `null` (if URL points to a space root).

Mode:
- URL = page + no `--skip-children` → page + descendants.
- URL = page + `--skip-children` → page only.
- URL = space root → full space.

### 2. Enumerate the pages to process

Via the Atlassian MCP, list pages:
- Single page: 1 page.
- Page + descendants: root page + recursion via `child_of` up to `--depth` or exhaustion.
- Space: full `pages_by_space`.

Filter by `--since` if provided (`updated_at >= since`).

### 3. Resolve the target project/domain

Same as `mem-archeo` step 2.

### 4. For each page: prepare the content

#### a. Verify idempotence

Search the vault for an existing atom with:
- `source: archeo-atlassian`
- matching `confluence_page_id`.
- matching `confluence_updated`.

If found → skip.
If found but `confluence_updated` differs → create a new archive with `previous_atom: [[old]]` (immutability).

#### b. Retrieve the page content

Via Atlassian MCP, retrieve:
- Title, body (Markdown or storage format converted to MD), author, creation/update date.
- Labels, space.
- Inbound / outbound links.

#### c. Jira enrichment (if not `--skip-jira`)

Extract Jira keys (regex `[A-Z]+-\d+`) from the page content. For each key:
- Via Atlassian MCP, retrieve: ticket title, status, assignee, sprint, type.
- Insert an enriched mention into the atom content.

#### d. Build the content for the router

Prepare a structured Markdown, similar to `mem-archeo`:

```
# Confluence page archive — {title}

[Page content, source: confluence]

## Principle: ... [if extracted from content]
## Concept: ... [if extracted from content]
```

### 5. Invoke the router for this page

Call the router with:
- `Content`: structured Markdown.
- `Hint zone`: `episodes` (default, but the router can route certain doctrinal pages to `20-knowledge` based on nature).
- `Hint source`: `archeo-atlassian`.
- `Metadata`: project/domain, **`confluence_page_id`**, **`confluence_updated`**, `confluence_url`, `space_key`, `jira_keys: [...]`.

{{INCLUDE _router}}

### 6. Loop over all pages

If `--dry-run`: display the list of pages + planned atoms. Ask for confirmation.

Otherwise: iterate. Safe mode by default unless `--no-confirm`.

### 7. Final report

Synthesis: N pages processed, N archives created, N derived atoms, N skips (idempotence), N revisions, N Jira tickets enriched.
