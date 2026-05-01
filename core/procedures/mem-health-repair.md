# Procedure: Health repair (v0.7.3)

Goal: apply safe, idempotent fixes to the hygiene defects detected by `mem-health-scan`. Dry-run by default — no write to the vault unless `--apply` is passed.

Scope of repairable categories:

- **stray-zone-md** → delete the empty MD at vault root (verified empty before deletion).
- **empty-md-at-root** → delete the empty MD at vault root.
- **missing-zone-index** → invoke `rebuild-vault-index.py` which re-creates them.
- **missing-display** → invoke `scripts/inject-display-frontmatter.py --apply`.
- **missing-archeo-hashes** → invoke `scripts/inject-archeo-hashes.py --apply`.
- **dangling-wikilinks** → manual review (not automated). Reported and skipped.
- **orphan-atoms** → semi-automated: prompt user per-orphan to either reclassify into `00-inbox/` (with tag `unlinked-atom`) or attach to a project/domain.

## Trigger

The user types `/mem-health-repair` or expresses the intent in natural language: "fix the vault", "repair memory health", "apply health fixes", "clean up the vault", "defrag memory" (the user uses "defrag" generically — full defrag of redundant atoms is out-of-scope for v0.7.3, see `mem-health-defrag` cadrage).

Recognized options:
- `--apply`: actually perform the fixes. Without this flag, only print the planned operations.
- `--from-report {path}`: apply the fixes recommended by an existing report instead of rescanning. Default: rescan in-process.
- `--only {category}`: restrict to a single repair category (e.g., `--only stray-zone-md`).
- `--no-orphans`: skip orphan-atoms (avoids the interactive prompts when running in batch mode).
- `--no-confirm`: do not prompt for confirmation before each fix; print + execute. Combine with `--apply`.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `kit_repo`. In what follows, `{VAULT}` is the vault path, `{KIT}` the kit repo path.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Source the findings

If `--from-report {path}` is provided, parse the YAML frontmatter + the per-category tables. Otherwise, run `mem-health-scan --no-write --quiet` in-process (no report file written) and use those findings.

If the scan returns zero findings:
```
✓ Nothing to repair.
```
Stop.

### 2. Plan the fixes

Build a fix-plan grouped by category. For each category, list the concrete operations:

#### 2.1 stray-zone-md / empty-md-at-root

```
DELETE  {VAULT}/20-knowledge.md   (size: 0 bytes)
DELETE  {VAULT}/{other}.md         (size: 0 bytes)
```

Pre-flight check before each delete (mandatory): re-stat the file and confirm size is 0 OR content is whitespace-only. If a file has been written to since the scan, skip it with a warning.

#### 2.2 missing-zone-index

```
INVOKE  python {KIT}/scripts/rebuild-vault-index.py --vault {VAULT}
        # creates missing {zone}/index.md hubs idempotently
        # (also rebuilds the root index.md — that's intended)
```

Single invocation regardless of how many zone indexes are missing — `rebuild-vault-index.py` handles them all in one go.

#### 2.3 missing-display

```
INVOKE  python {KIT}/scripts/inject-display-frontmatter.py --vault {VAULT} --apply
        # backfills display: into files that should carry it but don't
```

If the `--apply` flag is **not** passed at the `mem-health-repair` level, drop the `--apply` from the inner script call (= run it dry-run too).

#### 2.4 missing-archeo-hashes

```
INVOKE  python {KIT}/scripts/inject-archeo-hashes.py --vault {VAULT} --apply
```

Same `--apply` propagation rule.

#### 2.5 dangling-wikilinks

Skipped automatically (manual category). Print a one-line note:
```
SKIP    dangling-wikilinks ({N} findings) — manual review required.
        See report {report-path-if-known}.
```

#### 2.6 orphan-atoms

If `--no-orphans` is set, print:
```
SKIP    orphan-atoms ({N} findings) — --no-orphans was set.
```

Otherwise, for each orphan, prompt the user:
```
ORPHAN  40-principles/work/methodology/foo.md
        No project/domain attached, zero incoming wikilinks.

        [r]eclassify to 00-inbox/ (tag: unlinked-atom)
        [a]ttach to project — provide slug:
        [s]kip this one
        [q]uit orphan handling
```

Behaviour:
- `r` → move file to `{VAULT}/00-inbox/{basename}` (preserve frontmatter, ADD tag `unlinked-atom` and `migration-v0.7.3-orphan`, set `zone: inbox`). Use atomic rename (`.tmp` + replace).
- `a {slug}` → patch frontmatter `project: {slug}` (verify the project folder exists first under `10-episodes/projects/{slug}/`).
- `s` → skip, print `SKIP {path}`.
- `q` → break out of the orphan loop; remaining categories still run.

### 3. Confirm and execute

Print the full plan. If `--no-confirm` is not set:

```
Plan summary:
  DELETE         : {N} stray/empty MD(s) at vault root
  REBUILD INDEX  : 1 invocation (creates {N} missing zone indexes)
  INJECT DISPLAY : 1 invocation (~{N} files patched, dry-run preview before apply)
  INJECT HASHES  : 1 invocation (~{N} archeo atoms patched)
  ORPHAN PROMPT  : {N} interactive prompt(s)
  SKIPPED        : {N} dangling wikilinks (manual review)

Apply? [y/N]
```

Without `--apply`, replace the prompt with `(dry-run, --apply not passed; nothing will be written)` and stop.

With `--apply` and confirmation accepted (or `--no-confirm`), execute each operation in order. Surface per-operation success/failure.

### 4. Emit a repair report

After execution, append a sibling report to the scan one:

`{VAULT}/99-meta/health/repair-{ts}.md`

```yaml
---
date: {YYYY-MM-DD}
zone: meta
type: health-repair
display: "vault health repair {ts}"
tags: [zone/meta, type/health-repair]
repair_timestamp: {ts}
source_scan: "{path-to-scan-report-if-applicable}"
applied: {true|false}
operations_total: {N}
operations_succeeded: {N}
operations_failed: {N}
operations_skipped: {N}
---

# Vault health repair — {ts}

> Linked from [[index|vault index]] and from [[scan-{ts}|its source scan]] when known.

## Operations

| Status | Operation | Target | Note |
|---|---|---|---|
| ok    | DELETE     | `20-knowledge.md`              | size was 0 |
| ok    | INVOKE     | `rebuild-vault-index.py`       | created 9 zone indexes |
| ok    | INVOKE     | `inject-display-frontmatter.py`| 12 files patched |
| skip  | DELETE     | `weird-stray.md`               | size > 0 since scan, refused |
| ...   | ...        | ...                            | ... |

## Skipped categories

- dangling-wikilinks ({N}) — manual review
- orphan-atoms ({N}) — --no-orphans was set
```

Atomic write. Update `{VAULT}/index.md` `## Health` section with a new line:
- `[repair-{ts}](99-meta/health/repair-{ts}.md) — {N} operation(s){'  (DRY-RUN)' if not applied}`

### 5. Reply to the user

```
✓ Vault health repair {applied|simulated}.

  {N} operation(s) total:
    ok      : {N}
    skipped : {N}
    failed  : {N}

  Report : 99-meta/health/repair-{ts}.md
```

If failures > 0, also print the first failure path + message inline.

## Safety guarantees

1. **Dry-run is the default.** Never delete or patch without `--apply`.
2. **Empty-file pre-flight before delete.** Re-check size/content immediately before unlinking. If non-empty → skip with `[skip] {path} not empty since scan`.
3. **Backup convention for invoked scripts.** `inject-display-frontmatter.py` and `inject-archeo-hashes.py` produce per-file diffs that are visible in `git diff` if the vault is versioned. We do not duplicate the safety net.
4. **Atomic writes.** Every patch goes through `.tmp` + rename.
5. **Reports are never overwritten.** Each repair gets its own timestamped file.
6. **No silent destruction.** Every fix is announced before execution; the user can interrupt.
