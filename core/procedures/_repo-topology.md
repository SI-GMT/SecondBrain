## Repo topology — Phase 0 scan (shared block)

This block is included via `{{INCLUDE _repo-topology}}` by the four `mem-archeo*` skills (`mem-archeo-context`, `mem-archeo-stack`, `mem-archeo-git`, `mem-archeo` orchestrator) and by `mem-archive` full-mode (to refresh the persisted topology of the project's repo, when one is associated).

The goal is to build a **structural map** of a Git repository — where the sources are, where the docs are, where the configuration lives, what stack is detectable from manifests, what AI files are present. Each phase consumes the relevant slice of this map without re-scanning, so the three phases share a single ground truth.

### T0. Inputs

The caller passes:
- `{repo-path}` — absolute path to the repo root (must contain `.git/`).
- `{depth}` — maximum recursion depth for non-special folders. Default `2`. Special folders (`docs/`, `cadrage/`, `adr/`, `rfc/`, `src/` and their conventional siblings) are recursed up to depth `4`.

### T1. Standard exclusions

Always skip these directories during the scan, regardless of depth:

```
.git/  .hg/  .svn/  .idea/  .vscode/  .vs/  node_modules/  bower_components/
target/  dist/  build/  out/  .next/  .nuxt/  .output/  .turbo/  .cache/
__pycache__/  .pytest_cache/  .mypy_cache/  .ruff_cache/  .tox/  venv/  .venv/  env/  .env/
vendor/  Pods/  DerivedData/  .gradle/  bin/  obj/
coverage/  .nyc_output/  .coverage/
```

These are build artifacts, dependency caches, IDE metadata. They never carry topology-relevant signal and they dramatically inflate scan time.

### T2. Categories detected

The scan classifies each top-level entry of the repo into one of the categories below. An entry can fit multiple categories (e.g. `README.md` is both `docs` and `ai_files` in spirit; classify under all that apply).

| Category | What goes here | Detection heuristics |
|---|---|---|
| `sources` | Application code, libraries | `src/`, `source/`, `sources/`, `lib/`, `app/`, `apps/{name}/src/`, language-typed (`.py`, `.ts`, `.go`, `.rs`, `.java`, `.cs`) at root |
| `docs` | Project documentation | `docs/`, `documentation/`, `cadrage/`, `specs/`, `adr/`, `rfc/`, `wiki/`, `*.md` at root other than `CHANGELOG.md` |
| `ai_files` | LLM agent files | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `.cursorrules`, `.windsurfrules`, `.aider.conf.yml` |
| `readme` | Entry-point overview | `README.md`, `README.rst`, `README.txt` |
| `changelog` | Release log | `CHANGELOG.md`, `CHANGES.md`, `HISTORY.md`, `RELEASES.md`, `NEWS.md` |
| `config` | Runtime configuration | `.env.example`, `.env.sample`, `config/`, `settings/`, `*.config.{js,ts,json}` at root, `pyproject.toml` (also `manifests`) |
| `tests` | Test suites | `tests/`, `__tests__/`, `test/`, `spec/`, `e2e/`, `cypress/`, `playwright/` |
| `ci` | CI / CD config | `.github/workflows/`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `Jenkinsfile`, `.circleci/`, `.drone.yml` |
| `infra` | Containers, IaC | `Dockerfile*`, `docker-compose*.yml`, `compose.yml`, `Makefile`, `terraform/`, `pulumi/`, `infrastructure/`, `k8s/`, `helm/`, `kustomize/`, `ansible/` |
| `manifests` | Package / build manifests | `package.json`, `pyproject.toml`, `requirements*.txt`, `Pipfile`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`, `pom.xml`, `build.gradle*`, `*.csproj`, `mix.exs`, `pubspec.yaml` |
| `lockfiles` | Pinned deps | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`, `Cargo.lock`, `poetry.lock`, `uv.lock`, `Gemfile.lock`, `composer.lock`, `pubspec.lock` |
| `git_meta` | Git conventions | `.gitignore`, `.gitattributes`, `.git-blame-ignore-revs`, `.gitmodules` |
| `editor` | Tooling configs to surface (kept, not excluded) | `.editorconfig`, `.pre-commit-config.yaml`, `.eslintrc*`, `.prettierrc*`, `pyproject.toml` (sections `[tool.*]`), `tsconfig*.json` |
| `license` | Legal | `LICENSE*`, `COPYING*`, `NOTICE*` |

A directory or file that matches none of the above and is not excluded by T1 falls into `other` — surfaced in the topology but not actively consumed.

### T3. In-memory topology shape

The scan produces a structured representation that fits in the LLM's working context. Conceptually:

```
topology = {
    "repo_path": "/Users/ben/Projets/Kintsia",
    "repo_remote": "git@github.com:org/kintsia.git",   # via `git remote get-url origin`, empty if absent
    "scanned_at": "2026-05-01T14:22:00Z",
    "depth_limit": 2,                                   # the value used for this scan

    "categories": {
        "sources":   ["src/", "lib/"],
        "docs":      ["docs/", "cadrage/", "adr/"],
        "ai_files":  ["CLAUDE.md", "AGENTS.md", "GEMINI.md"],
        "readme":    ["README.md"],
        "changelog": ["CHANGELOG.md"],
        "config":    [".env.example", "config/"],
        "tests":     ["tests/"],
        "ci":        [".github/workflows/"],
        "infra":     ["Dockerfile", "docker-compose.yml"],
        "manifests": ["package.json", "pyproject.toml"],
        "lockfiles": ["pnpm-lock.yaml", "uv.lock"],
        "git_meta":  [".gitignore", ".gitattributes"],
        "editor":    [".editorconfig", ".pre-commit-config.yaml"],
        "license":   ["LICENSE"],
        "other":     ["scripts/", "tools/"]
    },

    "stack_hints": {
        # filled by lightweight heuristics on manifests — not a full resolution.
        # Phase 2 (mem-archeo-stack) does the deep resolution.
        "frontend": ["Next.js"],         # detected via package.json deps
        "backend":  ["Python", "FastAPI"], # detected via pyproject.toml + deps
        "db":       [],
        "lang":     ["typescript", "python"]
    }
}
```

Pass this object as a structured field of the calling skill's working memory (not as an atom file at this stage — persistence is the responsibility of `mem-archive` full-mode and the `mem-archeo` orchestrator, not of this Phase 0 block).

### T4. Stack hints (lightweight pre-resolution)

Phase 0 does **not** resolve the stack in depth (that's Phase 2's job). It only fills `stack_hints` with cheap heuristics that the other phases can rely on:

- If `package.json` exists, parse its `dependencies` / `devDependencies` keys (no version semantics) and tag known framework markers:
  - `next` → frontend Next.js
  - `react` → frontend React
  - `vue` → frontend Vue
  - `nuxt` → frontend Nuxt
  - `svelte` / `@sveltejs/kit` → frontend Svelte / SvelteKit
  - `express`, `fastify`, `koa`, `nestjs` → backend Node
- If `pyproject.toml` or `requirements*.txt` exists, read it and tag:
  - `fastapi`, `flask`, `django`, `aiohttp`, `starlette` → backend Python
  - `pytorch`, `tensorflow`, `transformers` → ML stack
- If `Cargo.toml` → tag `lang: rust` and look at `[dependencies]` for `axum`, `actix-web`, `rocket`.
- If `go.mod` → tag `lang: go`, look for `github.com/gin-gonic/gin`, `gorilla/mux`, etc.
- If `Dockerfile` → tag the base image's language family (`FROM python:`, `FROM node:`, etc.).

These are **hints, not commitments**. Phase 2 does the authoritative classification. The hints help Phase 1 contextualize the docs (e.g. it knows the project is Next.js + FastAPI before it reads any `cadrage/`).

### T5. Reading AI files at scan time

For each detected `ai_files` entry **and** the README, also read its current content (latest commit, not historical). Hold it in working memory keyed by filename. Phases 1, 2, 3 all need this and the cost of re-reading three times is wasteful.

When invoked from `mem-archeo-git` for a historical milestone, AI files are read via `git show {sha}:{file}` for the time of the commit — that's a different responsibility, handled at Phase 3 step 4b, not here. This Phase 0 always reads the current HEAD.

### T6. Persistence (when applicable)

Phase 0 itself does not write the persisted topology file. It produces the in-memory object. The persistence is handled by:

- **`mem-archeo` orchestrator** at the end of a full run — writes `99-meta/repo-topology/{slug}.md`.
- **`mem-archive` full-mode** at step 4.5 — refreshes the same file if the project has a `repo_path` and the topology has evolved.

The persisted form follows the schema defined in `docs/architecture/v0.7.0-archeo-and-base-skills-alignment.md` §2. **Mandatory frontmatter fields**:

```yaml
date: <YYYY-MM-DD>
zone: meta
type: repo-topology
project: <slug>
repo_path: <absolute-path>
repo_remote: <url-or-empty>
content_hash: <sha256-of-body>          # MUST — SHA-256 of the body Markdown after the frontmatter, used by R10 idempotence
previous_topology_hash: <sha256-or-empty>   # MUST — empty string "" on first snapshot, never omitted
last_archive: <wikilink-or-empty>
tags: [zone/meta, type/repo-topology, project/<slug>]
```

`content_hash` and `previous_topology_hash` are **never omitted** — empty values are written as `""`, never as missing keys. The hash is computed on the body **after** the frontmatter (everything from the first `# Topology` line onward), normalized to LF + UTF-8 without BOM before hashing.

When a persisted topology already exists for the project and the caller wants a **fresh scan**, the caller must explicitly opt in (e.g. orchestrator's `--rescan` flag). Otherwise the persisted topology is loaded and used as-is, which is faster.

### T7. Failure modes

- **Not a Git repo** (`git -C {repo-path} rev-parse --git-dir` fails): abort with a clear error. The 3 phases all require Git.
- **Empty repo** (no commits): allow the scan, but flag `stack_hints: {}` and warn the caller. Phase 3 will fail later with an empty history; Phases 1 and 2 may still run if files exist on disk.
- **Permission denied** on a subfolder: skip that subfolder, log a warning, continue. Do not abort.
- **Symlink loops**: bounded by depth limit; if a loop is detected before the limit, log and stop recursing into that branch.

### T8. Performance contract

A typical repo (~500 files at root + first level) should scan in < 2 seconds with depth 2. A monorepo with a `packages/` or `apps/` subfolder containing many sub-projects should still scan in < 10 seconds — the standard exclusions remove the bulk (`node_modules`, build dirs).

If a scan exceeds 30 seconds, the caller should consider:
- Increasing the exclusion list (project-specific via a `.archeoignore` file, future v0.7.x).
- Lowering the depth limit to 1 (loses some structure detection but stays usable).
