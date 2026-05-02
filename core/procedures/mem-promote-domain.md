# Procedure: Promote Domain (v0.5, hardened in v0.7.4)

Goal: promote a coherent set of items into a new **permanent domain** in `10-episodes/domains/{slug}/`. Hardened in v0.7.4 to support sources beyond `00-inbox/`, full idempotence on re-invocation, and explicit override of the anti-drift rule when justified.

Typical use cases:
- You accumulated 3-4 notes about your health in the inbox that don't fit into any project. Instead of creating a fake `health` project, promote them to a permanent domain.
- You have transverse atoms scattered in `40-principles/`, `20-knowledge/`, etc. (e.g. infra knowledge consumed by multiple projects) that share a sub-zone like `mt-iris-infra/` and need to be regrouped under a real domain rather than left orphan.
- You want to re-run the procedure on an existing domain to add newly-arrived items idempotently.

## Trigger

The user types `/mem-promote-domain {target-slug} [items]` or expresses intent in natural language: "create a health domain", "promote these 3 notes into a domain", "regroup this thread into a domain", "promote `40-principles/work/mt-iris-infra/` items into a domain".

Arguments:
- `{target-slug}` (**required**): slug of the domain to create or extend.
- `{items}` (optional, multi-valued): paths of items to promote. If absent and no source flag set, ask the user for the list.
- `--scope personal|work`: scope of the domain. Default: `default_scope` from `memory-kit.json`. **Ignored** if the domain already exists (the existing scope wins).
- `--from-inbox {keyword}`: promote all `00-inbox/` items matching a keyword.
- `--from-sub-zone {path}` _(v0.7.4, NEW)_: promote all atoms living under a sub-zone of a transverse zone, e.g. `40-principles/work/mt-iris-infra/`. Path is relative to the vault root. Useful for the "scattered transverse atoms" use case.
- `--from-tag {tag}` _(v0.7.4, NEW)_: promote all atoms whose frontmatter `tags:` contains the given tag (e.g. `topic/iris-infra`).
- `--allow-2-items` _(v0.7.4, NEW)_: explicit override of the anti-drift rule when only 2 items are available. Used sparingly, see "Anti-drift override" below.
- `--dry-run`: show the plan without applying.
- `--no-confirm`: apply without confirmation.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Slug resolution: create-mode vs extend-mode (v0.7.4)

Check whether `{VAULT}/10-episodes/domains/{target-slug}/` already exists.

- **Does NOT exist** → **create-mode** (original v0.5 flow). Verify there is no project with the same slug (semantic collision: a project and domain cannot share a slug). If conflict, stop with a clear error.
- **Already exists** → **extend-mode** (idempotent re-promotion). Read the existing `context.md` to load `scope`, `phase`, etc. The user-supplied `--scope` is ignored (warning printed if it contradicts). Proceed with the items list — items already attached to the domain (`domain: {slug}` already in their frontmatter) are skipped silently with a `[skip] already attached` note.

This makes the procedure **fully idempotent**: running it twice with the same arguments is a safe no-op for already-attached items. Useful when you discover late that an additional atom belongs to an existing domain.

### 2. Enumerate items to promote

Source resolution priority (first hit wins, mutually exclusive):

1. `{items}` provided as positional args → explicit list.
2. `--from-inbox {keyword}` → grep `00-inbox/` for files containing the keyword (case-insensitive).
3. `--from-sub-zone {path}` _(v0.7.4)_ → `find {VAULT}/{path} -name '*.md' -not -name 'index.md'`. Path must be under a transverse zone (`20-knowledge/`, `40-principles/`, `50-goals/`, `60-people/`). Reject paths outside.
4. `--from-tag {tag}` _(v0.7.4)_ → scan all transverse zone atoms, keep those whose frontmatter `tags:` contains `{tag}`.
5. Otherwise → ask the user. The router can suggest by reading the inbox.

For each candidate item, read its frontmatter and skip if it already carries `domain: {target-slug}` (idempotent extend-mode).

### 3. Anti-drift rule (v0.7.4 — clarified)

A new domain (create-mode) requires **≥ 3 items** on the same thread to prevent fake-domain proliferation. Soft override mechanisms:

- `--allow-2-items`: explicit acceptance for 2 items. Justified for **transverse atoms regrouping** where the 2 atoms are clearly anchors of a future-growing domain (e.g. infra knowledge that consolidates as the project consumers grow). Documented exception, not the default path.
- `--force`: bypass with no minimum (last resort, recommend only for migration of pre-v0.5 vaults).

Display when below the threshold without override:

```
Anti-drift rule: a new domain typically requires ≥ 3 items. You have {N}.

Recommendation: keep them in the inbox/transverse zone until you reach 3,
or attach to an existing domain.

Override: re-run with --allow-2-items (for clear transverse anchors) or
--force (last resort).
```

In **extend-mode**, the rule does not apply — adding 1 item to an existing domain is always fine.

### 4. Present the plan

Format (create-mode):

```
## Domain promotion — {target-slug} (CREATE)

Scope: {personal|work}

Items to promote ({N}):
  - {item path 1} → 10-episodes/domains/{slug}/archives/{name}.md   (move + retag)
  - {item path 2} → frontmatter patched in place: domain: {slug}    (transverse atom kept in zone)
  - ...

Structure created:
  10-episodes/domains/{target-slug}/
    context.md (skeleton)
    history.md (skeleton)
    archives/ (with moved items, if any are session-style)

Continue? [y/n]
```

Format (extend-mode):

```
## Domain promotion — {target-slug} (EXTEND existing domain)

Existing scope: {scope}  (--scope arg ignored if provided)

Items to add ({N}):
  - {item path} → frontmatter patched: domain: {slug} added
  - ...

Already attached, skipped ({M}): {paths}

Continue? [y/n]
```

Note on the **move-vs-retag** distinction (v0.7.4 clarification):

- **Inbox notes** (`00-inbox/{file}.md`) → moved to `10-episodes/domains/{slug}/archives/` with rename `YYYY-MM-DD-HHhMM-{slug}-{old-short-title}.md` (existing v0.5 behavior).
- **Transverse atoms** in `40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/` → **kept in their zone** (their semantic placement is correct; they're principles/knowledge, not session archives). Only their frontmatter is patched (`domain: {slug}` added, plus `domain/{slug}` tag). Their physical location is unchanged. The domain's `history.md` lists them as anchored atoms via wikilink, not as moved archives.

### 5. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

#### Create-mode steps

1. **Create the structure**: `mkdir -p 10-episodes/domains/{target-slug}/archives/`.
2. **Create `context.md`** skeleton (the intro line right after the frontmatter is mandatory — sourced from `core/i18n/strings.yaml` `{language}.context.intro_with_links`):
   ```yaml
   ---
   domain: {target-slug}
   phase: actif
   last-session: {YYYY-MM-DD}
   tags: [domain/{target-slug}, zone/episodes, kind/domain, scope/{scope}]
   zone: episodes
   kind: domain
   slug: {target-slug}
   scope: {scope}
   collective: false
   display: "{target-slug} — context"
   ---

   {{i18n: context.intro_with_links}}

   # {target-slug} — Active context

   ## Scope

   (one-paragraph definition of what this domain covers and why it is a domain
   rather than a project — vocation, transversality, repo absence, etc.)

   ## Current state

   - Domain created on YYYY-MM-DD from {N} items.
   - Initial atoms attached:
     - [[{atom 1}]]
     - [[{atom 2}]]
     - ...

   ## Cumulative decisions

   (to be enriched session after session)

   ## Next steps

   (to be defined)
   ```
3. **Create `history.md`** skeleton: frontmatter + the localized intro line (`{language}.history.intro_with_links`) right after, then title + the initial creation entry referencing the founding archive of the promotion session (i.e. the `mem-archive` archive of the very session that promoted these atoms — by wikilink).

#### Both modes — per-item application

For **inbox-style items** (originally in `00-inbox/`, or session-format archives):
- Read its current frontmatter.
- Update: `zone: episodes`, `kind: domain`, `domain: {target-slug}`, `scope` from domain, add tags `zone/episodes`, `kind/domain`, `domain/{target-slug}`.
- If the file date is not explicit, derive from FS mtime.
- Rename to `YYYY-MM-DD-HHhMM-{target-slug}-{old-short-title}.md`.
- Move to `10-episodes/domains/{target-slug}/archives/`.
- Pattern 1 (atomic rename) — see `_concurrence`.

For **transverse atoms** (`40-principles/...`, `20-knowledge/...`, `50-goals/...`, `60-people/...`) (v0.7.4 NEW path):
- Read its current frontmatter.
- Add `domain: {target-slug}` if absent. **Do not** override existing `project:` — an atom can be attached to both a project (originating context) and a domain (transverse classification). The router prefers `domain:` for index grouping when both are set.
- Add `context_origin: "[[<promotion-session-archive>]]"` if absent (the founding archive of the promotion session).
- Add tag `domain/{target-slug}` to the `tags:` list.
- **Do not move the file**. Atomic write of the patched frontmatter.
- Append a back-link to the domain's `context.md` body as a quote line right after the title:
  ```markdown
  > Domaine : [[10-episodes/domains/{target-slug}/context|{target-slug}]] — voir [[10-episodes/domains/{target-slug}/history|fil chronologique]].
  ```
  Idempotent (skip if already present).

#### Both modes — finalization

- **Update the domain's `history.md`**: add a line per newly-attached atom under the current date.
- **Update `index.md`**: regenerate via `python {kit_repo}/scripts/rebuild-vault-index.py --vault {vault}`. The Domains section will pick up the new domain or the new atoms grouped under it.

### 6. Confirm

Format (create-mode):

```
✓ Domain created: {target-slug} ({scope})
  {N} items promoted: {M} session-style moves + {K} transverse atoms re-tagged.
  Index updated.

  To add new archives to this domain: /mem-archive --domain {target-slug}
  To extend with more atoms later: /mem-promote-domain {target-slug} <items>  (idempotent)
```

Format (extend-mode):

```
✓ Domain extended: {target-slug}
  {N} new items attached, {M} already-attached items skipped.
  Index updated.
```

## Idempotence guarantees (v0.7.4)

The procedure is idempotent on three axes:

1. **Re-invocation with the same arguments** → no-op for items already attached.
2. **Slug already exists as domain** → extend-mode kicks in automatically (no error).
3. **Frontmatter patches** → if the target frontmatter already carries `domain:` / tag / `context_origin`, the patch is a no-op.

Slug collision with an existing **project** remains a hard error (different ontological status — projects have a finite vocation, domains are permanent; merging requires `mem-rename` first).
