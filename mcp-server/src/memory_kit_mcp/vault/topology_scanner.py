"""Repo topology scanner — Phase 0 shared primitive.

Spec: core/procedures/_repo-topology.md

Builds a structural map of a Git repository (categories, stack hints,
workspaces) consumed by Phase 1/2/3 archeo phases without re-scanning. This
module is a primitive used by archeo tools — it is NOT exposed as an MCP tool
on its own.

Scope of this implementation (deterministic only):
- T1 standard exclusions
- T2 categories (15 + 'other')
- T3 in-memory topology shape
- T3.1 workspace detection (4 main patterns: npm/pnpm, Cargo, pyproject)
- T4 stack hints (manifest parsing — JSON/TOML)
- T7 failure modes (NotAGitRepoError, empty repo warning)

Out of scope (deferred):
- T5 in-memory AI file caching — caller's responsibility if needed
- T6 persistence — handled by mem_archeo orchestrator + mem_archive full-mode
- T6.1 branch-first topology — v0.8.x
- gradle / pom.xml / lerna / turbo workspace detection — best-effort, falls back
  to generic apps/+packages/ heuristic if none of the above matches
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 not supported by the project
    import tomli as tomllib  # type: ignore[no-redef]

# T1 — standard exclusions
EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", ".idea", ".vscode", ".vs",
    "node_modules", "bower_components",
    "target", "dist", "build", "out",
    ".next", ".nuxt", ".output", ".turbo", ".cache",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "venv", ".venv", "env", ".env",
    "vendor", "Pods", "DerivedData", ".gradle", "bin", "obj",
    "coverage", ".nyc_output", ".coverage",
})

# Folders that are recursed deeper (depth 4 by default vs 2 elsewhere).
SPECIAL_DEEP_DIRS: frozenset[str] = frozenset({
    "docs", "documentation", "cadrage", "specs", "adr", "rfc",
    "src", "source", "sources", "lib", "app", "apps", "packages",
})

AI_FILES: frozenset[str] = frozenset({
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "MISTRAL.md",
    ".cursorrules", ".windsurfrules", ".aider.conf.yml",
})

README_FILES: frozenset[str] = frozenset({
    "README.md", "README.rst", "README.txt", "Readme.md", "readme.md",
})

CHANGELOG_FILES: frozenset[str] = frozenset({
    "CHANGELOG.md", "CHANGES.md", "HISTORY.md", "RELEASES.md", "NEWS.md",
})

GIT_META_FILES: frozenset[str] = frozenset({
    ".gitignore", ".gitattributes", ".git-blame-ignore-revs", ".gitmodules",
})

LICENSE_FILES_PREFIX: tuple[str, ...] = ("LICENSE", "COPYING", "NOTICE")

LOCKFILES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "Cargo.lock", "poetry.lock", "uv.lock", "Gemfile.lock",
    "composer.lock", "pubspec.lock",
})

MANIFEST_FILES: frozenset[str] = frozenset({
    "package.json", "pyproject.toml", "Pipfile", "Cargo.toml", "go.mod",
    "composer.json", "Gemfile", "pom.xml", "mix.exs", "pubspec.yaml",
})

EDITOR_FILES: frozenset[str] = frozenset({
    ".editorconfig", ".pre-commit-config.yaml", ".prettierrc", ".prettierrc.json",
    ".prettierrc.yml", ".prettierrc.yaml", "tsconfig.json",
})

EDITOR_PREFIXES: tuple[str, ...] = (".eslintrc", ".prettierrc", "tsconfig.")

# Common CI files at repo root.
CI_FILES: frozenset[str] = frozenset({
    ".gitlab-ci.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml",
    "Jenkinsfile", ".drone.yml", ".travis.yml", ".circleci",
})

# Infra signals (file or directory).
INFRA_FILES_OR_DIRS: frozenset[str] = frozenset({
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
    "compose.yaml", "Makefile", "terraform", "pulumi", "infrastructure",
    "k8s", "kubernetes", "helm", "kustomize", "ansible",
})

DOC_DIRS: frozenset[str] = frozenset({
    "docs", "documentation", "cadrage", "specs", "adr", "rfc", "wiki",
})

SOURCE_DIRS: frozenset[str] = frozenset({
    "src", "source", "sources", "lib", "app", "apps",
})

TEST_DIRS: frozenset[str] = frozenset({
    "tests", "test", "__tests__", "spec", "e2e", "cypress", "playwright",
})

CONFIG_DIRS: frozenset[str] = frozenset({"config", "settings"})

CATEGORY_KEYS: tuple[str, ...] = (
    "sources", "docs", "ai_files", "readme", "changelog", "config",
    "tests", "ci", "infra", "manifests", "workspaces", "lockfiles",
    "git_meta", "editor", "license", "other",
)


@dataclass
class WorkspaceMember:
    """One workspace package detected in a monorepo."""
    name: str
    path: str  # repo-relative
    manifest: str  # repo-relative
    vault_project: str = ""
    workspace_implicit: bool = False  # True if detected via apps/+packages/ fallback


@dataclass
class Topology:
    """In-memory topology object — Phase 0 output."""
    repo_path: str
    repo_remote: str
    scanned_at: str  # ISO 8601 UTC
    depth_limit: int
    categories: dict[str, list[str]] = field(default_factory=dict)
    stack_hints: dict[str, list[str]] = field(default_factory=lambda: {
        "frontend": [],
        "backend": [],
        "db": [],
        "lang": [],
    })
    workspaces: list[WorkspaceMember] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class NotAGitRepoError(ValueError):
    """Raised when {repo_path} is not a Git repository (T7)."""


def scan(repo_path: Path, depth: int = 2, vault: Path | None = None) -> Topology:
    """Scan a repo and return its Topology.

    Args:
        repo_path: absolute path to the repo root (must contain .git/).
        depth: max recursion depth for non-special folders. Default 2.
            Special folders (docs/, src/, etc.) are recursed up to depth 4.
        vault: optional vault path used to resolve workspace.vault_project
            slugs. If None, vault_project remains "" for all workspaces.

    Raises:
        NotAGitRepoError: if {repo_path} is not a git repo.
    """
    repo_path = repo_path.resolve()
    if not _is_git_repo(repo_path):
        raise NotAGitRepoError(f"{repo_path} is not a Git repository.")

    topo = Topology(
        repo_path=str(repo_path),
        repo_remote=_git_remote(repo_path),
        scanned_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        depth_limit=depth,
        categories={k: [] for k in CATEGORY_KEYS},
    )

    # Walk top-level entries; each is classified by name; directories that
    # match a special category may be recursed deeper to capture sub-files
    # (e.g. ci .github/workflows/*.yml).
    for entry in sorted(repo_path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name in EXCLUDED_DIRS:
            continue
        _classify(entry, topo, repo_path, depth)

    # T4 stack hints — parse known manifests for framework markers
    _resolve_stack_hints(repo_path, topo)

    # Empty-repo warning
    if not _has_commits(repo_path):
        topo.warnings.append("repo has no commits — Phase 3 will fail; Phases 1/2 OK if files exist.")
        topo.stack_hints = {"frontend": [], "backend": [], "db": [], "lang": []}

    # T3.1 workspace detection
    topo.workspaces = _detect_workspaces(repo_path, vault)

    return topo


# ----------------------------------------------------------------------
# Git helpers (subprocess, zero-dep)
# ----------------------------------------------------------------------

def _is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _git_remote(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _has_commits(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-list", "-n", "1", "--all"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


# ----------------------------------------------------------------------
# Classification (T2)
# ----------------------------------------------------------------------

def _classify(entry: Path, topo: Topology, root: Path, depth: int) -> None:
    """Add an entry to the relevant categories. An entry can fit several."""
    name = entry.name
    rel = _rel_with_slash(entry, root, is_dir=entry.is_dir())

    matched = False

    # File-level classification
    if entry.is_file():
        if name in AI_FILES:
            topo.categories["ai_files"].append(rel)
            matched = True
        if name in README_FILES:
            topo.categories["readme"].append(rel)
            matched = True
        if name in CHANGELOG_FILES:
            topo.categories["changelog"].append(rel)
            matched = True
        if name in GIT_META_FILES:
            topo.categories["git_meta"].append(rel)
            matched = True
        if name.startswith(LICENSE_FILES_PREFIX):
            topo.categories["license"].append(rel)
            matched = True
        if name in LOCKFILES:
            topo.categories["lockfiles"].append(rel)
            matched = True
        if name in MANIFEST_FILES:
            topo.categories["manifests"].append(rel)
            matched = True
        if name in EDITOR_FILES or any(name.startswith(p) for p in EDITOR_PREFIXES):
            topo.categories["editor"].append(rel)
            matched = True
        if name in CI_FILES or name == "Jenkinsfile":
            topo.categories["ci"].append(rel)
            matched = True
        if name in INFRA_FILES_OR_DIRS or name.startswith("Dockerfile"):
            topo.categories["infra"].append(rel)
            matched = True
        # config: dotfiles like .env.example or *.config.{js,ts,json} at root
        if (
            name in {".env.example", ".env.sample"}
            or re.match(r".+\.config\.(js|ts|cjs|mjs|json)$", name)
        ):
            topo.categories["config"].append(rel)
            matched = True
        # Generic .md files at root that are not special go into docs.
        if name.endswith(".md") and name not in CHANGELOG_FILES and name not in AI_FILES and name not in README_FILES:
            topo.categories["docs"].append(rel)
            matched = True
        if not matched:
            topo.categories["other"].append(rel)
        return

    # Directory-level classification
    if entry.is_dir():
        if name in DOC_DIRS:
            topo.categories["docs"].append(rel)
            matched = True
        if name in SOURCE_DIRS:
            topo.categories["sources"].append(rel)
            matched = True
        if name in TEST_DIRS:
            topo.categories["tests"].append(rel)
            matched = True
        if name in CONFIG_DIRS:
            topo.categories["config"].append(rel)
            matched = True
        if name in INFRA_FILES_OR_DIRS:
            topo.categories["infra"].append(rel)
            matched = True
        if name == ".github":
            # Surface .github/workflows/ as a CI signal
            wf = entry / "workflows"
            if wf.is_dir():
                topo.categories["ci"].append(_rel_with_slash(wf, root, is_dir=True))
            matched = True
        if name == ".circleci":
            topo.categories["ci"].append(rel)
            matched = True
        if not matched:
            topo.categories["other"].append(rel)
        return


def _rel_with_slash(p: Path, root: Path, *, is_dir: bool) -> str:
    """Return the path relative to root; append '/' for directories."""
    rel = p.relative_to(root).as_posix()
    return f"{rel}/" if is_dir else rel


# ----------------------------------------------------------------------
# Stack hints (T4) — lightweight pre-resolution
# ----------------------------------------------------------------------

_FRONTEND_DEPS: dict[str, str] = {
    "next": "Next.js",
    "react": "React",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "remix": "Remix",
    "astro": "Astro",
}

_BACKEND_NODE_DEPS: dict[str, str] = {
    "express": "Express",
    "fastify": "Fastify",
    "koa": "Koa",
    "@nestjs/core": "NestJS",
    "hono": "Hono",
}

_BACKEND_PYTHON_DEPS: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "aiohttp": "aiohttp",
    "starlette": "Starlette",
}

_DB_PYTHON_DEPS: dict[str, str] = {
    "psycopg": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL",
    "pymongo": "MongoDB",
    "redis": "Redis",
    "sqlalchemy": "SQLAlchemy",
}


def _resolve_stack_hints(root: Path, topo: Topology) -> None:
    """Fill topo.stack_hints by parsing known manifests at root."""
    pkg = root / "package.json"
    if pkg.is_file():
        deps = _read_package_json_deps(pkg)
        for dep, label in _FRONTEND_DEPS.items():
            if dep in deps and label not in topo.stack_hints["frontend"]:
                topo.stack_hints["frontend"].append(label)
        for dep, label in _BACKEND_NODE_DEPS.items():
            if dep in deps and label not in topo.stack_hints["backend"]:
                topo.stack_hints["backend"].append(label)
        if "typescript" in deps and "typescript" not in topo.stack_hints["lang"]:
            topo.stack_hints["lang"].append("typescript")
        elif pkg.is_file() and "javascript" not in topo.stack_hints["lang"]:
            topo.stack_hints["lang"].append("javascript")

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        deps = _read_pyproject_deps(pyproject)
        for dep, label in _BACKEND_PYTHON_DEPS.items():
            if dep in deps and label not in topo.stack_hints["backend"]:
                topo.stack_hints["backend"].append(label)
        for dep, label in _DB_PYTHON_DEPS.items():
            if dep in deps and label not in topo.stack_hints["db"]:
                topo.stack_hints["db"].append(label)
        if "python" not in topo.stack_hints["lang"]:
            topo.stack_hints["lang"].append("python")

    requirements = root / "requirements.txt"
    if requirements.is_file():
        deps = _read_requirements_deps(requirements)
        for dep, label in _BACKEND_PYTHON_DEPS.items():
            if dep in deps and label not in topo.stack_hints["backend"]:
                topo.stack_hints["backend"].append(label)
        if "python" not in topo.stack_hints["lang"]:
            topo.stack_hints["lang"].append("python")

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        if "rust" not in topo.stack_hints["lang"]:
            topo.stack_hints["lang"].append("rust")
        deps = _read_cargo_deps(cargo)
        for dep, label in (("axum", "Axum"), ("actix-web", "Actix"), ("rocket", "Rocket")):
            if dep in deps and label not in topo.stack_hints["backend"]:
                topo.stack_hints["backend"].append(label)

    gomod = root / "go.mod"
    if gomod.is_file() and "go" not in topo.stack_hints["lang"]:
        topo.stack_hints["lang"].append("go")


def _read_package_json_deps(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section.keys())
    return deps


def _read_pyproject_deps(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    deps: set[str] = set()
    project = data.get("project", {})
    for spec in project.get("dependencies", []):
        deps.add(_extract_pkg_name(spec))
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            for spec in group:
                deps.add(_extract_pkg_name(spec))
    # Poetry-style [tool.poetry.dependencies]
    poetry = data.get("tool", {}).get("poetry", {})
    poetry_deps = poetry.get("dependencies", {})
    if isinstance(poetry_deps, dict):
        deps.update(name for name in poetry_deps if name != "python")
    return deps


def _read_requirements_deps(path: Path) -> set[str]:
    deps: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            deps.add(_extract_pkg_name(line))
    except OSError:
        pass
    return deps


def _read_cargo_deps(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    deps: set[str] = set()
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section.keys())
    return deps


_PKG_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _extract_pkg_name(spec: str) -> str:
    """Extract the package name from a requirement specifier (e.g. 'fastapi>=0.100')."""
    spec = spec.strip().lower()
    m = _PKG_NAME_RE.match(spec)
    return m.group(1) if m else spec


# ----------------------------------------------------------------------
# Workspace detection (T3.1)
# ----------------------------------------------------------------------

def _detect_workspaces(root: Path, vault: Path | None) -> list[WorkspaceMember]:
    """Detect monorepo workspace members. Returns [] if none found."""
    members: list[WorkspaceMember] = []

    # 1. npm/pnpm/lerna workspaces via root package.json
    pkg = root / "package.json"
    if pkg.is_file():
        members.extend(_detect_npm_workspaces(pkg, root))

    # 2. pnpm-workspace.yaml (cheap parse without yaml dep — minimal grammar)
    pnpm = root / "pnpm-workspace.yaml"
    if pnpm.is_file() and not members:
        members.extend(_detect_pnpm_workspaces(pnpm, root))

    # 3. Cargo [workspace]
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        members.extend(_detect_cargo_workspaces(cargo, root))

    # 4. pyproject [tool.uv.workspace]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        members.extend(_detect_uv_workspaces(pyproject, root))

    # 5. Generic apps/+packages/ fallback only if nothing else detected
    if not members:
        members.extend(_detect_implicit_workspaces(root))

    # Resolve vault_project for each member if vault is provided
    if vault is not None:
        for m in members:
            m.vault_project = _resolve_vault_project(vault, m.name)

    return members


def _detect_npm_workspaces(pkg_path: Path, root: Path) -> list[WorkspaceMember]:
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    ws = data.get("workspaces")
    patterns: list[str] = []
    if isinstance(ws, list):
        patterns = [p for p in ws if isinstance(p, str)]
    elif isinstance(ws, dict):
        patterns = [p for p in ws.get("packages", []) if isinstance(p, str)]
    if not patterns:
        return []
    members: list[WorkspaceMember] = []
    for pattern in patterns:
        for member_pkg in _glob_pkgjson(root, pattern):
            try:
                mdata = json.loads(member_pkg.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            name = str(mdata.get("name") or member_pkg.parent.name)
            members.append(WorkspaceMember(
                name=name,
                path=member_pkg.parent.relative_to(root).as_posix(),
                manifest=member_pkg.relative_to(root).as_posix(),
            ))
    return members


def _detect_pnpm_workspaces(pnpm_path: Path, root: Path) -> list[WorkspaceMember]:
    """Minimal parse of `packages:` array in pnpm-workspace.yaml.

    Avoids a full YAML dep — handles the common shape only:
        packages:
          - 'apps/*'
          - 'packages/*'
    """
    patterns: list[str] = []
    in_packages = False
    try:
        for line in pnpm_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("packages:"):
                in_packages = True
                continue
            if in_packages:
                if stripped.startswith("- "):
                    patterns.append(stripped[2:].strip().strip("'\""))
                elif stripped and not stripped.startswith("#"):
                    in_packages = False
    except OSError:
        return []
    members: list[WorkspaceMember] = []
    for pattern in patterns:
        for member_pkg in _glob_pkgjson(root, pattern):
            try:
                mdata = json.loads(member_pkg.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            name = str(mdata.get("name") or member_pkg.parent.name)
            members.append(WorkspaceMember(
                name=name,
                path=member_pkg.parent.relative_to(root).as_posix(),
                manifest=member_pkg.relative_to(root).as_posix(),
            ))
    return members


def _detect_cargo_workspaces(cargo_path: Path, root: Path) -> list[WorkspaceMember]:
    try:
        data = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    ws = data.get("workspace")
    if not isinstance(ws, dict):
        return []
    members_paths = ws.get("members")
    if not isinstance(members_paths, list):
        return []
    out: list[WorkspaceMember] = []
    for entry in members_paths:
        if not isinstance(entry, str):
            continue
        for sub_cargo in _glob_subtoml(root, entry, "Cargo.toml"):
            try:
                sub_data = tomllib.loads(sub_cargo.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            pkg = sub_data.get("package", {})
            name = str(pkg.get("name") or sub_cargo.parent.name)
            out.append(WorkspaceMember(
                name=name,
                path=sub_cargo.parent.relative_to(root).as_posix(),
                manifest=sub_cargo.relative_to(root).as_posix(),
            ))
    return out


def _detect_uv_workspaces(pyproject_path: Path, root: Path) -> list[WorkspaceMember]:
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    ws = data.get("tool", {}).get("uv", {}).get("workspace", {})
    if not isinstance(ws, dict):
        return []
    members_paths = ws.get("members")
    if not isinstance(members_paths, list):
        return []
    out: list[WorkspaceMember] = []
    for entry in members_paths:
        if not isinstance(entry, str):
            continue
        for sub_pyproject in _glob_subtoml(root, entry, "pyproject.toml"):
            try:
                sub_data = tomllib.loads(sub_pyproject.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            project = sub_data.get("project", {})
            name = str(project.get("name") or sub_pyproject.parent.name)
            out.append(WorkspaceMember(
                name=name,
                path=sub_pyproject.parent.relative_to(root).as_posix(),
                manifest=sub_pyproject.relative_to(root).as_posix(),
            ))
    return out


def _detect_implicit_workspaces(root: Path) -> list[WorkspaceMember]:
    """Generic fallback: apps/*/{package.json,pyproject.toml} + packages/*/..."""
    out: list[WorkspaceMember] = []
    for parent in ("apps", "packages"):
        base = root / parent
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            for manifest_name in ("package.json", "pyproject.toml", "Cargo.toml"):
                manifest = child / manifest_name
                if not manifest.is_file():
                    continue
                name = _read_manifest_name(manifest, fallback=child.name)
                out.append(WorkspaceMember(
                    name=name,
                    path=child.relative_to(root).as_posix(),
                    manifest=manifest.relative_to(root).as_posix(),
                    workspace_implicit=True,
                ))
                break  # first manifest wins
    return out


def _glob_pkgjson(root: Path, pattern: str) -> list[Path]:
    """Expand a workspace glob and return matched package.json paths."""
    pattern = pattern.strip("./").rstrip("/")
    if pattern.endswith("/*"):
        base = root / pattern[:-2]
        if not base.is_dir():
            return []
        return [c / "package.json" for c in sorted(base.iterdir()) if c.is_dir() and (c / "package.json").is_file()]
    # exact path or single ** not handled — best-effort
    candidate = root / pattern / "package.json"
    return [candidate] if candidate.is_file() else []


def _glob_subtoml(root: Path, pattern: str, manifest_name: str) -> list[Path]:
    pattern = pattern.strip("./").rstrip("/")
    if pattern.endswith("/*"):
        base = root / pattern[:-2]
        if not base.is_dir():
            return []
        return [c / manifest_name for c in sorted(base.iterdir()) if c.is_dir() and (c / manifest_name).is_file()]
    candidate = root / pattern / manifest_name
    return [candidate] if candidate.is_file() else []


def _read_manifest_name(manifest: Path, fallback: str) -> str:
    try:
        if manifest.name == "package.json":
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return str(data.get("name") or fallback)
        if manifest.name in ("pyproject.toml", "Cargo.toml"):
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            project = data.get("project") or data.get("package", {})
            if isinstance(project, dict):
                return str(project.get("name") or fallback)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, OSError):
        pass
    return fallback


_SLUG_SANITIZE_RE = re.compile(r"[/@.]+")


def _slug_sanitize(name: str) -> str:
    """Sanitize a package name to a vault-compatible slug.

    @acme/web -> acme-web ; com.example.app -> com-example-app
    """
    s = name.lstrip("@").lower()
    s = _SLUG_SANITIZE_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _resolve_vault_project(vault: Path, member_name: str) -> str:
    """Find a vault project matching member_name. Returns "" if none."""
    candidate = _slug_sanitize(member_name)
    if not candidate:
        return ""
    projects_dir = vault / "10-episodes" / "projects"
    if (projects_dir / candidate).is_dir():
        return candidate
    return ""
