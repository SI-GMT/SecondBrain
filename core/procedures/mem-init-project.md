# Procedure: `mem-init-project` (v0.9.3)

Goal: bootstrap an **empty** project or domain folder in the vault so that subsequent `mem-archive` calls can write to it without raising `FileNotFoundError`. Closes the UX gap exposed by Codex (and any MCP-only CLI client) when the LLM tries to archive a session for a slug that has not been initialised yet.

## When to invoke

The user expresses one of:

- "Initialise / bootstrap / créer le projet `{slug}`"
- "Add a new project `{slug}` to the vault"
- "I want to start tracking sessions on `{slug}` (not in the vault yet)"

Or — most commonly — the LLM gets back a `FileNotFoundError` from `mem-archive` mentioning that the slug does not exist, and infers that `mem-init-project` is the right preparatory step.

## Arguments

- `slug` (required) — kebab-case identifier for the project or domain.
- `kind` (`project` | `domain`, default `project`) — `project` for active sessions, `domain` for cross-project transverse atoms (cf. `_archived.md` doctrine).
- `scope` (`work` | `personal`, default `work`) — frontmatter scope tag.
- `display` (optional) — human-readable display name (defaults to capitalised slug).
- `repo_path` (optional) — absolute path of the associated Git repo if any. Sets `repo_path` in the `context.md` frontmatter so future `mem-archeo` runs can find it without re-detection.

## Behaviour

1. Validate that `slug` is non-empty and contains no path separators or `..` (defensive — no traversal).
2. Resolve the slug via `paths.resolve_slug` across active projects, domains, and archived locations. **If found anywhere, refuse with `FileExistsError`** — opt-in creation only, no overwrite.
3. Choose the destination folder per `kind`:
   - `project` → `{vault}/10-episodes/projects/{slug}/`
   - `domain` → `{vault}/10-episodes/domains/{slug}/`
4. Create the folder + `archives/` subfolder + `archives/.gitkeep` (so the folder is preserved in git for new projects).
5. Write `context.md` with the universal frontmatter (`zone`, `kind`, `slug`, `scope`, `phase: initial`, `last-session: today`, `display`, optional `repo_path` + empty `workspace_member`) and a minimal body (intro line cross-linking to `history.md` + skeleton sections for state / decisions / next steps / assets).
6. Write `history.md` with universal frontmatter and intro line cross-linking to `context.md`.
7. Return a `ChangeReport` listing the 3 files created.

## Doctrinal notes

- **No write to `index.md` global** — that's the responsibility of `mem_archive` (which appends naturally on the first archive) or `scripts/rebuild-vault-index.py`. Keeps `mem-init-project` strictly local to the project folder.
- **Idempotence by refusal** — calling twice on the same slug raises rather than silently overwriting. Forces the user to confirm a typo and pick a different slug.
- **No archive yet** — the freshly created `history.md` will say `"(no sessions yet)"` until the first `mem_archive` call.
- **Bootstrap order** — typical flow: `mem-init-project` → first `mem-archive` (which prepends a session line and bootstraps `index.md` global). Don't skip step 1 hoping `mem-archive` will create the folder; it won't (defensive check).

## Output expected

```
**mem_init_project** — created project `{slug}` (work, display = '{Display}')

- 10-episodes/projects/{slug}/context.md
- 10-episodes/projects/{slug}/history.md
- 10-episodes/projects/{slug}/archives/.gitkeep

Run `mem_archive` on `{slug}` to start tracking sessions.
```

## Encoding

UTF-8 without BOM, LF line endings — same as every other vault write.
