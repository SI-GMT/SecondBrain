# Procedure: `mem-read-context` (v0.9.3)

Goal: surface the raw `context.md` of a project or domain (frontmatter + body) without going through `mem-recall`'s full briefing synthesis. Lighter-weight alternative when the LLM only needs the current snapshot (phase, decisions, next steps) — not the assembled list of active principles, open goals, key people, topology hash, etc.

## When to invoke

- The user asks "what's the current phase of `{slug}`?" or "show me the context of `{slug}`" without wanting the full briefing.
- An automated pipeline (audit, digest aggregator, BrainyAgent analytics) wants to inspect just the context without the recall overhead.
- A migration / hygiene task that needs to read the raw frontmatter for validation.

## Arguments

- `slug` (required) — project or domain slug.

## Behaviour

1. Resolve `slug` via `paths.resolve_slug`. Works on active projects, domains, and archived projects (read-only is allowed by `_archived.md`).
2. Read `{folder}/context.md` via `vault.frontmatter.read`.
3. Return a `VaultReadResult` with `kind="context"`, parsed frontmatter, raw body, and a summary surfacing the phase, last session, and body length.

## Doctrinal notes

- **Read-only**.
- **Use `mem-recall` instead** when the goal is to brief the LLM for a session — `mem-recall` does the synthesis (active principles, open goals, etc.) which `mem-read-context` deliberately skips.
- **`FileNotFoundError` on missing `context.md`** — points the user to `mem-init-project` (bootstrap) or `mem-archive` (populate) as remediation.

## Encoding

UTF-8 without BOM.
