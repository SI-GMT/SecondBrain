# Procedure: Health scan (v0.7.3.1)

Goal: audit the vault for hygiene defects without modifying anything. Produces a structured report under `99-meta/health/scan-{ts}.md` that `mem-health-repair` can later consume to apply fixes. Read-only.

## Doctrinal note (v0.7.3.1)

This procedure **delegates to a versioned Python script** (`{kit_repo}/scripts/mem-health-scan.py`) rather than re-implementing the scan in LLM-orchestrated tool calls every invocation. Rationale: a systematic vault parse (parse YAML for every `*.md`, scan wikilinks, build incoming-link graph) is intrinsically a script job, not LLM-orchestration territory. Re-implementing it ad hoc per session would burn tool-call budget, drift from the spec and skip the unit-test surface. See `core/procedures/_when-to-script.md` for the full doctrinal rule.

The LLM's role here is therefore narrow: resolve the vault path, invoke the script, parse its output, surface the result to the user in their conversational language. **Do not re-implement any of the 8 checks below in tool calls** — the spec lives here for readability and contract stability with `mem-health-repair`, but the *execution* is the script's job.

## Categories audited (8)

| Category | Severity | Description |
|---|---|---|
| `malformed-frontmatter` | error | YAML frontmatter that fails to parse — typically unquoted `[TAG]` flow-sequences or stray colons. Detected first to avoid false-positive cascades into other categories. |
| `stray-zone-md` | warn | Empty `{vault}/{NN-zone}.md` files at vault root, created by Obsidian on click of a dangling wiki-link target named after a zone. |
| `empty-md-at-root` | warn | Other empty `*.md` at vault root (broader catch). |
| `missing-zone-index` | warn | Zone folder exists but lacks its `{zone}/index.md` hub. |
| `missing-display` | info | Frontmatter without `display:` where universal conventions require it (see `_frontmatter-universal.md`). |
| `dangling-wikilinks` | info | `[[X]]` references whose target is not present anywhere in the vault. |
| `orphan-atoms` | warn | Transverse atoms with no `project:`/`domain:` and zero incoming wikilinks. |
| `missing-archeo-hashes` | warn | Atoms with `source: archeo-*` missing `content_hash` (or `previous_topology_hash` for repo-topology files). |

## Trigger

The user types `/mem-health-scan` or expresses the intent in natural language: "audit my vault", "check the vault health", "scan the memory for issues", "what's broken in memory?", "find orphans in the vault".

Recognized options (passed through to the script):
- `--zones {comma-separated list}` — restrict to one or more numbered zones.
- `--only {category}` — restrict to a single check category.
- `--quiet` — suppress per-finding stdout, summary only.
- `--no-write` — do not persist the report file.
- `--json` — print a JSON summary on stdout instead of plain text (useful for chaining into `mem-health-repair`).

## Vault path & kit repo resolution

Read {{CONFIG_FILE}} and extract:
- `vault` → `{VAULT}` in what follows.
- `kit_repo` → `{KIT}` in what follows. Required to locate `scripts/mem-health-scan.py`.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Invoke the scanner

Run, with the user-provided options forwarded:

```
python {KIT}/scripts/mem-health-scan.py --vault {VAULT} [options]
```

The script:
1. Walks `{VAULT}/**/*.md` (excluding `.obsidian/` and `.trash/`).
2. Runs each of the 8 checks in dependency order — `malformed-frontmatter` first so that subsequent checks skip files whose frontmatter cannot be parsed (avoids cascading false positives).
3. Persists the report at `{VAULT}/99-meta/health/scan-{ts}.md` (unless `--no-write`).
4. Prints a parseable summary on stdout (text by default, JSON with `--json`).
5. Exit code `1` if any `error`-severity finding, else `0`.

### 2. Surface the result to the user

Read the script's stdout. Reply in the user's conversational language with a 4-line summary:

```
✓ Vault health scan completed.

  Total findings : {N} ({E} errors, {W} warnings, {I} info)
  Top categories : {category-1} ({N1}), {category-2} ({N2}), ...

  Report : 99-meta/health/scan-{ts}.md
```

If the script wrote no report (because `--no-write` was passed), replace the "Report" line with `(report not persisted, --no-write was set)`.

If `findings_by_severity.error > 0`, lead the summary with a one-line warning suggesting that `error` findings (most often `malformed-frontmatter`) be addressed before running other vault tooling, since malformed frontmatters break downstream scripts that rely on YAML parsing.

If the scan finds zero issues across all categories:

```
✓ Vault is clean. No findings.
```

### 3. Refresh the index

Invoke `python {KIT}/scripts/rebuild-vault-index.py --vault {VAULT}` to update the `## Health` section of `{VAULT}/index.md` with the new report. Optional but recommended — without it the new report is not linked from the root index until the next mutation triggers a rebuild.

## What NOT to do

- **Do not** open and parse `*.md` files in the vault yourself (Glob/Grep/Read in a loop). The script does this — and does it correctly with the `malformed-frontmatter` priority that avoids false positives.
- **Do not** create an ad-hoc script in `$TEMP/` or anywhere outside `scripts/`. The procedure is doctrinally bound to `{KIT}/scripts/mem-health-scan.py`. If the script is missing, the right reaction is to instruct the user to re-run `deploy.ps1` (or alternatively run from the kit checkout if `kit_repo` points to a stale path).
- **Do not** re-implement any check in this procedure body. The 8-category table above is a *contract* with `mem-health-repair` and a doc for the user — it is not a re-implementable spec. The single source of truth is `scripts/mem-health-scan.py`.

## Escape hatch

If the script fails to run (Python missing, PyYAML missing, kit_repo points to a stale path), surface a clear message:

```
✗ mem-health-scan failed to invoke the scanner.

  Reason : {short reason from stderr}

  Expected: python {KIT}/scripts/mem-health-scan.py --vault {VAULT}
  Action  : ensure Python and PyYAML are installed, and that
            kit_repo in {{CONFIG_FILE}} points to a valid kit checkout.
            Re-run `deploy.ps1` from the kit root if in doubt.
```

Do not fall back to an in-LLM scan reimplementation. The "no fallback" stance is intentional — silent fallback would mean future calls of this skill silently produce different (likely degraded) results depending on environment quirks, which is exactly the doctrinal failure mode this procedure is meant to prevent.
