# Doctrinal block: archived project handling (v0.7.4)

This block is shared (`{{INCLUDE _archived}}`) by skills that need to filter or reject archived projects. The rules below are doctrinal — deviations require an explicit note in the calling procedure.

## Definition

A project is **archived** when:

1. Its physical folder lives at `{VAULT}/10-episodes/archived/{slug}/` (not `10-episodes/projects/{slug}/`), AND
2. Its `context.md` frontmatter carries `phase: archived` and `archived_at: "{date}"`.

These two conditions are co-imposed by `mem-historize` at the moment of archival. Either alone (folder moved without phase patch, or phase patched without move) is a half-state to be flagged by `mem-health-scan` (future check, not in v0.7.4 yet — listed in the v0.7.5 backlog).

## Resolution: where to find a slug

A skill that resolves a project by slug MUST check both locations in this order:

1. `{VAULT}/10-episodes/projects/{slug}/` — active.
2. `{VAULT}/10-episodes/archived/{slug}/` — archived.

The first match wins. If both exist, that's a half-state error — refuse to proceed and ask the user to `mem-historize --revive` or manually clean up.

## Per-skill behaviour matrix (v0.7.4)

| Skill | Default on archived | Override flag | Reason |
|---|---|---|---|
| `mem-recall` | Refuses silently if no slug specified. Loads the project if `mem-recall {slug}` is explicit. | (none — explicit slug IS the override) | Reduces token consumption of the implicit briefing. The user can always force by naming the slug. |
| `mem-list` | Section `### Archived ({N})` collapsed (count only). | `--include-archived` (full list) / `--archived-only` (only archived) | Inventory should reflect both, but archived shouldn't dilute the active view. |
| `mem-search` | Skips `10-episodes/archived/**` from the scan. | `--include-archived` / `--archived-only` | Same reason: keep the active surface fast and relevant. |
| `mem-digest` | Refuses on an archived slug. Surfaces a one-line message with the override hint. | `--from-archived` | Digesting an archived project is a deliberate retrospective action, not a default. |
| `mem-archive` | **Hard error**, no override. | (none — must `mem-historize --revive` first) | Writing to an archived project would silently un-archive it without metadata. Force the explicit revive step. |
| `mem-rename` / `mem-merge` / `mem-rollback-archive` | Operate normally on archived projects. | — | These are vault-management skills; their semantics don't depend on the archived flag. |
| `mem-archeo` (and -context / -stack / -git) | Refuses on an archived slug. | `--allow-archived` | An archeo'd repo should typically be an active one — but if you want to do a retrospective, the override is there. |
| `mem-promote-domain` | Operates normally — promotion does not touch archived/active classification. | — | A transverse atom can be promoted to a domain regardless of its originating project's archive state. |
| `mem-doc` | Refuses on `--project {slug}` if archived (same as `mem-archive`). | (none — must revive first) | Same reasoning as `mem-archive` — writing into an archived project's archives folder is a write operation that requires explicit revival. |
| `mem-historize` itself | Idempotent — re-archiving an archived slug or reviving an active one is a no-op + report. | — | Self-documenting via the script's idempotence. |

## Implementation contract for skills

A skill bound by this block MUST:

1. **Resolve the project location** (active vs archived) before any read or write. Do not assume `10-episodes/projects/{slug}/` exists.
2. **Apply the matrix above** for the default behavior.
3. **Honor the override flag** if present in user invocation.
4. **Surface a clear message** when refusing — never fail silently. Format:

   ```
   ✗ Project '{slug}' is archived (since {date}).

     Default action skipped per archived-project rule.

     Options:
     - Override:    {skill-name} {original-args} --include-archived (or --from-archived / --allow-archived)
     - Reactivate:  /mem-historize {slug} --revive --apply
   ```

The exact override flag name varies per skill (see matrix). Surface the right one.

## Cross-reference resolution

When a transverse atom carries `project: {slug}`, the resolver looks up both `10-episodes/projects/{slug}/` and `10-episodes/archived/{slug}/`. This is the responsibility of `rebuild-vault-index.py` (which groups atoms in the index) and any skill that follows `project:` references. **The atom's frontmatter is not patched on archive/revive** — `project: {slug}` remains valid in both states; only the folder location changes.

## Why this design

The alternative was to introduce a separate frontmatter field (`archived: true`) on every atom of the project. That would:
- Multiply write operations on archive (every archive file in the project's folder needs a patch).
- Risk drift if the patches partially fail.
- Pollute the per-atom frontmatter with status that's already implicit from the parent folder.

By keeping the archive flag at the project level (folder location + `context.md` phase), we keep the operation atomic (one `shutil.move` + one frontmatter patch on `context.md`), reversible (one `--revive`), and visible (folder path is self-documenting in any file browser).
