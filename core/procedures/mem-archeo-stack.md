# Procedure: Archeo Stack (Phase 2, v0.7.0)

Goal: extract from a repo's **technical manifests, infrastructure, CI/CD and configuration** the resolved stack, the patterns of interoperability between layers, and the tooling conventions. Produces atoms with `source: archeo-stack`, classified by layer and routed to `20-knowledge/architecture/` (and occasionally `40-principles/{scope}/conventions/`).

Phase 2 of the triphasic archeo. Independent skill (invocable as `/mem-archeo-stack`) and also called by the `mem-archeo` orchestrator. Reads HEAD only.

## Trigger

The user types `/mem-archeo-stack [repo-path]` or expresses intent in natural language: "ingest the stack of this project", "extract the technical context", "archeo the deps and infra".

Arguments:
- `{repo-path}` (optional, default = CWD): absolute path to a local Git repository.
- `--project {slug}`: forces the target project.
- `--depth {N}`: max recursion depth for the topology scan (default 2; default 1 in branch-first mode).
- `--only-layers {list}`: comma-separated subset of `frontend,backend,db,ci,infra,tests,tooling,other`. Default: all detected.
- `--dry-run`, `--no-confirm`, `--rescan`: as in `mem-archeo-context`.
- `--branch-first {branch}` (v0.7.1): scope Phase 2 to **manifests modified on the branch** since divergence with `--branch-base`. Layers untouched by the branch are summarized in a single ambient atom that links to the main topology. Atoms produced inherit `branch` field in their frontmatter.
- `--branch-base {ref}` (v0.7.1): base ref for the divergence calculation (default `main`, fallback `master`).

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope`, and `kit_repo`. If `vault` is missing, standard error message and stop.

## Procedure

### 1. Validate the source repository

Same as `mem-archeo-context` step 1.

### 2. Resolve the target project

Same as `mem-archeo-context` step 2.

### 3. Phase 0 — Topology scan

{{INCLUDE _repo-topology}}

Phase 2 specifically consumes:
- `topology.categories.manifests`
- `topology.categories.lockfiles` (used as signal, not parsed in depth)
- `topology.categories.infra`
- `topology.categories.ci`
- `topology.categories.tests`
- `topology.categories.editor`
- `topology.categories.config`
- `topology.categories.sources` (for layer-presence inference)
- `topology.stack_hints` (already filled by Phase 0)

### 3.1. Branch-first scoping (v0.7.1)

When `--branch-first {branch}` is set, the layer resolution at step 4 is **scoped** to manifests modified on the branch:

1. Identify modified manifests on the branch:
   ```
   git -C {repo-path} log --no-merges {branch_base}..{branch} --name-only --diff-filter=AM \
       | grep -E '(package\.json|pyproject\.toml|requirements.*\.txt|Pipfile|Cargo\.toml|go\.mod|composer\.json|Gemfile|pom\.xml|build\.gradle.*|.*\.csproj|mix\.exs|pubspec\.yaml|Dockerfile.*|docker-compose.*\.yml)$' \
       | sort -u
   ```
2. Map each modified manifest to its layer (per the manifest-to-layer rules of step 4).
3. Resolve **only** the layers whose manifests appear in this set. Layers untouched on the branch are skipped from full resolution.
4. **Workspaces awareness** : if `topology.branch_focus.touched_workspaces` is non-empty (filled by the orchestrator at Phase 0 augmentation), each touched workspace whose `vault_project` is non-empty is added as a **cross-link** in the ambient atom (see step 5.b).

If no manifest was modified on the branch, Phase 2 in branch-first mode produces only the ambient atom (step 5.b) — no per-layer resolution at all.

### 4. Resolve the stack by layer

For each layer in `frontend|backend|db|ci|infra|tests|tooling|other`, build a structured resolution.

#### a. `frontend`

If `package.json` is present and any of `next`, `react`, `vue`, `nuxt`, `svelte`, `@sveltejs/kit`, `solid-js`, `remix`, `astro`, `qwik` is in `dependencies` or `devDependencies`:

- Identify the meta-framework if any (`next`, `nuxt`, `remix`, `astro`, `@sveltejs/kit`).
- Identify the underlying view layer (`react`, `vue`, `svelte`, `solid-js`).
- Identify the styling system (presence of `tailwindcss`, `styled-components`, `emotion`, `sass`, `vanilla-extract`).
- Identify the state layer (`zustand`, `redux`, `pinia`, `jotai`, `recoil`, `@tanstack/react-query`, `swr`).
- Identify the form/validation layer (`react-hook-form`, `formik`, `zod`, `yup`, `valibot`).
- Identify the test layer (`@testing-library/*`, `vitest`, `jest`, `playwright`, `cypress`).

If no `package.json` matches the front-typical markers but `index.html` + a `*.html` heavy structure is at root (rare modern), tag `frontend: vanilla` and skip the rest.

#### b. `backend`

For Python (`pyproject.toml` or `requirements*.txt`):
- Web framework: `fastapi`, `flask`, `django`, `aiohttp`, `starlette`, `quart`, `sanic`.
- ORM/DB: `sqlalchemy`, `tortoise-orm`, `prisma`, `peewee`, `psycopg`, `asyncpg`, `pymongo`, `motor`.
- Validation: `pydantic`, `marshmallow`, `attrs`.
- Auth: `python-jose`, `pyjwt`, `passlib`, `authlib`.
- Background: `celery`, `dramatiq`, `arq`, `huey`.

For Node.js backend (`package.json` with backend markers):
- Web framework: `express`, `fastify`, `koa`, `hapi`, `nestjs`, `hono`.
- ORM: `prisma`, `typeorm`, `sequelize`, `mongoose`, `drizzle-orm`, `kysely`.
- Auth: `passport`, `next-auth`, `lucia-auth`, `jsonwebtoken`.

For Go (`go.mod`):
- Framework: `gin-gonic/gin`, `gorilla/mux`, `labstack/echo`, `gofiber/fiber`.
- ORM: `gorm.io/gorm`, `ent`.

For Rust (`Cargo.toml`):
- Framework: `axum`, `actix-web`, `rocket`, `warp`, `tide`.
- ORM: `diesel`, `sea-orm`, `sqlx`.

For Java/Kotlin (`pom.xml`, `build.gradle*`):
- Framework: Spring Boot, Quarkus, Micronaut, Ktor.

For .NET (`*.csproj`):
- Framework: ASP.NET Core, Minimal APIs.

#### c. `db`

Direct signals first (specific config files): `prisma/schema.prisma`, `drizzle.config.*`, `alembic.ini`, `flyway.conf`, `liquibase.properties`, `migrations/` folder layout.

Indirect signals (deps detected in step b): `psycopg` → PostgreSQL, `mysql-connector` → MySQL, `pymongo`/`mongoose` → MongoDB, `redis-py`/`ioredis` → Redis, `motor` → MongoDB async, `aiosqlite` → SQLite.

Container signals (Phase 0 `infra`): `docker-compose.yml` services with images like `postgres:`, `mysql:`, `mongo:`, `redis:`, `mariadb:`, `elasticsearch:`.

Self-hosted Supabase signal: `docker-compose.yml` with `supabase/`, `kong:`, `postgrest:`, `gotrue:` services → tag specifically (this is the Kintsia case from the analysis 3-LLM).

#### d. `ci`

For each file in `topology.categories.ci`:
- `.github/workflows/*.yml` → list workflow names + triggers (`on: push`, `on: pull_request`, schedules).
- `.gitlab-ci.yml` → list stages.
- `Jenkinsfile` → identify pipeline structure (declarative vs scripted).
- `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `.circleci/config.yml`: similar structural extraction.

Don't dump the raw YAML — produce a 5-line summary per pipeline.

#### e. `infra`

- `Dockerfile` (and `Dockerfile.*`): base image, exposed ports, entrypoint summary.
- `docker-compose.yml`: services list (name + image + ports), networks, volumes.
- `Makefile`: list of phony targets (the project's command surface for newcomers).
- `terraform/` or `pulumi/`: providers detected (`aws`, `gcp`, `azure`, `cloudflare`, `digitalocean`).
- `k8s/`, `helm/`, `kustomize/`: chart name, kind list.
- `ansible/`: roles list.

#### f. `tests`

Test framework markers (already detected per language above) + structural signals:
- `pytest.ini`, `tox.ini`, `conftest.py` → pytest convention.
- `jest.config.*`, `vitest.config.*` → JS test runner.
- `playwright.config.*`, `cypress.config.*`, `e2e/` → end-to-end suite.
- `coverage.xml`, `.coveragerc` → coverage tracking enabled.

Identify test scope: `unit|integration|e2e|all`.

#### g. `tooling`

Files in `topology.categories.editor`:
- `.pre-commit-config.yaml` → list configured hooks.
- `.eslintrc*`, `eslint.config.*`, `.prettierrc*` → JS lint/format active.
- `pyproject.toml [tool.ruff]`, `[tool.black]`, `[tool.mypy]` → Python tooling active.
- `tsconfig.json` → TypeScript strictness flags worth surfacing (`strict: true`, `noUncheckedIndexedAccess: true`).
- `.editorconfig` → present or not.
- `commitlint.config.*`, `.husky/` → conventional commits enforced.

Distill into a 1-paragraph "tooling profile" of the project.

#### h. `other`

Anything significant detected at root or in `topology.categories.other` not captured above. Default behaviour: produce a single atom listing the non-classifiable signals, so they don't disappear from the record.

### 5. Build atoms per layer

**Invariant: one atom per detected layer.** Never consolidate multiple layers into a single atom. If frontend + backend + db + ci + infra are all detected → 5 atoms minimum. The `detected_layer` field is the unit of analysis. Producing a single "synthesis" atom that mixes layers is a procedure violation, even if the LLM judges the project simple.

For each layer with non-empty resolution, build one atom:

- Subject = layer name + 1-line synthesis (e.g. "Frontend — Next.js 14 + React 18 + Tailwind").
- Body = the structured resolution from step 4 in Markdown form (subsections per sub-area when relevant).
- Frontmatter (**all MUST, never omitted**):
  ```yaml
  source: archeo-stack
  source_manifest: <main manifest path for this layer, e.g. package.json | pyproject.toml | docker-compose.yml>
  detected_layer: <one of the eight: frontend|backend|db|ci|infra|tests|tooling|other>    # MUST
  detected_techno: <name or list of detected techs>                                       # MUST — string or YAML list
  content_hash: <sha256-of-this-atom-body>                                                # MUST — SHA-256 of body (after frontmatter, LF + UTF-8 no BOM)
  previous_atom: <wikilink-or-empty>                                                      # MUST — empty "" on first write
  branch: <branch-name-or-empty>                                                          # v0.7.1 — empty "" in standard mode, set in branch-first mode
  project: {slug}
  context_origin: "[[99-meta/repo-topology/{slug}]]"
  ```

A layer with strong convention signals (e.g. `tooling` with strict mypy + pre-commit + commitlint) may produce **two** atoms: one in `20-knowledge/architecture/` describing the stack itself, one in `40-principles/{scope}/conventions/` for the enforced rule (e.g. "All commits must follow Conventional Commits via commitlint enforcement"). The second atom carries `force: heuristic` (English value, never localized — `red-line | heuristic | preference` are the canonical strings).

### 5.b Branch-first ambient atom (v0.7.1)

In branch-first mode, in addition to per-layer atoms (which may be zero if no manifest was modified on the branch), produce **one ambient atom** that captures the global stack context not affected by the branch:

- Subject: "Stack — Ambient context (branch {branch})"
- Body: a 5-15 line synthesis listing the layers resolved in the **main topology** (or in `topology.stack_hints` if no main topology yet) — frontend X, backend Y, db Z, etc. — with a wikilink to the main topology for the full resolution. Plus, if `topology.branch_focus.touched_workspaces` is non-empty, a `## Cross-workspace context` section listing each touched workspace with its vault project link if any:

  ```markdown
  ## Cross-workspace context

  This branch touches the following monorepo workspaces:
  - `@acme/web` (`packages/web`) → [[10-episodes/projects/acme-web/context]] — [[99-meta/repo-topology/acme-web]]
  - `@acme/api` (`packages/api`) → [[10-episodes/projects/acme-api/context]] — [[99-meta/repo-topology/acme-api]]
  - `@acme/shared` (`packages/shared`) → no associated vault project (suggest /mem-archeo packages/shared to bootstrap)
  ```

- Frontmatter (**all MUST**):
  ```yaml
  source: archeo-stack
  source_manifest: ""                                  # empty for ambient atom — by definition not tied to a single manifest
  detected_layer: ambient                              # special value reserved for ambient atoms
  detected_techno: <list-from-main-topology-or-empty>
  content_hash: <sha256>
  previous_atom: <wikilink-or-empty>
  branch: {branch-name}                                # MUST when produced in branch-first mode
  project: {slug}
  context_origin: "[[99-meta/repo-topology/{slug}-branches/{branch-san}]]"
  ```

The ambient atom path: `{VAULT}/20-knowledge/architecture/{slug}-branch-{branch-san}-ambient.md` to avoid collision with the per-layer atoms.

**Idempotence for ambient atoms**: clé `(project, branch, detected_layer=ambient)`. Re-running on the same branch with same content → silent skip.

### 6. Idempotence check

Same logic as `mem-archeo-context` step 5d, with key `(project, source_manifest, detected_layer)`:
- Match found + `content_hash` equal → silent skip.
- Match found + `content_hash` differs → revision with `previous_atom: "[[old]]"`.

### 7. Invoke the router for each candidate atom

For each non-skipped candidate, call the router with:

- `Content`: the body.
- `Hint zone`: `knowledge` for architecture-typed atoms, `principles` for the convention-typed atoms (rare).
- `Hint source`: `archeo-stack`.
- `Metadata`: the candidate's frontmatter shell.

{{INCLUDE _router}}

The router applies R10 idempotence and R11 collision detection.

### 8. Update the persisted topology

Same logic as `mem-archeo-context` step 7, but updating the **`Stack résolue`** section of the topology file (ground truth for the resolved stack) and the `Phases archeo couvertes` line for Phase 2.

The `Stack résolue` section is **the** authoritative description of the project's stack from this point forward. `mem-recall` reads it directly. Phase 1 may have populated `stack_hints` (lightweight); Phase 2 supersedes those hints with the resolved truth.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

### 9. Final report

Display:

```
Phase 2 archeo-stack — {slug}

Layers resolved   : {N}
Atoms created     : {N}
Atoms revised     : {N}
Atoms skipped     : {N}  (idempotent)
By layer          :
  frontend  : {1 atom or "—"}
  backend   : {1 atom or "—"}
  db        : {1 atom or "—"}
  ci        : {1 atom or "—"}
  infra     : {1 atom or "—"}
  tests     : {1 atom or "—"}
  tooling   : {1 atom or "—"}  (+ {N} convention atom(s) in principles)
  other     : {0|1 atom}

Topology updated  : 99-meta/repo-topology/{slug}.md
Stack résolue     : {one-line synthesis: "Next.js 14 + FastAPI + PostgreSQL/Supabase self-hosted"}
```

If invoked from the `mem-archeo` orchestrator, return the structured result.

## Invariants

- **Canonical write paths only** — same as `mem-archeo-context`.
- **No raw config dumps.** Each layer atom is a synthesis, not a copy of the file. Verbatim YAML/JSON stays in the repo, not in the vault.
- **One atom per detected layer, never less.** A single consolidated "stack" atom that mixes frontend + backend + db + infra is a procedure violation. The atom granularity is the layer. Convention atoms in `40-principles/` are the only legitimate additional split per layer.
- **No layer fusion.** If `frontend` and `backend` share a manifest (rare, e.g. monorepo `package.json` at root), still produce two atoms with `detected_layer: frontend` and `detected_layer: backend`, each carrying its specific resolution. Same `source_manifest`, different `detected_layer`.
- **`detected_layer`, `detected_techno`, `content_hash` are mandatory** on every Phase 2 atom — never omitted, even if value is `[]` for `detected_techno` or `""` for `previous_atom`.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block). `mem-archeo-stack` refuses by default on an archived target slug — see the override path in `mem-archeo.md` (`--allow-archived` flag forwarded from the orchestrator).
