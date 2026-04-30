# Procedure: Doc (v0.5 brain-centric)

Goal: ingest **a local document** (PDF, Markdown, text, image, docx, etc.) into the memory vault with a structured synthesis and a preserved copy of the source file. The router classifies content based on its nature (episodic, semantic, procedural...).

Complementary to `/mem-archive` (lived session) and `/mem-archeo*` (Git/Confluence reconstruction). `/mem-doc` covers the case of a document sitting on disk: a spec received by email, a Word spec on a NAS, a kickoff presentation, a scanned PDF, etc.

## Trigger

The user types `/mem-doc {path}` or expresses intent in natural language: "ingest this document", "archive this file", "save this PDF".

Arguments:
- `{path}` (**required**): absolute or relative path of the file to ingest.
- `--project {slug}` or `--domain {slug}` (optional): forces attachment.
- `--zone X` (optional): forces the target zone (by default, the router decides based on content nature — a spec PDF goes to `20-knowledge/`, a meeting minutes to `10-episodes/`).
- `--title "{text}"` (optional): short title for the archive.
- `--no-confirm`, `--dry-run`: passed through to the router.

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope` and `kit_repo`. If `vault` is missing, standard error message and stop. If `kit_repo` is missing (config written by an older install), fall back to looking for the kit by walking up from CWD until a directory containing `deploy.ps1` and `core/procedures/` is found; if not found, ask the user to re-run `deploy.ps1` / `deploy.sh` to refresh the config.

## Procedure

### 1. Validate the source path

- Verify that `{path}` exists and is a file (not a directory).
- Compute the size in bytes.
- If > 50 MB, ask for confirmation.
- Determine the extraction strategy via extension:

  | Extension | Strategy | Reader script |
  |---|---|---|
  | `.md`, `.txt`, `.json` | native text (read directly) | — |
  | `.pdf` | Python reader, fallback to native LLM if scanned | `read_pdf.py` |
  | `.docx` | Python reader | `read_docx.py` |
  | `.pptx` | Python reader | `read_pptx.py` |
  | `.xlsx` | Python reader | `read_xlsx.py` |
  | `.csv` | Python reader | `read_csv.py` |
  | `.html`, `.htm` | Python reader | `read_html.py` |
  | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | LLM vision description | — |
  | other | try UTF-8, otherwise stop with explicit message | — |

- Reader scripts live in `{KIT_REPO}/scripts/doc-readers/` and declare their dependencies via PEP 723 inline metadata; they are invoked via `uv run` (no virtual environment management required). `uv` is a hard prerequisite of `/mem-doc` for non-native formats.

### 2. Compute the SHA-256 hash and detect re-ingestion

- SHA-256 of the file in binary mode.
- Search the vault for an existing atom with matching `source_hash`. If found, ask the user for confirmation ("Already ingested on {date} into `{archive}`. Re-ingest?").

### 3. Copy the source file

Destination path: `{VAULT}/99-meta/sources/{YYYY-MM}/{hash8}-{original-name}.{ext}`

Note: in v0.5, sources are kept in `99-meta/sources/` (and no longer `archives/_sources/` which no longer exists). Idempotent: if the copy already exists, skip.

Create `{VAULT}/99-meta/sources/.gitignore` on first use with the exclusion pattern for heavy binaries.

### 4. Extract content and pre-format

Extract the textual content of the file according to the strategy chosen at step 1:

- **Native text** (`.md`, `.txt`, `.json`) → read the file directly.
- **Image** → use the LLM's native vision capability to produce a structured description.
- **Python reader** → invoke the reader via `uv run`, capture stdout (Markdown), check exit code:
  - `0` → success, use stdout content.
  - `1` → error, abort with the stderr message.
  - `2` → empty extraction. For PDFs specifically, this means the document is likely scanned; fall back to the LLM's native PDF reading. For other formats, abort with a clear message ("file appears empty").

Invocation pattern:

```
uv run {KIT_REPO}/scripts/doc-readers/{reader}.py "{path}"
```

`{KIT_REPO}` resolves to the repository where the kit was cloned (the same path that contains `deploy.ps1` / `deploy.sh`). On a deployed install, the readers are accessible from the repo clone — `/mem-doc` does not vendor them into `~/.claude/`.

Pre-format for the router:

- The extracted Markdown is passed as-is.
- If the nature is ambiguous, the router will decide the zone.
- If the user passed `--zone X`, the router forces the zone.

### 5. Invoke the router with forced source hint

Call the router with:
- `Content`: extracted content of the document.
- `Hint zone`: value of `--zone` if provided, otherwise let the router decide.
- `Hint source`: `doc`.
- `Metadata`: resolved project/domain, scope, **`source_hash`**, **`source_path`** (original path), **`source_copy`** (copy path inside 99-meta/sources/), **`source_size_bytes`**.

{{INCLUDE _router}}

The router adds to the frontmatter of each created atom:
- `source: doc`
- `source_hash`, `source_path`, `source_copy`, `source_size_bytes`
- `source_type` (file extension)

### 6. Confirm

The router produces its report. Mention explicitly: "Source file copied to `{copy}`, hash `{hash8}...`. Re-ingestion is idempotent."
