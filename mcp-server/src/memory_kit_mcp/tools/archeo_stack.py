"""mem_archeo_stack — Phase 2 of the triphasic archeo: stack resolution.

Spec: core/procedures/mem-archeo-stack.md

Reads HEAD only. Produces one atom per detected layer in the eight-layer model
(frontend, backend, db, ci, infra, tests, tooling, other). Atoms land in
20-knowledge/architecture/ with frontmatter source=archeo-stack and
detected_layer set. Idempotent on (project, source_manifest, detected_layer).

POC scope (v0.8.x):
- All 8 layers covered by deterministic manifest parsing (JSON + TOML + globs).
- Atoms written directly to 20-knowledge/architecture/{slug}-stack-{layer}.md
  (no router cascade — the procedure's R10/R11 collision logic is left to
  skills mode for now).
- Branch-first mode (--branch-first) NOT implemented — falls back to standard
  mode (full repo scan).
- Convention atoms in 40-principles/ NOT auto-emitted — the LLM may emit them
  via skill fallback if needed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ArcheoStackResult, LayerResolution
from memory_kit_mcp.vault import frontmatter, paths
from memory_kit_mcp.vault.atomic_io import hash_content
from memory_kit_mcp.vault.topology_scanner import NotAGitRepoError, Topology, scan

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# ----------------------------------------------------------------------
# Public tool
# ----------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_stack with the FastMCP instance."""

    @mcp.tool()
    def mem_archeo_stack(
        repo_path: str = Field(..., description="Absolute path to the local Git repository to scan."),
        project: str | None = Field(
            None,
            description="Target project slug. Defaults to basename(repo_path) if it matches an existing project.",
        ),
        depth: int = Field(2, ge=1, le=4, description="Topology scan depth."),
    ) -> ArcheoStackResult:
        """Phase 2 of the triphasic archeo: resolve the stack by layer.

        Scans the repo's manifests / lockfiles / infra / ci / editor configs and
        produces one atom per detected layer in 20-knowledge/architecture/.
        Idempotent: re-running on an unchanged repo skips all atoms with matching
        content_hash. Refuses non-Git directories with NotAGitRepoError.
        """
        config = get_config()
        vault = config.vault

        repo = Path(repo_path).expanduser().resolve()
        try:
            topology = scan(repo, depth=depth, vault=vault)
        except NotAGitRepoError as e:
            raise NotAGitRepoError(str(e)) from e

        slug = _resolve_project_slug(vault, repo, project)
        layers = _resolve_all_layers(repo, topology)

        atoms_created = 0
        atoms_revised = 0
        atoms_skipped = 0
        files_created: list[str] = []
        files_modified: list[str] = []

        for layer in layers:
            outcome = _write_layer_atom(vault, slug, layer)
            if outcome == "created":
                atoms_created += 1
                files_created.append(_layer_atom_path(vault, slug, layer.layer).as_posix())
            elif outcome == "revised":
                atoms_revised += 1
                files_modified.append(_layer_atom_path(vault, slug, layer.layer).as_posix())
            else:
                atoms_skipped += 1

        return ArcheoStackResult(
            project=slug,
            repo_path=str(repo),
            layers_resolved=len(layers),
            atoms_created=atoms_created,
            atoms_revised=atoms_revised,
            atoms_skipped=atoms_skipped,
            layers=layers,
            files_created=files_created,
            files_modified=files_modified,
            warnings=topology.warnings,
            summary_md=_summary_md(slug, layers, atoms_created, atoms_revised, atoms_skipped),
        )


# ----------------------------------------------------------------------
# Project slug resolution (deterministic — interactive flows belong to skills)
# ----------------------------------------------------------------------


def _resolve_project_slug(vault: Path, repo: Path, explicit: str | None) -> str:
    """Resolve target project slug. POC: explicit > basename match > error.

    The skills procedure (mem-archeo-context step 2) describes a richer
    cascade (remote URL match, ask user, create new project). The MCP server
    cannot do interactive prompts, so it limits itself to the deterministic
    branches and asks the LLM to retry with --project on ambiguity.
    """
    if explicit:
        return explicit
    candidate = repo.name
    if (vault / "10-episodes" / "projects" / candidate).is_dir():
        return candidate
    raise ValueError(
        f"Cannot auto-resolve target project slug for repo {repo.name!r}. "
        f"No project named {candidate!r} exists in {paths.ZONE_EPISODES}/projects/. "
        "Pass `project=<slug>` explicitly, or create the project via mem_archive first."
    )


# ----------------------------------------------------------------------
# Layer resolution (eight resolvers)
# ----------------------------------------------------------------------


def _resolve_all_layers(repo: Path, topology: Topology) -> list[LayerResolution]:
    """Try every layer resolver. Each returns None when nothing was detected."""
    out: list[LayerResolution] = []
    for resolver in (
        _resolve_frontend,
        _resolve_backend,
        _resolve_db,
        _resolve_ci,
        _resolve_infra,
        _resolve_tests,
        _resolve_tooling,
        _resolve_other,
    ):
        result = resolver(repo, topology)
        if result is not None:
            out.append(result)
    return out


# ---- frontend ----


_FRONTEND_META: dict[str, str] = {
    "next": "Next.js",
    "nuxt": "Nuxt",
    "remix": "Remix",
    "astro": "Astro",
    "@sveltejs/kit": "SvelteKit",
    "qwik": "Qwik",
}
_FRONTEND_VIEW: dict[str, str] = {
    "react": "React",
    "vue": "Vue",
    "svelte": "Svelte",
    "solid-js": "Solid",
}
_FRONTEND_STYLING: dict[str, str] = {
    "tailwindcss": "Tailwind CSS",
    "styled-components": "styled-components",
    "@emotion/react": "Emotion",
    "sass": "Sass",
    "@vanilla-extract/css": "Vanilla Extract",
}
_FRONTEND_STATE: dict[str, str] = {
    "zustand": "Zustand",
    "redux": "Redux",
    "@reduxjs/toolkit": "Redux Toolkit",
    "pinia": "Pinia",
    "jotai": "Jotai",
    "recoil": "Recoil",
    "@tanstack/react-query": "TanStack Query",
    "swr": "SWR",
}
_FRONTEND_FORM: dict[str, str] = {
    "react-hook-form": "react-hook-form",
    "formik": "Formik",
    "zod": "Zod",
    "yup": "Yup",
    "valibot": "Valibot",
}
_FRONTEND_TEST: dict[str, str] = {
    "vitest": "Vitest",
    "jest": "Jest",
    "@testing-library/react": "Testing Library",
    "playwright": "Playwright",
    "@playwright/test": "Playwright",
    "cypress": "Cypress",
}


def _resolve_frontend(repo: Path, topology: Topology) -> LayerResolution | None:
    pkg = repo / "package.json"
    if not pkg.is_file():
        return None
    deps = _read_npm_deps(pkg)
    meta = _hits(deps, _FRONTEND_META)
    view = _hits(deps, _FRONTEND_VIEW)
    if not meta and not view:
        return None
    styling = _hits(deps, _FRONTEND_STYLING)
    state = _hits(deps, _FRONTEND_STATE)
    forms = _hits(deps, _FRONTEND_FORM)
    tests = _hits(deps, _FRONTEND_TEST)
    technos = _ordered_unique([*meta, *view, *styling, *state, *forms, *tests])

    parts = [f"# Frontend layer\n"]
    if meta:
        parts.append(f"- **Meta-framework**: {', '.join(meta)}")
    if view:
        parts.append(f"- **View layer**: {', '.join(view)}")
    if styling:
        parts.append(f"- **Styling**: {', '.join(styling)}")
    if state:
        parts.append(f"- **State / data fetching**: {', '.join(state)}")
    if forms:
        parts.append(f"- **Forms / validation**: {', '.join(forms)}")
    if tests:
        parts.append(f"- **Tests**: {', '.join(tests)}")
    parts.append(f"\n_Source manifest: `package.json`._")
    return LayerResolution(
        layer="frontend",
        source_manifest="package.json",
        technos=technos,
        summary_md="\n".join(parts) + "\n",
    )


# ---- backend ----


_BACKEND_PYTHON_FW: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "aiohttp": "aiohttp",
    "starlette": "Starlette",
    "quart": "Quart",
    "sanic": "Sanic",
}
_BACKEND_PYTHON_ORM: dict[str, str] = {
    "sqlalchemy": "SQLAlchemy",
    "tortoise-orm": "Tortoise ORM",
    "peewee": "Peewee",
    "psycopg": "psycopg (PostgreSQL)",
    "asyncpg": "asyncpg (PostgreSQL)",
    "pymongo": "PyMongo",
    "motor": "Motor (MongoDB async)",
}
_BACKEND_PYTHON_VALIDATION: dict[str, str] = {
    "pydantic": "Pydantic",
    "marshmallow": "Marshmallow",
    "attrs": "attrs",
}
_BACKEND_NODE_FW: dict[str, str] = {
    "express": "Express",
    "fastify": "Fastify",
    "koa": "Koa",
    "@nestjs/core": "NestJS",
    "hono": "Hono",
}
_BACKEND_NODE_ORM: dict[str, str] = {
    "prisma": "Prisma",
    "@prisma/client": "Prisma",
    "typeorm": "TypeORM",
    "sequelize": "Sequelize",
    "mongoose": "Mongoose",
    "drizzle-orm": "Drizzle",
    "kysely": "Kysely",
}
_BACKEND_GO_FW: dict[str, str] = {
    "github.com/gin-gonic/gin": "Gin",
    "github.com/gorilla/mux": "Gorilla Mux",
    "github.com/labstack/echo": "Echo",
    "github.com/gofiber/fiber": "Fiber",
}
_BACKEND_RUST_FW: dict[str, str] = {
    "axum": "Axum",
    "actix-web": "Actix Web",
    "rocket": "Rocket",
    "warp": "Warp",
    "tide": "Tide",
}


def _resolve_backend(repo: Path, topology: Topology) -> LayerResolution | None:
    py = repo / "pyproject.toml"
    req = repo / "requirements.txt"
    pipfile = repo / "Pipfile"
    pkg = repo / "package.json"
    cargo = repo / "Cargo.toml"
    gomod = repo / "go.mod"

    technos: list[str] = []
    parts = ["# Backend layer\n"]
    source_manifest: str | None = None

    py_deps: set[str] = set()
    if py.is_file():
        py_deps |= _read_pyproject_deps(py)
    if req.is_file():
        py_deps |= _read_requirements_deps(req)
    if pipfile.is_file():
        py_deps |= _read_pipfile_deps(pipfile)
    if py_deps:
        fw = _hits(py_deps, _BACKEND_PYTHON_FW)
        orm = _hits(py_deps, _BACKEND_PYTHON_ORM)
        val = _hits(py_deps, _BACKEND_PYTHON_VALIDATION)
        if fw or orm or val:
            source_manifest = "pyproject.toml" if py.is_file() else (
                "requirements.txt" if req.is_file() else "Pipfile"
            )
            parts.append("## Python\n")
            if fw:
                parts.append(f"- **Web framework**: {', '.join(fw)}")
            if orm:
                parts.append(f"- **ORM / DB driver**: {', '.join(orm)}")
            if val:
                parts.append(f"- **Validation**: {', '.join(val)}")
            technos.extend([*fw, *orm, *val])

    if pkg.is_file():
        deps = _read_npm_deps(pkg)
        fw = _hits(deps, _BACKEND_NODE_FW)
        orm = _hits(deps, _BACKEND_NODE_ORM)
        if fw or orm:
            if source_manifest is None:
                source_manifest = "package.json"
            parts.append("\n## Node.js\n")
            if fw:
                parts.append(f"- **Web framework**: {', '.join(fw)}")
            if orm:
                parts.append(f"- **ORM**: {', '.join(orm)}")
            technos.extend([*fw, *orm])

    if cargo.is_file():
        deps = _read_cargo_deps(cargo)
        fw = _hits(deps, _BACKEND_RUST_FW)
        if fw:
            if source_manifest is None:
                source_manifest = "Cargo.toml"
            parts.append("\n## Rust\n")
            parts.append(f"- **Web framework**: {', '.join(fw)}")
            technos.extend(fw)

    if gomod.is_file():
        gomod_deps = _read_gomod_deps(gomod)
        fw = _hits(gomod_deps, _BACKEND_GO_FW)
        if fw:
            if source_manifest is None:
                source_manifest = "go.mod"
            parts.append("\n## Go\n")
            parts.append(f"- **Web framework**: {', '.join(fw)}")
            technos.extend(fw)

    if not technos or source_manifest is None:
        return None
    parts.append(f"\n_Source manifest: `{source_manifest}`._")
    return LayerResolution(
        layer="backend",
        source_manifest=source_manifest,
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- db ----


_DB_PY_DEPS: dict[str, str] = {
    "psycopg": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL",
    "asyncpg": "PostgreSQL",
    "mysql-connector-python": "MySQL",
    "pymongo": "MongoDB",
    "motor": "MongoDB",
    "redis": "Redis",
    "aiosqlite": "SQLite",
    "sqlalchemy": "SQLAlchemy",
}
_DB_NODE_DEPS: dict[str, str] = {
    "pg": "PostgreSQL",
    "mysql2": "MySQL",
    "mongoose": "MongoDB",
    "ioredis": "Redis",
    "redis": "Redis",
    "sqlite3": "SQLite",
    "better-sqlite3": "SQLite",
}
_DB_CONTAINER_IMAGES: tuple[str, ...] = (
    "postgres", "mysql", "mariadb", "mongo", "redis", "elasticsearch",
    "supabase", "kong", "postgrest", "gotrue",
)


def _resolve_db(repo: Path, topology: Topology) -> LayerResolution | None:
    technos: list[str] = []
    direct_signals: list[str] = []
    container_signals: list[str] = []
    source_manifest: str | None = None

    if (repo / "prisma" / "schema.prisma").is_file():
        direct_signals.append("Prisma schema (prisma/schema.prisma)")
        source_manifest = "prisma/schema.prisma"
    if (repo / "alembic.ini").is_file():
        direct_signals.append("Alembic migrations (alembic.ini)")
        source_manifest = source_manifest or "alembic.ini"
    if (repo / "drizzle.config.ts").is_file() or (repo / "drizzle.config.js").is_file():
        direct_signals.append("Drizzle config")
        source_manifest = source_manifest or "drizzle.config.ts"

    py_deps: set[str] = set()
    if (repo / "pyproject.toml").is_file():
        py_deps |= _read_pyproject_deps(repo / "pyproject.toml")
    if (repo / "requirements.txt").is_file():
        py_deps |= _read_requirements_deps(repo / "requirements.txt")
    py_hits = _hits(py_deps, _DB_PY_DEPS)
    if py_hits:
        technos.extend(py_hits)
        source_manifest = source_manifest or "pyproject.toml"

    if (repo / "package.json").is_file():
        node_deps = _read_npm_deps(repo / "package.json")
        node_hits = _hits(node_deps, _DB_NODE_DEPS)
        if node_hits:
            technos.extend(node_hits)
            source_manifest = source_manifest or "package.json"

    # Container signals via topology.categories.infra
    for entry in topology.categories.get("infra", []):
        if not entry.startswith("docker-compose") and entry != "compose.yml":
            continue
        compose_path = repo / entry
        if not compose_path.is_file():
            continue
        try:
            content = compose_path.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        for image in _DB_CONTAINER_IMAGES:
            if f"image: {image}" in content or f"image: '{image}" in content or f'image: "{image}' in content:
                container_signals.append(f"{image} (docker-compose)")
                technos.append(image.capitalize() if image not in ("kong", "postgrest", "gotrue") else f"Supabase ({image})")
        if any(svc in content for svc in ("supabase/", "kong:", "postgrest:", "gotrue:")):
            if "Supabase (self-hosted)" not in technos:
                technos.append("Supabase (self-hosted)")
            source_manifest = source_manifest or entry

    if not technos and not direct_signals and not container_signals:
        return None
    parts = ["# Database layer\n"]
    if direct_signals:
        parts.append("## Direct signals (config files)")
        for s in direct_signals:
            parts.append(f"- {s}")
    if technos:
        parts.append("\n## Indirect signals (deps & containers)")
        for t in _ordered_unique(technos):
            parts.append(f"- {t}")
    parts.append(f"\n_Source manifest: `{source_manifest or '(multiple)'}`._")
    return LayerResolution(
        layer="db",
        source_manifest=source_manifest or "package.json",
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- ci ----


def _resolve_ci(repo: Path, topology: Topology) -> LayerResolution | None:
    ci_entries = topology.categories.get("ci", [])
    if not ci_entries:
        return None
    parts = ["# CI / CD layer\n"]
    technos: list[str] = []
    source_manifest = ci_entries[0]

    for entry in ci_entries:
        if entry == ".github/workflows/":
            workflows_dir = repo / ".github" / "workflows"
            if workflows_dir.is_dir():
                workflows = sorted(p.name for p in workflows_dir.iterdir() if p.suffix in {".yml", ".yaml"})
                if workflows:
                    parts.append(f"## GitHub Actions\n- Workflows: {', '.join(workflows)}")
                    technos.append("GitHub Actions")
        elif entry == ".gitlab-ci.yml":
            parts.append("## GitLab CI\n- `.gitlab-ci.yml` present")
            technos.append("GitLab CI")
        elif entry == "Jenkinsfile":
            parts.append("## Jenkins\n- `Jenkinsfile` present")
            technos.append("Jenkins")
        elif entry == "azure-pipelines.yml":
            parts.append("## Azure Pipelines\n- `azure-pipelines.yml` present")
            technos.append("Azure Pipelines")
        elif entry == "bitbucket-pipelines.yml":
            parts.append("## Bitbucket Pipelines\n- present")
            technos.append("Bitbucket Pipelines")
        elif entry in (".circleci", ".circleci/"):
            parts.append("## CircleCI\n- `.circleci/` present")
            technos.append("CircleCI")
        elif entry == ".drone.yml":
            parts.append("## Drone\n- `.drone.yml` present")
            technos.append("Drone")
        elif entry == ".travis.yml":
            parts.append("## Travis\n- `.travis.yml` present")
            technos.append("Travis")
    parts.append(f"\n_Sources: {', '.join(ci_entries)}._")
    return LayerResolution(
        layer="ci",
        source_manifest=source_manifest,
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- infra ----


def _resolve_infra(repo: Path, topology: Topology) -> LayerResolution | None:
    infra_entries = topology.categories.get("infra", [])
    if not infra_entries:
        return None
    technos: list[str] = []
    parts = ["# Infrastructure layer\n"]
    source_manifest = infra_entries[0]

    for entry in infra_entries:
        if entry.startswith("Dockerfile"):
            base = _dockerfile_base(repo / entry)
            label = f"Docker (base: {base})" if base else "Docker"
            parts.append(f"## {entry}\n- {label}")
            if "Docker" not in technos:
                technos.append("Docker")
        elif entry.startswith("docker-compose") or entry == "compose.yml" or entry == "compose.yaml":
            services = _docker_compose_services(repo / entry)
            parts.append(f"## {entry}")
            if services:
                parts.append(f"- Services: {', '.join(services)}")
            if "docker-compose" not in technos:
                technos.append("docker-compose")
        elif entry == "Makefile":
            parts.append("## Makefile\n- Command surface for newcomers")
            technos.append("Makefile")
        elif entry in ("terraform/", "pulumi/", "k8s/", "helm/", "kustomize/", "ansible/"):
            label = entry.rstrip("/").capitalize()
            parts.append(f"## {entry}\n- IaC tool: {label}")
            technos.append(label)
    parts.append(f"\n_Sources: {', '.join(infra_entries)}._")
    return LayerResolution(
        layer="infra",
        source_manifest=source_manifest,
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- tests ----


def _resolve_tests(repo: Path, topology: Topology) -> LayerResolution | None:
    test_entries = topology.categories.get("tests", [])
    technos: list[str] = []
    structural_signals: list[str] = []

    for marker, label in (
        ("pytest.ini", "pytest"),
        ("tox.ini", "tox"),
        ("conftest.py", "pytest"),
        ("jest.config.js", "Jest"),
        ("jest.config.ts", "Jest"),
        ("vitest.config.js", "Vitest"),
        ("vitest.config.ts", "Vitest"),
        ("playwright.config.js", "Playwright"),
        ("playwright.config.ts", "Playwright"),
        ("cypress.config.js", "Cypress"),
        ("cypress.config.ts", "Cypress"),
    ):
        if (repo / marker).is_file():
            structural_signals.append(marker)
            if label not in technos:
                technos.append(label)

    # tests/ folder presence
    if test_entries:
        structural_signals.extend(test_entries)

    # Frontend test deps from package.json
    if (repo / "package.json").is_file():
        deps = _read_npm_deps(repo / "package.json")
        for dep in ("vitest", "jest", "@playwright/test", "playwright", "cypress"):
            if dep in deps:
                label = {
                    "vitest": "Vitest",
                    "jest": "Jest",
                    "@playwright/test": "Playwright",
                    "playwright": "Playwright",
                    "cypress": "Cypress",
                }[dep]
                if label not in technos:
                    technos.append(label)

    # Python test deps
    py_deps: set[str] = set()
    if (repo / "pyproject.toml").is_file():
        py_deps |= _read_pyproject_deps(repo / "pyproject.toml")
    if "pytest" in py_deps and "pytest" not in technos:
        technos.append("pytest")

    if not technos and not structural_signals:
        return None

    scope = "unknown"
    if any("e2e" in s.lower() or "playwright" in s.lower() or "cypress" in s.lower() for s in structural_signals + technos):
        scope = "e2e + unit"
    elif technos:
        scope = "unit / integration"

    parts = ["# Tests layer\n"]
    if technos:
        parts.append(f"- **Frameworks**: {', '.join(technos)}")
    if structural_signals:
        parts.append(f"- **Structural signals**: {', '.join(_ordered_unique(structural_signals))}")
    parts.append(f"- **Scope**: {scope}")
    return LayerResolution(
        layer="tests",
        source_manifest=structural_signals[0] if structural_signals else "package.json",
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- tooling ----


def _resolve_tooling(repo: Path, topology: Topology) -> LayerResolution | None:
    technos: list[str] = []
    parts = ["# Tooling layer\n"]
    detected = False
    source_manifest: str | None = None

    if (repo / ".pre-commit-config.yaml").is_file():
        parts.append("- **pre-commit**: hooks declared in `.pre-commit-config.yaml`")
        technos.append("pre-commit")
        source_manifest = source_manifest or ".pre-commit-config.yaml"
        detected = True

    eslint_files = [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs", "eslint.config.js"]
    if any((repo / f).is_file() for f in eslint_files):
        parts.append("- **ESLint**: present")
        technos.append("ESLint")
        detected = True
    if (repo / ".prettierrc").is_file() or (repo / ".prettierrc.json").is_file() or (repo / ".prettierrc.yaml").is_file():
        parts.append("- **Prettier**: present")
        technos.append("Prettier")
        detected = True

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
        tool = data.get("tool", {}) if isinstance(data, dict) else {}
        for name in ("ruff", "black", "mypy", "isort", "pytest"):
            if name in tool:
                parts.append(f"- **{name}**: configured in `pyproject.toml [tool.{name}]`")
                technos.append(name)
                source_manifest = source_manifest or "pyproject.toml"
                detected = True

    tsconfig = repo / "tsconfig.json"
    if tsconfig.is_file():
        try:
            tsdata = json.loads(tsconfig.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            tsdata = {}
        compiler = tsdata.get("compilerOptions", {}) if isinstance(tsdata, dict) else {}
        flags = []
        for flag in ("strict", "noUncheckedIndexedAccess", "noImplicitAny"):
            if compiler.get(flag) is True:
                flags.append(flag)
        if flags:
            parts.append(f"- **TypeScript strictness**: {', '.join(flags)} = true")
        else:
            parts.append("- **TypeScript**: `tsconfig.json` present")
        technos.append("TypeScript")
        source_manifest = source_manifest or "tsconfig.json"
        detected = True

    if (repo / ".editorconfig").is_file():
        parts.append("- **EditorConfig**: present")
        technos.append("EditorConfig")
        detected = True

    if (repo / "commitlint.config.js").is_file() or (repo / ".husky").is_dir():
        parts.append("- **Conventional commits**: commitlint or husky enforced")
        technos.append("commitlint")
        detected = True

    if not detected:
        return None
    return LayerResolution(
        layer="tooling",
        source_manifest=source_manifest or ".editorconfig",
        technos=_ordered_unique(technos),
        summary_md="\n".join(parts) + "\n",
    )


# ---- other ----


def _resolve_other(repo: Path, topology: Topology) -> LayerResolution | None:
    """Surface non-classifiable signals as a single 'other' atom.

    Conservative: only emit if at least one entry exists in topology.categories['other']
    that does NOT match an excluded scaffolding folder (.github, docs, etc.).
    """
    others = topology.categories.get("other", [])
    significant = [e for e in others if not e.endswith("scripts/") and not e.startswith(".")]
    if not significant:
        return None
    parts = ["# Other / non-classified signals\n"]
    parts.append("Entries not captured by frontend/backend/db/ci/infra/tests/tooling resolvers:")
    for e in significant[:20]:
        parts.append(f"- `{e}`")
    return LayerResolution(
        layer="other",
        source_manifest="(repo root)",
        technos=[],
        summary_md="\n".join(parts) + "\n",
    )


# ----------------------------------------------------------------------
# Atom write + idempotence
# ----------------------------------------------------------------------


def _layer_atom_path(vault: Path, slug: str, layer: str) -> Path:
    return vault / "20-knowledge" / "architecture" / f"{slug}-stack-{layer}.md"


def _write_layer_atom(vault: Path, slug: str, layer: LayerResolution) -> str:
    """Write or skip the atom for one layer. Returns 'created'|'revised'|'skipped'."""
    target = _layer_atom_path(vault, slug, layer.layer)
    new_body = layer.summary_md
    new_hash = hash_content(new_body)

    fm: dict[str, Any] = {
        "source": "archeo-stack",
        "source_manifest": layer.source_manifest,
        "detected_layer": layer.layer,
        "detected_techno": layer.technos,
        "content_hash": new_hash,
        "previous_atom": "",
        "branch": "",
        "project": slug,
        "context_origin": f"[[99-meta/repo-topology/{slug}]]",
        "zone": "knowledge",
        "kind": "architecture",
        "scope": "work",
        "tags": [
            "kind/architecture",
            "zone/knowledge",
            "scope/work",
            f"project/{slug}",
            f"detected_layer/{layer.layer}",
        ],
        "display": f"{slug} — stack {layer.layer}",
    }

    if target.is_file():
        existing_fm, _ = frontmatter.read(target)
        existing_hash = existing_fm.get("content_hash")
        if existing_hash == new_hash:
            return "skipped"
        # Revision: link previous and bump
        previous_name = target.stem
        fm["previous_atom"] = f"[[{previous_name}]]"
        frontmatter.write(target, fm, new_body)
        return "revised"

    frontmatter.write(target, fm, new_body)
    return "created"


# ----------------------------------------------------------------------
# Manifest parsing helpers
# ----------------------------------------------------------------------


def _read_npm_deps(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    out: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            out.update(section.keys())
    return out


def _read_pyproject_deps(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    out: set[str] = set()
    project = data.get("project", {})
    for spec in project.get("dependencies", []):
        out.add(_pkg_name(spec))
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            for spec in group:
                out.add(_pkg_name(spec))
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        out.update(name for name in poetry_deps if name != "python")
    return out


def _read_requirements_deps(path: Path) -> set[str]:
    out: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            out.add(_pkg_name(line))
    except OSError:
        pass
    return out


def _read_pipfile_deps(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    out: set[str] = set()
    for key in ("packages", "dev-packages"):
        section = data.get(key, {})
        if isinstance(section, dict):
            out.update(section.keys())
    return out


def _read_cargo_deps(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    out: set[str] = set()
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            out.update(section.keys())
    return out


def _read_gomod_deps(path: Path) -> set[str]:
    """Lightweight go.mod parser: extracts module paths from `require` blocks."""
    out: set[str] = set()
    in_require = False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("require ("):
                in_require = True
                continue
            if line == ")":
                in_require = False
                continue
            if line.startswith("require "):
                # Single-line require
                parts = line.split()
                if len(parts) >= 2:
                    out.add(parts[1])
                continue
            if in_require:
                parts = line.split()
                if parts:
                    out.add(parts[0])
    except OSError:
        pass
    return out


_PKG_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _pkg_name(spec: str) -> str:
    """Extract the package name from a requirement specifier (e.g. 'fastapi>=0.100')."""
    spec = spec.strip().lower()
    m = _PKG_NAME_RE.match(spec)
    return m.group(1) if m else spec


def _hits(deps: set[str], catalog: dict[str, str]) -> list[str]:
    """Return labels from catalog whose key is in deps, preserving catalog order."""
    return [label for key, label in catalog.items() if key.lower() in deps]


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ----------------------------------------------------------------------
# Infra helpers
# ----------------------------------------------------------------------


_DOCKERFILE_FROM_RE = re.compile(r"^FROM\s+([\w./:\-@]+)", re.MULTILINE)


def _dockerfile_base(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    match = _DOCKERFILE_FROM_RE.search(content)
    return match.group(1) if match else ""


_COMPOSE_SERVICE_RE = re.compile(r"^\s{2}([\w\-]+):\s*$", re.MULTILINE)


def _docker_compose_services(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    in_services = False
    services: list[str] = []
    for line in content.splitlines():
        if line.strip() == "services:":
            in_services = True
            continue
        if in_services:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                in_services = False
                continue
            m = re.match(r"^\s\s([\w\-]+):\s*$", line)
            if m:
                services.append(m.group(1))
    return services


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------


def _summary_md(
    slug: str,
    layers: list[LayerResolution],
    created: int,
    revised: int,
    skipped: int,
) -> str:
    lines = [
        f"**mem_archeo_stack** — {slug}",
        "",
        f"Layers resolved : {len(layers)}",
        f"Atoms created  : {created}",
        f"Atoms revised  : {revised}",
        f"Atoms skipped  : {skipped} (idempotent)",
        "",
        "## By layer",
    ]
    by_layer = {layer.layer: layer for layer in layers}
    for canonical in ("frontend", "backend", "db", "ci", "infra", "tests", "tooling", "other"):
        layer = by_layer.get(canonical)
        if layer is None:
            lines.append(f"- {canonical}: —")
        else:
            technos = ", ".join(layer.technos) if layer.technos else "(no specific techno)"
            lines.append(f"- {canonical}: {technos}")
    lines.append("")
    return "\n".join(lines)
