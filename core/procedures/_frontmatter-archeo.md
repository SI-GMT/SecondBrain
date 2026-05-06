## Frontmatter — archeo atoms (source: archeo-*)

This block is included by `mem-archeo-context.md`, `mem-archeo-stack.md` and
`mem-archeo-git.md`. It enumerates **exhaustively** every frontmatter field
required on an archeo atom — universal fields (from `_frontmatter-universal.md`)
+ archeo-specific fields. The split between blocks is intentional :
`_frontmatter-universal.md` defines the 6 fields any vault file must carry,
this block adds the 5–8 archeo-specific MUST fields.

### Why this block

Empirical observation : LLM adapters less rigorous than the reference Claude
client partially apply the procedure body. They retain fields explicitly
named in the local section they read but skip universal fields not
enumerated locally — even when the universal block is INCLUDEd. Result :
batches of atoms produced with `scope`, `collective`, `modality`, `branch`,
`source_doc_hash`, `context_origin` silently missing — the YAML parses fine
without them, so the defect goes undetected at write time and is only
surfaced later by the round-trip mismatch (atoms unrecognised by
`mem_recall`, mis-rendered by Obsidian's graph view, flagged by the new
health-scan categories below).

This block is the **single checklist** an LLM agent (or a Python writer) must
walk before writing any archeo atom. If a field is not in this list, it must
not be added ; if a field is in this list and absent in your candidate atom,
the atom is malformed.

### MUST fields by source

The table below is the canonical contract. Every column with `MUST` means the
field is **required**, never omitted, never `null`, never a missing key —
explicitly set with the listed value (or empty string `""` / empty list `[]`).

| Field | universal `_frontmatter-universal` | source: archeo-context | source: archeo-stack | source: archeo-git (archive) | source: archeo-git (derived atom) | type: repo-topology |
|---|---|---|---|---|---|---|
| `date` | MUST | MUST | MUST | MUST (commit date or window start) | MUST | MUST (last scan) |
| `zone` | MUST | MUST | MUST | MUST `episodes` | MUST | MUST `meta` |
| `scope` | MUST (`personal\|work`) | MUST | MUST | MUST | MUST | — (meta is neutral) |
| `collective` | MUST (default `false`) | MUST | MUST | MUST | MUST | — |
| `modality` | MUST (`left\|right`, default `left`) | MUST `left` | MUST `left` | MUST `left` | MUST `left` | — |
| `type` | yes | MUST `principle\|architecture\|procedure\|goal\|person` per category | MUST `architecture` | MUST `archive` | MUST per zone (principle/architecture/goal) | MUST `repo-topology` |
| `project` | yes (or `domain`) | MUST | MUST | MUST | MUST | MUST |
| `tags` | MUST | MUST + `category/{cat}` + zone-specific (force/, horizon/, status/, adr/, etc.) | MUST + `detected_layer/{layer}` | MUST | MUST + same zone-specific tags as Phase 1 | MUST |
| `display` | recommended | MUST | MUST | MUST | MUST | MUST |
| `source` | — | MUST `archeo-context` | MUST `archeo-stack` | MUST `archeo-git` | MUST `archeo-git` | (n/a) |
| `source_doc` | — | MUST (path relative to repo) | — | — | — | — |
| `source_doc_hash` | — | **MUST** (SHA-256 of the doc text — idempotence key) | — | — | — | — |
| `source_manifest` | — | — | MUST (manifest path that drove resolution) | — | — | — |
| `detected_layer` | — | — | MUST (`frontend\|backend\|db\|ci\|infra\|tests\|tooling\|other`) | — | — | — |
| `detected_techno` | — | — | MUST (list, possibly empty `[]`) | — | — | — |
| `extracted_category` | — | **MUST** (`workflow\|sync\|multi-tenant\|security\|adr\|goal\|other`) | — | — | **MUST** (same enum) | — |
| `context_origin` | — | **MUST** `"[[99-meta/repo-topology/{slug}]]"` | **MUST** `"[[99-meta/repo-topology/{slug}]]"` | — | **MUST** `"[[<milestone-archive-name-without-md>]]"` | — |
| `content_hash` | — | MUST (SHA-256 of body, LF-normalised, UTF-8 no BOM) | MUST | MUST | MUST | MUST |
| `previous_atom` | — | MUST `''` first write, set on revisions | MUST | MUST | MUST | — |
| `previous_topology_hash` | — | — | — | — | — | MUST `''` first scan |
| `branch` | — | MUST `''` standard mode, set in branch-first | MUST `''` | **MUST** `''` standard, branch name in branch-first | **MUST** `''` standard, branch name in branch-first | — |
| `branch_base` | — | — | — | MUST `''` standard, ref in branch-first | — | — |
| `branch_base_sha` | — | — | — | MUST `''` standard, sha in branch-first | — | — |
| `milestone_kind` | — | — | — | MUST (`tag\|release\|merge\|window`) | — | — |
| `source_milestone` | — | — | — | MUST (e.g. `v0.8.0`, `release-v0.8.0`, `pr-#42`, `window-2026-W18`) | MUST (same as parent archive) | — |
| `commit_sha` | — | — | — | MUST (or `''` for window with multiple commits — then use `source_commits`) | MUST (the milestone's anchor commit) | — |
| `friction_detected` | — | — | — | MUST (bool) | — | — |
| `topology_snapshot_hash` | — | — | — | MUST `''` unless triggered from `mem-archive` full-mode | — | — |
| `granularity` | — | — | — | MUST (`window\|by-author\|by-merge\|tag\|release\|merge`) | — | — |
| `derived_atoms` | — | — | — | **MUST** (list of `[[wikilink]]` to atoms produced by this milestone — `[]` if none) | — | — |
| `repo_path` | — | — | — | — | — | MUST |
| `repo_remote` | — | — | — | — | — | MUST (or `''`) |
| `last_archive` | — | — | — | — | — | MUST (last archive filename, `''` if no Phase 3 yet) |
| `horizon` | — | (only when `extracted_category: goal`) MUST `short\|medium\|long` | — | — | (idem) MUST | — |
| `status` | — | (only when `extracted_category: goal`) MUST `open\|in-progress\|done\|abandoned` | — | — | (idem) MUST | — |
| `force` | — | (only when atom is a principle) MUST `red-line\|heuristic\|preference` | — | — | (idem) MUST | — |
| `sources` | — | (optional list of secondary doc references) | — | — | — | — |

### Tag mirror — exhaustive checklist

`tags:` must redundantly mirror the structural frontmatter fields. Always
include these (per atom kind) :

- **Always** (any zone except inbox/meta) : `zone/{zone}`, `scope/{scope}`,
  `modality/{modality}`, `project/{slug}` (or `domain/{slug}`).
- **type-specific** : `type/{type}` (e.g. `type/architecture`, `type/principle`).
- **archeo source** : `source/{source}` (e.g. `source/archeo-context`).
- **principles** : `force/{force}`.
- **goals** : `horizon/{horizon}`, `status/{status}`.
- **ADR (when `extracted_category: adr`)** : `category/adr`, `adr/{status}`
  (typically `adr/accepted` for newly archived ADRs).
- **archeo extracted category** : `category/{extracted_category}`.
- **archeo-stack** : `detected_layer/{layer}`.
- **archeo-git archives** : `kind/archive`.

A finding in `mem-health-scan` flags any frontmatter where the `tags:` list
does not redundantly mirror the structural fields enumerated above.

### Pre-write checklist (LLM walkthrough)

Before invoking the router with a candidate atom, walk this checklist line by
line. If any answer is `no`, do not write — fix the candidate first.

```
[ ] date present and YYYY-MM-DD format ?
[ ] zone matches the target folder ?
[ ] scope is personal | work ?
[ ] collective is bool (default false) ?
[ ] modality is left | right ?
[ ] type is set per the table above ?
[ ] project (or domain) is set ?
[ ] source is exactly one of: archeo-context | archeo-stack | archeo-git ?
[ ] all source-specific MUST fields are present per the table ?
[ ] context_origin points to the correct anchor ?
    - archeo-context / archeo-stack -> [[99-meta/repo-topology/{slug}]]
    - archeo-git derived atom       -> [[<milestone-archive-name>]]
[ ] branch is "" (empty string) at minimum, never null, never missing ?
[ ] tags redundantly mirror all structural fields ?
[ ] display is set per _frontmatter-universal conventions ?
[ ] content_hash is the SHA-256 of the body (LF-normalised, UTF-8 no BOM) ?
[ ] previous_atom is "" (empty string) on first write ?
```

### Forbidden patterns

The following frontmatter shapes are **bugs** and must be rejected by the
writer (LLM or Python) :

- `previous_atom:` with no value (parses as `null` — write `previous_atom: ''` explicitly).
- `branch:` missing entirely (write `branch: ''` explicitly even out of branch-first mode).
- `source: archeo-git` on a transverse atom (`40-principles/`, `20-knowledge/`,
  `50-goals/`) **without** the matching milestone archive listing this atom in
  its `derived_atoms:` field. The link must be bidirectional.
- `source: archeo-git` on a transverse atom **without** `context_origin`
  pointing to the milestone archive.
- `source: archeo-git` on a file in `10-episodes/.../archives/` **without**
  the full archive frontmatter (milestone_kind, source_milestone, commit_sha,
  granularity, etc.).
- Frontmatter delimiter `---` glued to the first key (e.g. `---project: <slug>`
  on line 1). The opening `---` must be on its own line.
- Any duplicated top-level YAML key (`source: …` twice, etc.).
