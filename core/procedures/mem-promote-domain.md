# Procedure: Promote Domain (new in v0.5)

Goal: promote a coherent set of items from `00-inbox/` (or items scattered across the vault) into a new **permanent domain** in `10-episodes/domains/{slug}/`. Enforces the anti-drift rule (>= 3 items on the same thread).

Typical use case: you have accumulated 3-4 notes about your health in the inbox that don't fit into any project. Instead of creating a fake `health` project, promote them to a permanent domain.

## Trigger

The user types `/mem-promote-domain {target-slug} [items]` or expresses intent in natural language: "create a health domain", "promote these 3 notes into a domain", "regroup this thread into a domain".

Arguments:
- `{target-slug}` (**required**): slug of the new domain to create.
- `{items}` (optional, multi-valued): paths of items to promote. If absent, ask the user for the list.
- `--scope personal|work`: scope of the domain. Default: `default_scope` from `memory-kit.json`.
- `--from-inbox`: promote all inbox items matching a keyword (to be supplied).
- `--dry-run`: shows the plan without applying.
- `--no-confirm`: applies without confirmation.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Verify slug uniqueness

Verify that `{VAULT}/10-episodes/domains/{target-slug}/` does not already exist. Also verify there is no project with the same slug (semantic collision).

If conflict, stop with a clear message.

### 2. Enumerate items to promote

- If `{items}` provided: explicit list.
- If `--from-inbox {keyword}`: grep in `00-inbox/` for files containing the keyword.
- Otherwise: ask the user (the router can suggest by reading the inbox).

### 3. Enforce the anti-drift rule (>= 3 items)

If fewer than 3 items to promote, display:

> Anti-drift rule: a domain can only be created from at least 3 archives on the same thread. You have {N}.
> Recommendation: keep them in the inbox until you reach 3 items, or attach to an existing domain.

Allow the user to bypass explicitly with `--force` (bool, to be added as an option if needed).

### 4. Present the plan

Format:

```
## Domain promotion — {target-slug}

Scope: {personal|work}

Items to promote ({N}):
  - {item path 1} → 10-episodes/domains/{slug}/archives/{name}.md
  - {item path 2} → ...
  - ...

Structure created:
  10-episodes/domains/{target-slug}/
    context.md (skeleton)
    history.md (skeleton)
    archives/ (with moved items)

Continue? [y/n]
```

If `--dry-run`: stop here.

### 5. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

Steps:

1. **Create the structure**: `mkdir -p 10-episodes/domains/{target-slug}/archives/`.
2. **Create `context.md`** skeleton (the intro line right after the frontmatter is mandatory — sourced from `core/i18n/strings.yaml` `{language}.context.intro_with_links`):
   ```yaml
   ---
   zone: episodes
   kind: domain
   slug: {target-slug}
   scope: {scope}
   collective: false
   tags: [zone/episodes, kind/domain, domain/{target-slug}, scope/*]
   ---

   {{i18n: context.intro_with_links}}

   # {target-slug} — Active context

   ## Current state
   Permanent domain created on YYYY-MM-DD from {N} items.

   ## Cumulative decisions
   (to be enriched session after session)

   ## Next steps
   (to be defined)
   ```
3. **Create `history.md`** skeleton: frontmatter + the localized intro line (`{language}.history.intro_with_links`) right after, then title + N initial entries for the promoted items.
4. **For each item to promote**:
   - Read its current frontmatter.
   - Update: `zone: episodes`, `kind: domain`, `domain: {target-slug}`, add tags `zone/episodes`, `kind/domain`, `domain/{target-slug}`.
   - If the file date is not explicit, derive it from the FS creation date.
   - Rename the file to `YYYY-MM-DD-HHhMM-{target-slug}-{old-short-title}.md`.
   - Move to `10-episodes/domains/{target-slug}/archives/`.
   - Pattern 1 (atomic rename).
5. **Update `index.md`**: add the domain in the Domains section.
6. **For each promoted item**: add a line in the new domain's `history.md`.

### 6. Confirm

Format:

```
Domain created: {target-slug} ({scope})
{N} items promoted from inbox / other zones.
Index updated.

To add new archives to this domain: /mem-archive --domain {target-slug}
```
