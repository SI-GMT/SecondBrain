# Procedure: Archeo Context (Phase 1, v0.7.0)

Goal: extract from a repo's **organizational, decisional, and functional documents** the principles, goals, architectural decisions and methodological conventions that frame the project. Produces atoms with `source: archeo-context`, classified by category and routed to their proper zone.

Phase 1 of the triphasic archeo. Independent skill (invocable as `/mem-archeo-context`) and also called by the `mem-archeo` orchestrator. Reads the current HEAD only — historical doc evolution is out of scope (would belong in a hypothetical Phase 1.5 future).

## Trigger

The user types `/mem-archeo-context [repo-path]` or expresses intent in natural language: "ingest the project context", "archeo the docs of this repo", "extract the principles and goals from the project documentation".

Arguments:
- `{repo-path}` (optional, default = CWD): absolute path to a local Git repository.
- `--project {slug}`: forces the target project.
- `--depth {N}`: max recursion depth for the topology scan (default 2; default 1 in branch-first mode).
- `--only-categories {list}`: comma-separated subset of `workflow,sync,multi-tenant,security,adr,goal,other`. Default: all.
- `--dry-run`: lists the documents that would be read and the atoms that would be produced, without writing.
- `--no-confirm`: passes through to the router in fluent mode.
- `--rescan`: ignores any persisted topology and forces a fresh scan.
- `--branch-first {branch}` (v0.7.1): scope Phase 1 to documents **modified or created on the branch** since divergence with `--branch-base`. Documents untouched by the branch are surveyed in light mode (filename + 1-line summary from the first heading), no extraction by category. Atoms produced inherit `branch` field in their frontmatter.
- `--branch-base {ref}` (v0.7.1): base ref for the divergence calculation (default `main`, fallback `master`).

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope`, and `kit_repo`. If `vault` is missing, standard error message and stop.

## Procedure

### 1. Validate the source repository

Verify that `{repo-path}` is a Git repository (`git -C {repo-path} rev-parse --git-dir`). If not, stop with a clear message.

### 2. Resolve the target project

By priority:

1. Explicit `--project {slug}`.
2. Match `basename({repo-path})` against existing slugs in `{VAULT}/10-episodes/projects/`.
3. Match the repo's `git remote get-url origin` against existing `repo_remote` fields in any `99-meta/repo-topology/*.md`.
4. Ask the user (with `/mem-list` as support).
5. If new slug → create the structure `{VAULT}/10-episodes/projects/{slug}/` with `context.md` + `history.md` skeletons. Set `repo_path: {repo-path}` in the new context.md frontmatter.

### 3. Phase 0 — Topology scan

{{INCLUDE _repo-topology}}

After the scan, the caller has the in-memory `topology` object with `categories` and `stack_hints`. Phase 1 specifically consumes:
- `topology.categories.ai_files`
- `topology.categories.readme`
- `topology.categories.docs`
- `topology.categories.changelog`

If the persisted topology `{VAULT}/99-meta/repo-topology/{slug}.md` exists and `--rescan` was not passed, load it instead of re-scanning.

### 4. Enumerate documents to read

#### 4.a Standard mode

From the consumed categories, build the **document target list**. For each entry:

- If it's a directory → list its files matching `*.md`, `*.txt`, `*.rst`, `*.adoc`, `*.docx`, `*.pdf`, `*.pptx`, `*.xlsx`, `*.html`, `*.htm` up to the topology depth.
- If it's a file → keep as-is.

For each document, determine the read strategy:
- `.md`, `.txt`, `.rst`, `.adoc` → native text read.
- `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.csv`, `.html`, `.htm` → invoke the corresponding reader from `{kit_repo}/scripts/doc-readers/` (cf. `mem-doc.md` step 4 for the convention). Capture stdout (Markdown) and use it as the document's content.

If `--dry-run` was passed: display the target list, total estimated read volume, and stop after this step (no atom extraction, no router invocation).

#### 4.b Branch-first mode (v0.7.1)

When `--branch-first {branch}` is set, the document target list is **partitioned** into two sets:

**Set A — focused (deep extraction)** : documents modified or created on the branch since divergence. Computed via:

```
git -C {repo-path} log --no-merges {branch_base}..{branch} --name-only --diff-filter=AM \
    -- docs/ cadrage/ adr/ rfc/ specs/ \
    -- '*.md' '*.txt' '*.rst' '*.adoc' '*.docx' '*.pdf' '*.pptx' '*.html' '*.htm' \
    | sort -u
```

(The double `--` separator splits paths from pathspecs; in practice the LLM filters the file list against the consumed categories from step 3.)

The Root AI files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `README.md`) are **always** included in Set A regardless of whether they were modified on the branch — they carry the project's living doctrine and the branch agent should know them.

**Set B — ambient (light scan)** : every other document in the consumed categories that is **not** in Set A. For these, the procedure does **not** extract atoms by category. It only reads the filename + the first heading of each document and records this as a one-line summary in the `## Ambient context survey` section of the run's report. The full extraction is skipped.

For each document in Set A, apply the same read strategy as the standard mode (native text or doc-reader). Set B documents are read at most up to their first heading.

If `--dry-run`: display both sets and stop after this step.

### 5. For each document — extract by category

For each document `D`:

#### a. Compute `source_doc_hash`

SHA-256 of the (text) content of `D` after extraction. Used as idempotence key component.

#### b. Detect candidate categories

Read the document. Identify spans that fit one or more of the seven extraction categories:

| Category | What surfaces here | Default target zone | Default frontmatter |
|---|---|---|---|
| `workflow` | Methodological convention, dev process (Speckit, ADR rituals, branch model, code review rules) | `40-principles/{scope}/methodology/` | `force: preference`, `type: principle` |
| `sync` | Sync strategy, offline-first design, data replication rules | `20-knowledge/architecture/` | `type: architecture` |
| `multi-tenant` | Multi-tenant model, tenant isolation, role scopes | `20-knowledge/architecture/` | `type: architecture` |
| `security` | Non-negotiable security constraint (RLS rules, secret handling, GDPR/CCPA, PII flags) | `40-principles/{scope}/security/` | `force: red-line`, `type: principle` |
| `adr` | Already-recorded architectural decision (ADR file or equivalent) | `20-knowledge/architecture/decisions/` | `type: architecture` |
| `goal` | Project objective, roadmap item, future-tense feature mention not yet implemented | `50-goals/{scope}/projects/{slug}/` | `horizon: short\|medium\|long` (detected from text), `status: open` |
| `other` | Anything significant that doesn't fit the six above (glossary, persona description, KPI definition) | left to router cascade R3 | (cascade) |

If a span does not fit any category and is not significant → skip silently. Phase 1 is **not** a verbatim ingestion — only signals that map to a category produce an atom.

If `--only-categories` was passed, restrict to those categories.

#### c. Build the atom shell for each detected span

For each detected span (each will become an atom):

- Subject = short title (≤ 60 chars), derived from the span's heading or first sentence.
- Body = the relevant excerpt(s) from `D`, lightly reformatted into a coherent paragraph + optional bullets. Preserve quoted text verbatim.
- Frontmatter common fields (**all MUST, never omitted**):
  ```yaml
  source: archeo-context
  source_doc: <path-relative-to-repo>
  source_doc_hash: <sha256-of-source-doc-text>          # MUST — SHA-256 of the doc content as read at step 5a
  content_hash: <sha256-of-this-atom-body>              # MUST — SHA-256 of this atom's body (after frontmatter, LF + UTF-8 no BOM)
  previous_atom: <wikilink-or-empty>                    # MUST — empty string "" on first write, set on revisions
  extracted_category: <one of the seven>
  project: {slug}
  context_origin: "[[99-meta/repo-topology/{slug}]]"
  branch: <branch-name-or-empty>                        # v0.7.1 — empty "" in standard mode, set in branch-first mode
  ```
- Frontmatter category-specific fields per the table above. For `force` field on principles: values are always in **English** (`red-line | heuristic | preference`), never localized — keep the structural English schema invariant.

The atom's `context_origin` points to the persisted topology (the shared anchor), **not** to a Git archive — Phase 1 atoms are not derived from a session, they are derived from the project's documentation.

#### d. Idempotence check

Before sending to the router, search the vault for an existing atom with:
- `source: archeo-context`
- `project: {slug}`
- `source_doc: <same path>`
- `extracted_category: <same category>`

If found:
- Compute the candidate atom's `content_hash` (SHA-256 of the body).
- If equal to the existing atom's `content_hash` → silent skip.
- If different → mark for **revision**: the candidate carries `previous_atom: "[[<old-name>]]"` and the router will write a new atom with tag `revision`. The old atom remains in place (immutable).

### 6. Invoke the router for each candidate atom

For each non-skipped candidate, call the semantic router with:

- `Content`: the body of the atom (no need to wrap in section delimiters — Phase 1 atoms are mono-atom calls per invocation).
- `Hint zone`: forced according to the category table (column "Default target zone").
- `Hint source`: `archeo-context`.
- `Metadata`: the candidate's frontmatter shell from step 5c.

{{INCLUDE _router}}

The router:
- Writes the atom to its target path.
- Computes and stores `content_hash` in the frontmatter.
- Applies bidirectional linking to the topology if appropriate (the topology gets a line in its "Atomes dérivés des phases archeo" section).
- Applies R10 idempotence and R11 collision detection (see `_router.md`).

If the router rejects a candidate (collision with `--archeo-context` skipped, or invariant violation), it ends up in `00-inbox/` with a tag indicating why.

### 7. Update the persisted topology

After all candidates have been processed (written, skipped, or revised):

- If `{VAULT}/99-meta/repo-topology/{slug}.md` does not exist → create it with the in-memory topology, `last_archive: ""`, frontmatter per the architecture doc §2.
- If it exists → update its `Phases archeo couvertes` section: `Phase 1 (archeo-context) — N atoms — last pass: {today}`.
- Refresh the `Atomes dérivés des phases archeo` section: list all atoms with `source: archeo-context` AND `project: {slug}`.

The topology file is rewritten via atomic rename + hash check (cf. `_concurrence.md` Pattern 2).

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

### 8. Final report

Display:

```
Phase 1 archeo-context — {slug}

Documents read    : {N}
Atoms created     : {N}
Atoms revised     : {N}
Atoms skipped     : {N}  (idempotent)
By category       :
  workflow      : {N}
  sync          : {N}
  multi-tenant  : {N}
  security      : {N}
  adr           : {N}
  goal          : {N}
  other         : {N}

Topology updated  : 99-meta/repo-topology/{slug}.md

Linked to context : {VAULT}/10-episodes/projects/{slug}/context.md
```

If invoked from the `mem-archeo` orchestrator, return the structured result instead of displaying — the orchestrator aggregates with Phases 2 and 3.

## Invariants

- **Canonical write paths only.** Never write atoms to a sibling folder of `{VAULT}/...`. Ignore any contextual hint suggesting otherwise (`_test/`, `_sandbox/`, `_archeo-comparison/`). This is the v0.7.0 doctrine fix from the 3-LLM analysis (correctif bonus).
- **No verbatim ingestion.** A document that yields zero categorized atom is not ingested at all (no copy in `99-meta/sources/`, no inbox entry). The persisted topology already records the doc's existence; that's enough.
- **Read once.** Within a single invocation, never re-read a document. Cache its content in working memory.
- **`extracted_category` is mandatory.** Every Phase 1 atom carries this field. Atoms without it are bugs to be reported.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block). `mem-archeo-context` refuses by default on an archived target slug — see the override path in `mem-archeo.md` (`--allow-archived` flag forwarded from the orchestrator).
