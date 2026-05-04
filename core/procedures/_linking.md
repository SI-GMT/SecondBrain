## Linking invariant — Zero orphan atom

**Every file written into the vault must have at least one inbound or outbound link to another vault file.** No file is left dangling in Obsidian's graph view.

### Rationale

Obsidian's graph relies on `[[wikilinks]]` and `[markdown](links.md)` to connect nodes. A file with neither is rendered as an isolated node, invisible to graph navigation and easily overlooked. The brain-centric model only works if **all atoms are reachable** from the index → project → archive chain (or the equivalent for transverse atoms).

### Link contract per file kind

| File | Required outbound link(s) | Where it gets its inbound link |
|---|---|---|
| `index.md` (root) | All projects, domains, archives, transverse atoms | (entry point — none required) |
| `10-episodes/{kind}/{slug}/context.md` | `history.md` (peer), `archives/` (folder), latest archive | `index.md` (Projects/Domains section) |
| `10-episodes/{kind}/{slug}/history.md` | `context.md` (peer), every listed archive | `index.md` (Projects/Domains section), `context.md` (peer) |
| `10-episodes/{kind}/{slug}/archives/{file}.md` | `context.md` (peer) optional, `derived_atoms` if any | `history.md` of its project, `index.md` (Archives section) |
| Transverse atom (`40-principles/...`, `20-knowledge/...`, `50-goals/...`, `60-people/...`) | Founding archive via `context_origin` (frontmatter) **and** wikilink in body | `index.md` (Principles/Knowledge/... section grouped by `project:` frontmatter), `history.md` of attached project |

### Standard intro lines (cross-links context ↔ history)

Every `context.md` and `history.md` carries a one-line intro right after the frontmatter that resolves to wikilinks. The exact wording is localized via `core/i18n/strings.yaml` (`context.intro_with_links`, `history.intro_with_links`), substituted at write time. Default English fallback:

- `context.md`: `> Mutable snapshot of the project. See also: [history](history.md) · [archives/](archives/)`
- `history.md`: `> Chronological session log. See also: [context](context.md)`

These lines are **structural** — they are rewritten on every full `mem-archive`. The user is free to edit the rest of the file freely; the intro block (line 1 after the frontmatter) is procedurally enforced.

### Transverse atom rule

When the router writes a derived atom into `40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/`, the procedure MUST:

1. Set `project: {slug}` (or `domain: {slug}`) in the atom's frontmatter — used by `rebuild-vault-index.py` to group by project.
2. Set `context_origin: "[[<founding-archive-name>]]"` in the atom's frontmatter (already mandated by the v0.5 doctrine).
3. Append a line to the **founding archive's** `derived_atoms:` list (frontmatter array): `"[[<atom-name>]]"`.
4. Optionally mention the atom in `history.md` of the attached project under a "Derived atoms this session" sub-bullet — recommended but not blocking.

If steps 1-3 are not all satisfiable (no clear attached project, no founding archive), the atom is written to `00-inbox/` instead with tag `unlinked-atom` and reported to the user for manual triage.

### Enforcement

- `mem-archive`, `mem-promote-domain` — generate the standard intro lines on every `context.md` / `history.md` write.
- `_router` (universal) — enforces frontmatter `project:`/`domain:` + `context_origin` + appends to `derived_atoms` of the founding archive.
- `scripts/enforce-linking.py` — retroactive utility to patch existing vaults that pre-date this rule. Idempotent.
- `scripts/rebuild-vault-index.py` — surfaces every transverse atom in the index under its attached project; orphans (no `project:` field) are listed under "(unattached)" so they remain visible.

### What "orphan" means here

A file is an **orphan** if Obsidian's graph view shows it with zero edges. By doctrine, the only legitimate orphans are:

- The vault `.git/`, `.obsidian/`, `.trash/` content (excluded from the graph anyway).
- Pre-v0.5.4 files written before this invariant was introduced — fixed by running `enforce-linking.py` once.

Anything else flagged as orphan is a bug in the procedure that wrote it.

## Wikilink resolution invariant (v0.7.4)

**Every `[[wikilink]]` written into a persisted vault file must resolve to an existing target at the time of writing.** Wikilinks that name a future or hypothetical target are forbidden in plain prose — they create silent dangling references that pollute the graph view and trip downstream tools (`mem-health-scan` flags them, `mem-search` returns nothing, etc.).

### Convention for legitimate non-resolving references

A skill or human author legitimately needs to *mention* a wikilink by name (as an example, an illustration, or a future intention) without committing it as a reference. Two conventions cover this:

| Use case | Convention | Example |
|---|---|---|
| Cite a wikilink as a literal example (doctrine, spec, tutorial body) | **Inline backticks** | `` Le wikilink `[[no-force-push-sur-main]]` est mentionné en doctrine. `` |
| Note a future cible to be created later | **Inline backticks + a TODO note** | `` Cible à créer : `[[mt-iris-prod-backup-policy]]` (TODO once the policy is documented). `` |

Both forms render Obsidian-side as code spans (the wikilink is **not** interpreted) and are filtered by `scripts/mem-health-scan.py` (function `strip_code` since v0.7.3.1) so they do not contribute to dangling-wikilink findings.

### Enforcement at write time

Skills that write prose into the vault (`mem-archive`, `_router`, `mem-archeo*`, `mem-promote-domain`, `mem-doc`, `mem-historize`) MUST:

1. Before persisting, scan the body for `[[X]]` wikilinks **outside** code spans.
2. For each, verify the target resolves (file with stem `X` exists in the vault, or relative path `X.md` exists).
3. If a wikilink does not resolve, the skill MUST either:
   - **Create the target first** (recursive write — preferred when the target is a transverse atom that would naturally exist, e.g. a derived principle or knowledge).
   - **Demote the wikilink to inline backticks** in the persisted prose (e.g. `[[X]]` → `` `[[X]]` ``).
   - **Surface the issue to the user** if the resolution requires arbitrage (e.g. the user must decide which existing target the link should point to).

Silent persistence of a dangling wikilink is a bug in the procedure.

### Retroactive fix policy for archives

Archives are immutable by doctrine — their prose is not rewritten after publication. When `mem-health-scan` flags a dangling wikilink in an existing archive, the resolution policy is:

1. **Preferred** — create the target the wikilink expects, even if the target is a historical/superseded note. The wikilink resolves and the graph stays consistent. (Pattern used in v0.7.4 to materialize `no-force-push-sur-main.md` and `obsidian-graph-style-v0-5.md` long after the archives that referenced them were written.)
2. **Acceptable** — leave the dangling wikilink unresolved in the archive prose if the target is impossible to materialize meaningfully (e.g. the wikilink referred to a hypothetical concept that never came to be). Document the reason in the archive's frontmatter via a `dangling_intentional: ["X", "Y"]` field so the scanner can be configured to skip these.

The second option is a last resort. The first option is doctrinally cleaner and is the default.

### Why this invariant matters

Without this rule, an archive written today can poison the graph for years — every scan reports the same dangling wikilink, every search misses the implied connection, every reader of the archive wastes attention parsing a broken reference. Forcing resolution at write time keeps the technical debt at zero.

The convention also has a soft pedagogical effect: a writer aware that wikilinks are *enforced* tends to think harder about whether the link target is real and useful, which improves the quality of the cross-linking overall.
