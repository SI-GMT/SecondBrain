# Procedure: Historize project (v0.7.4)

Goal: move a finished project into the **archived zone** (`10-episodes/archived/{slug}/`) so it stays in the vault for long-term reference but is excluded by default from the access skills (`mem-recall`, `mem-list`, `mem-search`, `mem-digest`). Reduces token consumption of the briefing at session start.

Reverse operation: `--revive` to bring an archived project back to active state.

Doctrinal pattern (per `core/procedures/_when-to-script.md`): this skill **delegates to a versioned Python script** (`scripts/mem-historize.py`). The LLM's role is to resolve paths, invoke the script, parse its output, and surface the result in the user's conversational language. Do not re-implement the move/patch logic in tool calls.

## Trigger

The user types `/mem-historize {slug}` (or `/mem-historize {slug} --revive`) or expresses intent in natural language: "archive le projet codemagdns, c'est fini", "ressuscite codemagdns", "remets codemagdns en actif", "mets ce projet de côté il est terminé", "rapatrie ce projet dans les archives".

Recognized options (forwarded to the script):

- `{slug}` (**required**): project slug.
- `--revive`: reverse mode, bring `10-episodes/archived/{slug}/` back to `10-episodes/projects/{slug}/`. Default: archive an active project.
- `--apply`: actually perform the move + frontmatter patch. Without this, dry-run only — print the plan and stop.
- `--no-confirm`: skip the interactive confirmation prompt (combine with `--apply`).
- `--json`: machine-readable output for chaining.

## Vault path & kit repo resolution

Read {{CONFIG_FILE}} and extract `vault` and `kit_repo`. If absent or unreadable, surface the standard error and stop.

## Procedure

### 1. Pre-flight check

Verify the slug exists in the vault before invoking the script. Use Glob:
- `{VAULT}/10-episodes/projects/{slug}/` exists → active project, can be archived.
- `{VAULT}/10-episodes/archived/{slug}/` exists → already archived, can be revived.
- Both → **ambiguity error**, refuse to proceed (manual cleanup required).
- Neither → unknown slug, ask the user to verify or provide `mem-list` output.

If the user said "archive {slug}" but it's already archived (or said "revive" but it's already active), the script's idempotent path will report a no-op. No need to second-guess in the procedure — let the script signal it.

### 2. Invoke the script

```
python {KIT}/scripts/mem-historize.py --vault {VAULT} --slug {SLUG} [--revive] [--apply] [--no-confirm]
```

The script:
1. Locates the slug across active/archived directories.
2. Patches `context.md` frontmatter:
   - **Archive**: `phase: archived`, `archived_at: "{date}"`, append `" [archived]"` to `display`.
   - **Revive**: `phase: revived (please update with current state)`, remove `archived_at`, strip `" [archived]"` from `display`.
3. Moves the project folder atomically (`shutil.move`) between `projects/` and `archived/`.
4. Prints a summary on stdout (or JSON with `--json`).

The script is idempotent: archiving an already-archived project, or reviving an already-active one, is a no-op + report.

### 3. Surface the result

After the script returns, parse stdout (or JSON) and reply in the user's conversational language:

```
✓ Project '{slug}' archived.

  Moved   : 10-episodes/projects/{slug}/  →  10-episodes/archived/{slug}/
  Patched : context.md (phase: archived, archived_at: {date}, display: '... [archived]')

  Future access:
  - /mem-recall {slug}        → loads from archived/ on explicit demand
  - /mem-list --include-archived  → shows the project in inventory
  - /mem-search ... --include-archived  → searches the project's archives
  - /mem-historize {slug} --revive  → bring it back if needed
```

For revive:

```
✓ Project '{slug}' revived.

  Moved   : 10-episodes/archived/{slug}/  →  10-episodes/projects/{slug}/
  Patched : context.md (phase: revived — please update with current state)

  The project is back in default scope. Update its phase next time you write to it.
```

### 4. Refresh the index

Invoke `python {KIT}/scripts/rebuild-vault-index.py --vault {VAULT}` after a successful operation. The index will:

- Move the project line from the **Projects** section to **Archived projects** (or vice-versa for revive).
- Pick up the modified `display` for graph view.

Optional but recommended — without it, `index.md` stays out of date until the next mutation.

## Doctrinal rules (v0.7.4)

These rules are enforced by the script and by the access skills patched in v0.7.4:

| Skill | Default behavior on archived projects | Override |
|---|---|---|
| `mem-recall` | Refuses silently to load an archived project unless invoked with the explicit slug. The default briefing's project list does not enumerate archived ones. | `mem-recall {slug}` loads even if archived. |
| `mem-list` | Section `### Archived ({N})` collapsed by default — count only. | `--include-archived` expands the list. `--archived-only` shows only archived. |
| `mem-search` | Excludes `10-episodes/archived/**` from the scan. | `--include-archived` reincludes. `--archived-only` searches only archived. |
| `mem-digest` | Refuses on an archived slug. | `--from-archived` allows it. |
| `mem-archive` | **Hard error** if the project is archived — no override. The user must `--revive` first. | (none) |
| `mem-rename` / `mem-merge` / `mem-rollback-archive` | Operate on archived as on any other project. No restriction. | — |
| `mem-archeo*` | Refuses on an archived slug (an archeo'd repo should be active). | `--allow-archived`. |

**Cross-reference resolution**: when a transverse atom carries `project: {slug}` and the project is archived, the resolver still finds it by checking both `10-episodes/projects/{slug}/` and `10-episodes/archived/{slug}/`. The resolver is in `rebuild-vault-index.py` and in the index-grouping logic — it does NOT need to be re-implemented per skill.

**No-zombie rule**: an archived project is never automatically deleted, even if its associated `repo_path` is removed from the filesystem. Permanent deletion goes through a future `mem-purge` skill (out of scope for v0.7.4).

**Workflow recommendation**: run hygiene before historizing.

```
/mem-health-scan
/mem-health-repair --apply
/mem-historize {slug}
```

This guarantees you don't archive a project with orphan atoms or malformed frontmatter — those would silently haunt future scans.

## What NOT to do

- **Do not** move the project folder yourself in tool calls (no `Bash mv`, no manual atomic-rename in the procedure body). The script handles `shutil.move` correctly with cross-platform semantics.
- **Do not** patch `context.md` frontmatter yourself in tool calls. The script handles the regex patches idempotently.
- **Do not** fall back to in-LLM reimplementation if the script is missing. Surface the error per the `_when-to-script.md` doctrine.

## Escape hatch

If the script fails (Python missing, kit_repo points to a stale path):

```
✗ mem-historize failed to invoke the script.

  Reason : {short reason from stderr}

  Expected: python {KIT}/scripts/mem-historize.py --vault {VAULT} --slug {SLUG}
  Action  : ensure Python is installed and that kit_repo in {{CONFIG_FILE}}
            points to a valid kit checkout. Re-run `deploy.ps1` from the
            kit root if in doubt.
```
