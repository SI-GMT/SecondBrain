# Procedure: `mem-read-archive` (v0.9.3)

Goal: surface the full content (frontmatter + body) of a single archive file by its filename. Bridges the gap for MCP-only CLI clients (Codex, Vibe, Gemini in pure MCP mode) which don't have direct filesystem access — those LLMs need a vault-native way to fetch an archive's full text after `mem-recall` lists them.

## When to invoke

- The user asks for the details of a specific archive named in a previous `mem-recall` / `mem-list` / `mem-search` reply (e.g. "donne-moi les détails de l'archive `2026-04-22-15h21-...`").
- The LLM wants to traverse a citation chain: an archive references `previous_atom` or a `derived_atoms` wikilink — fetching the target's full text is needed for the response.
- An audit / digest workflow that wants to inspect each archive end-to-end without using `mem-search` per topic.

## Arguments

- `slug` (required) — project or domain slug owning the archive.
- `filename` (required) — archive filename. The `.md` suffix is optional; if missing, it's added automatically.

## Behaviour

1. Resolve `slug` via `paths.resolve_slug` across active projects, domains, and archived locations (the `_archived.md` doctrine still allows reads from archived projects).
2. Defensive: refuse if `filename` contains `/`, `\`, or `..` — no traversal.
3. Resolve `archives_dir / filename`. If missing, raise `FileNotFoundError` with up to 10 closest filenames as suggestions to help the LLM correct itself.
4. Read frontmatter + body via `vault.frontmatter.read`.
5. Return a `VaultReadResult` with `kind="archive"`, the parsed frontmatter, the raw body, and a summary listing the frontmatter keys + body length.

## Doctrinal notes

- **Read-only** — no writes anywhere. Archives are immutable per the v0.5 doctrine; `mem-read-archive` honours that strictly.
- **Archived projects readable** — per `_archived.md`, archived projects accept reads but not writes. This tool reads, so works on both active and archived.
- **No filtering / synthesis** — the body is returned verbatim. Use `mem-digest` for a synthesised narrative across multiple archives, or `mem-search` to find specific text.

## Encoding

UTF-8 without BOM. The tool reads the file as UTF-8; if the file was written by a non-conforming process (rare), the read will surface a `UnicodeDecodeError` which the caller should treat as a hygiene finding.
