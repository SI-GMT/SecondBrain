# Procedure: Health scan (v0.7.3)

Goal: audit the vault for hygiene defects without modifying anything. Produces a structured report under `99-meta/health/scan-{ts}.md` that `mem-health-repair` can later consume to apply fixes. Read-only.

Symptoms covered (one section per category in the report):

- **stray-zone-md** — empty/trivial `{vault}/{NN-zone}.md` files at the vault root, created by Obsidian when the user clicks a dangling wiki-link target named after a zone (pre-v0.7.3 vault root index linked `[20-knowledge](20-knowledge/)` which Obsidian resolved to a non-existent `20-knowledge` note). Safe to delete.
- **empty-md-at-root** — empty/trivial `*.md` files at the vault root that are not `index.md`. Same root cause; broader catch.
- **missing-zone-index** — zones (`00-inbox`, `10-episodes`, etc.) that exist as folders but lack their `{zone}/index.md` hub. Re-asserted by `rebuild-vault-index.py`.
- **missing-display** — files that should carry a `display:` field per `_frontmatter-universal.md` (any `context.md`, `history.md`, archive, transverse atom, topology, root index) but don't. Backfilled by `scripts/inject-display-frontmatter.py`.
- **dangling-wikilinks** — `[[X]]` references whose target file is not present anywhere in the vault. Either the target was removed, was never created (prospective wikilink), or was renamed without a sweep.
- **orphan-atoms** — files in a transverse zone (`40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/`) without a `project:` or `domain:` frontmatter field, AND with no incoming wiki-link from any other vault file. Either reclassified to `00-inbox/` with tag `unlinked-atom` or attached to a project/domain.
- **missing-archeo-hashes** — atoms with `source: archeo-*` whose frontmatter lacks `content_hash` or (for `repo-topology`) `previous_topology_hash`. Repaired by `scripts/inject-archeo-hashes.py`.

## Trigger

The user types `/mem-health-scan` or expresses the intent in natural language: "audit my vault", "check the vault health", "scan the memory for issues", "what's broken in memory?", "find orphans in the vault".

Recognized options:
- `--zones {list}`: restrict the scan to one or more numbered zones (default: all).
- `--only {category}`: restrict to a single check category (e.g., `--only dangling-wikilinks`).
- `--quiet`: suppress per-finding output, only print the summary.
- `--no-write`: do not persist the report file under `99-meta/health/`. Print to stdout only.

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` field. In what follows, `{VAULT}` denotes this value. Read also the `kit_repo` field — needed to locate the auxiliary Python scripts (`inject-display-frontmatter.py`, `validate-archeo-frontmatter.py`).

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Resolve the report path and timestamp

- Timestamp: ISO-like, `YYYY-MM-DD-HHmmss` (matches the existing archive convention).
- Report directory: `{VAULT}/99-meta/health/`. Create if missing.
- Report file: `{VAULT}/99-meta/health/scan-{ts}.md`.

### 2. Run the scan checks

For each category below, build a list of findings. Each finding is `(severity, path-relative-to-vault, message, fix-hint)`. Severities: `info`, `warn`, `error`.

#### 2.1 stray-zone-md

For each numbered zone in `[00-inbox, 10-episodes, 20-knowledge, 30-procedures, 40-principles, 50-goals, 60-people, 70-cognition, 99-meta]`, check whether `{VAULT}/{zone}.md` exists. If it does and (a) its size is 0 OR (b) its non-whitespace content is empty → finding `warn` with fix-hint `delete-stray-zone-md`.

#### 2.2 empty-md-at-root

List `{VAULT}/*.md`. For each file other than `index.md` whose non-whitespace content is empty, finding `warn` with fix-hint `delete-empty-root-md`. (Stray-zone-md is a special case caught earlier — do not double-report.)

#### 2.3 missing-zone-index

For each numbered zone whose folder exists, check that `{VAULT}/{zone}/index.md` exists. Otherwise finding `warn` with fix-hint `recreate-zone-index`.

#### 2.4 missing-display

Scan all `*.md` in the vault outside `00-inbox/` and outside `99-meta/` subfolders (except `99-meta/repo-topology/`). For each file, parse the YAML frontmatter and check whether `display` is present and non-empty.

If a file should carry `display:` per `_frontmatter-universal.md` (any `context.md`, `history.md`, archive under `*/archives/*.md`, transverse atom under `40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/`, topology under `99-meta/repo-topology/*.md`, root `index.md`, zone hub `*/index.md`) and lacks the field → finding `info` with fix-hint `inject-display`.

#### 2.5 dangling-wikilinks

Scan all `*.md` outside `.obsidian/` and outside backup files. Extract every `[[X]]` (skip image embeds `![[X]]`, skip code-fenced blocks). For each link target, resolve it against the vault file index (a target may match either a basename without extension, or a relative path). If unresolved, finding `info` with fix-hint `manual-review` (these are often prospective links the user wants to keep).

Skip (do not report) wikilinks that point to:
- `index` (vault root)
- A zone hub like `20-knowledge/index` or `99-meta/repo-topology/{slug}` (these are now real files in v0.7.3 — but if for some reason they are missing, the missing-zone-index check above already covers it).

#### 2.6 orphan-atoms

For each `*.md` under `40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/`:

- Parse frontmatter. If neither `project:` nor `domain:` is set, the atom is candidate-orphan.
- For each candidate, count incoming wiki-links from other vault files (basename match suffices). If the count is zero → finding `warn` with fix-hint `reclassify-to-inbox`.

Atoms attached to a project/domain that no longer exists (folder absent under `10-episodes/projects/{slug}/` or `10-episodes/domains/{slug}/`) → also finding `warn` with fix-hint `reclassify-to-inbox` and message `"orphan because target {project|domain} '{slug}' no longer exists"`.

#### 2.7 missing-archeo-hashes

For each `*.md` whose frontmatter has `source:` starting with `archeo-` (`archeo-context`, `archeo-stack`, `archeo-git`, `archeo-atlassian`):

- If `content_hash` is missing or empty → finding `warn` with fix-hint `inject-archeo-hashes`.
- For `99-meta/repo-topology/*.md` only, also check `previous_topology_hash` (may be empty string for the first snapshot — that's fine; missing entirely is the bug).

### 3. Emit the report

The report file uses the standard meta-frontmatter:

```yaml
---
date: {YYYY-MM-DD}
zone: meta
type: health-scan
display: "vault health scan {ts}"
tags: [zone/meta, type/health-scan]
scan_timestamp: {ts}
vault_path: "{VAULT}"
findings_count_total: {N}
findings_by_severity:
  info: {N}
  warn: {N}
  error: {N}
findings_by_category:
  stray-zone-md: {N}
  empty-md-at-root: {N}
  missing-zone-index: {N}
  missing-display: {N}
  dangling-wikilinks: {N}
  orphan-atoms: {N}
  missing-archeo-hashes: {N}
---
```

Body — one section per category that has at least one finding. Empty categories are omitted entirely.

```markdown
# Vault health scan — {ts}

> Read-only audit. Run `/mem-health-repair` to apply the suggested fixes.
> Linked from [[index|vault index]].

## Summary

- **Total findings**: {N} ({E} errors, {W} warnings, {I} info)
- **Vault**: `{VAULT}`
- **Scan started**: {ts}
- **Scope**: all zones (or `--zones X,Y` if restricted)

## stray-zone-md ({N} finding(s))

| Severity | File | Message | Fix |
|---|---|---|---|
| warn | `20-knowledge.md` | empty MD at root, named after zone `20-knowledge` | delete-stray-zone-md |
| ... | ... | ... | ... |

## empty-md-at-root ({N})

(table)

## missing-zone-index ({N})

(table)

(... etc, one section per category ...)
```

Atomic write UTF-8 / LF (use `.tmp` + rename).

### 4. Reply to the user

Print a short summary in their conversational language:

```
✓ Vault health scan completed.

  Total findings : {N} ({E} errors, {W} warnings, {I} info)
  Top categories : {category-1} ({N1}), {category-2} ({N2}), ...

  Report : 99-meta/health/scan-{ts}.md

Run /mem-health-repair to apply the safe fixes (delete stray MDs, create
missing zone indexes, inject missing display fields, inject missing archeo
hashes). Orphan atoms and dangling wikilinks require manual review.
```

If `--no-write` was passed, replace the "Report" line with `(report not persisted, --no-write was set)`.

## Index linking

Add a top-level entry to `{VAULT}/index.md` under a `## Health` section if any health report exists. Format:
- `[scan-{ts}](99-meta/health/scan-{ts}.md) — {N} finding(s)`

If a `## Health` section is absent, append it before the first existing section that comes alphabetically after "Health" — or at the end if none. Idempotent: same-day rescans append a new line, do not replace previous ones.

(`rebuild-vault-index.py` does not yet aggregate this section — that's a follow-up. For now the writing skill manages it directly.)

## Empty vault / nothing to report

If the scan finds zero issues across all categories:

```
✓ Vault is clean. No findings.
```

Still write the report file (with `findings_count_total: 0` and only the Summary section) so there is a baseline to compare future scans against.

## Escape hatch

If any check raises an unexpected error (corrupt frontmatter, encoding issue), log the file path + error in a final `## Scan errors` section of the report and continue with the other checks. Never abort the whole scan because one file fails to parse.
