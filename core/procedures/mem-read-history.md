# Procedure: `mem-read-history` (v0.9.3)

Goal: surface the raw `history.md` of a project or domain (chronological session log) without aggregation. Returns the list as-is, one bullet per archived session.

## When to invoke

- The user asks for "the chronological log of `{slug}`" or "list the sessions of `{slug}`".
- A digest aggregator wants the raw input before synthesising (use `mem-digest` for the synthesised version).
- A hygiene task wants to verify the format / count of session entries.

## Arguments

- `slug` (required) — project or domain slug.

## Behaviour

1. Resolve `slug` via `paths.resolve_slug`. Works on active, domain, and archived locations.
2. Read `{folder}/history.md` via `vault.frontmatter.read`.
3. Count session entries (lines starting with `- [`) for the summary.
4. Return a `VaultReadResult` with `kind="history"`, frontmatter, raw body, and a summary noting the entry count + body length.

## Doctrinal notes

- **Read-only**.
- **Use `mem-digest` for synthesis** — `mem-read-history` is intentionally raw; it does no aggregation, no narrative.
- **`FileNotFoundError` on missing `history.md`** — points to `mem-init-project` (bootstrap) or `mem-archive` (populate).

## Encoding

UTF-8 without BOM.
