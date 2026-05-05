# Procedure: `mem-get-topology` (v0.9.3)

Goal: surface the persisted topology snapshot of a project (`99-meta/repo-topology/{slug}.md`) without re-scanning the repository. Useful for LLM-driven tasks (Phase 1 archeo semantic analysis, BrainyAgent contextual reasoning, hygiene audits) that want the topology metadata without the cost of a fresh `vault.topology_scanner.scan()` call.

## When to invoke

- A `mem-archeo-context` skill (Phase 1, LLM-driven) needs the file categories, stack hints, and workspace info without re-walking the repo.
- The LLM wants to answer "what's the stack of `{project}`?" or "what AI files does `{project}` carry?" from cached topology rather than triggering a scan.
- A digest / analytics workflow that consults topology for many projects in sequence — re-scanning each would be wasteful.

## Arguments

- `project` (required) — project slug.

## Behaviour

1. Resolve `paths.topology_file(vault, project)` → `{vault}/99-meta/repo-topology/{slug}.md`.
2. If absent: return `TopologyReadResult(exists=False, ...)` with a summary recommending `mem-archeo` / `mem-archeo-stack` to populate. **No exception** — this is a normal case for projects that were never archeo'd.
3. If present: read frontmatter + body via `vault.frontmatter.read`. Surface `repo_path`, `repo_remote`, `content_hash`, `last_archive` as dedicated fields for easy access alongside the full frontmatter dict.

## Doctrinal notes

- **Read-only**.
- **Stale-tolerant by design** — the topology snapshot can be hours, days, or weeks old. The caller is expected to know whether it needs a fresh scan (then call `mem-archeo` instead) or accepts the cached version.
- **`exists=False` is not an error** — the caller decides whether to trigger a scan or fall back. This contrasts with `mem-read-context` which raises on missing file (because a project without context.md is broken; a project without topology is just one that was never archeo'd).

## Encoding

UTF-8 without BOM.
