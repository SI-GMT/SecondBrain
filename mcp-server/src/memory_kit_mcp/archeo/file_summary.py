"""Per-file structural summary extraction for archeo Phase 3 body enrichment.

Reads a file at a given git commit and extracts language-specific signals
(class declarations, method signatures, top-of-file docstrings, schema
lines) so the archive body can pre-fill the **Analyse technique** section
with mechanical content instead of placeholder ``_(LLM TODO ...)_`` markers.

Doctrine : the LLM is NOT a substitute for reading the actual files. The
2026-05-09 IRIS USER case study showed that when archives only carry
``subject + diff stats``, the perimeter is preserved (50 files captured
correctly) but the **functional + technical content** of those files is
lost — the archive becomes a mechanical commit dump with no narrative
value. This module bridges that gap by extracting structure cheaply
(regex-based, no AST) and bounding I/O (max files + max bytes per file).

Languages supported (regex-based extractors) :

- ``.cls``      — InterSystems IRIS ObjectScript : ``Class``, ``Property``,
                  ``Method``, ``ClassMethod``, ``Storage`` declarations.
- ``.py``       — top docstring, ``class``, top-level ``def``.
- ``.js``/``.jsx``/``.ts``/``.tsx``/``.mjs`` — top JSDoc comment, ``export
                  class``, ``export function``, ``export const``.
- ``.sql``      — ``CREATE TABLE`` / ``CREATE INDEX`` / ``CREATE VIEW``
                  / ``ALTER TABLE`` lines.
- ``.md``       — first H1 + first paragraph.
- everything else — first 200 bytes as raw context (informational).

Bounded resources :

- ``MAX_FILES_PER_CYCLE`` = 30 (extra files listed without extraction).
- ``MAX_BYTES_PER_FILE`` = 16 KiB (head only — class/function declarations
  live near the top in well-structured code, and the goal is structural
  summary not full content).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES_PER_CYCLE: int = 30
MAX_BYTES_PER_FILE: int = 16 * 1024


@dataclass
class FileSummary:
    """Structural summary of one file at one commit."""

    path: str
    language: str  # 'cls' | 'py' | 'js' | 'ts' | 'sql' | 'md' | 'unknown'
    top_doc: str = ""  # first docstring or comment block (max ~3 lines)
    classes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    schema_lines: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    error: str = ""  # populated when read failed (binary, missing, etc.)


def _git_show_file(repo: Path, sha: str, file_path: str) -> str | None:
    """Read ``file_path`` at ``sha`` via ``git show {sha}:{file}``.

    Returns ``None`` on read failure (binary file, file deleted at sha,
    git error). Truncates to ``MAX_BYTES_PER_FILE`` because structural
    declarations live near the top — full file is wasted I/O.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{sha}:{file_path}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        raw = result.stdout[:MAX_BYTES_PER_FILE]
        return raw.decode("utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None


def _detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".cls":
        return "cls"
    if suffix == ".py":
        return "py"
    if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        return "js"
    if suffix in {".ts", ".tsx"}:
        return "ts"
    if suffix == ".sql":
        return "sql"
    if suffix == ".md":
        return "md"
    return "unknown"


# IRIS ObjectScript .cls patterns
_CLS_CLASS_RE = re.compile(
    r"^Class\s+([A-Za-z][\w.]*)(?:\s+Extends\s+([\w.,%\s()]+))?",
    re.MULTILINE,
)
_CLS_PROPERTY_RE = re.compile(
    r"^(?:Property|Relationship)\s+([A-Za-z]\w*)\s+As\s+([\w.%]+)",
    re.MULTILINE,
)
_CLS_METHOD_RE = re.compile(
    r"^(?:Method|ClassMethod|Query)\s+([A-Za-z]\w*)\s*\(",
    re.MULTILINE,
)
_CLS_TOP_COMMENT_RE = re.compile(
    r"\A\s*((?:///[^\n]*\n){1,5})",
    re.MULTILINE,
)


def _extract_cls(content: str) -> dict:
    out: dict = {"classes": [], "methods": [], "properties": [], "top_doc": ""}
    top = _CLS_TOP_COMMENT_RE.match(content)
    if top:
        out["top_doc"] = "\n".join(
            ln.lstrip("/").strip() for ln in top.group(1).strip().splitlines()
        )
    for m in _CLS_CLASS_RE.finditer(content):
        name = m.group(1)
        ext = m.group(2)
        if ext:
            out["classes"].append(f"{name} extends {ext.strip()}")
        else:
            out["classes"].append(name)
    for m in _CLS_PROPERTY_RE.finditer(content):
        out["properties"].append(f"{m.group(1)} : {m.group(2)}")
    for m in _CLS_METHOD_RE.finditer(content):
        out["methods"].append(m.group(1))
    return out


# Python patterns
_PY_DOCSTRING_RE = re.compile(
    r'\A(?:(?:#.*\n)|\s)*("""|\'\'\')(.*?)\1',
    re.DOTALL,
)
_PY_CLASS_RE = re.compile(r"^class\s+([A-Za-z]\w*)\s*[:(]", re.MULTILINE)
_PY_DEF_RE = re.compile(r"^def\s+([A-Za-z]\w*)\s*\(", re.MULTILINE)


def _extract_py(content: str) -> dict:
    out: dict = {"classes": [], "methods": [], "properties": [], "top_doc": ""}
    doc = _PY_DOCSTRING_RE.match(content)
    if doc:
        body = doc.group(2).strip().splitlines()
        out["top_doc"] = " ".join(ln.strip() for ln in body[:3]).strip()
    for m in _PY_CLASS_RE.finditer(content):
        out["classes"].append(m.group(1))
    for m in _PY_DEF_RE.finditer(content):
        out["methods"].append(m.group(1))
    return out


# JS/TS patterns
_JS_TOP_COMMENT_RE = re.compile(r"\A\s*/\*\*?(.*?)\*/", re.DOTALL)
_JS_EXPORT_CLASS_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z]\w*)",
    re.MULTILINE,
)
_JS_EXPORT_FN_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z]\w*)",
    re.MULTILINE,
)
_JS_EXPORT_CONST_RE = re.compile(
    r"^\s*export\s+(?:const|let|var)\s+([A-Za-z]\w*)",
    re.MULTILINE,
)


def _extract_js(content: str) -> dict:
    out: dict = {"classes": [], "methods": [], "properties": [], "top_doc": ""}
    top = _JS_TOP_COMMENT_RE.match(content)
    if top:
        body = re.sub(r"\n\s*\*\s?", " ", top.group(1)).strip()
        out["top_doc"] = body[:200]
    for m in _JS_EXPORT_CLASS_RE.finditer(content):
        out["classes"].append(m.group(1))
    for m in _JS_EXPORT_FN_RE.finditer(content):
        out["methods"].append(m.group(1))
    for m in _JS_EXPORT_CONST_RE.finditer(content):
        out["properties"].append(m.group(1))
    return out


# SQL patterns
_SQL_DDL_RE = re.compile(
    r"^\s*(CREATE\s+(?:TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER)|"
    r"ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX|VIEW))\s+([\w.]+)",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_sql(content: str) -> dict:
    out: dict = {"classes": [], "methods": [], "properties": [], "top_doc": "", "schema_lines": []}
    for m in _SQL_DDL_RE.finditer(content):
        out["schema_lines"].append(f"{m.group(1).upper()} {m.group(2)}")
    return out


# Markdown
_MD_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _extract_md(content: str) -> dict:
    out: dict = {"classes": [], "methods": [], "properties": [], "top_doc": ""}
    h1 = _MD_H1_RE.search(content)
    if h1:
        out["top_doc"] = h1.group(1).strip()
    return out


def _extract_unknown(content: str) -> dict:
    snippet = content[:200].strip().replace("\n", " ")
    return {"classes": [], "methods": [], "properties": [], "top_doc": snippet}


_EXTRACTORS = {
    "cls": _extract_cls,
    "py": _extract_py,
    "js": _extract_js,
    "ts": _extract_js,
    "sql": _extract_sql,
    "md": _extract_md,
}


def extract_file_summary(
    repo: Path, sha: str, file_path: str
) -> FileSummary:
    """Read ``file_path`` at ``sha`` and return a structural summary.

    Empty / error summary on read failure (binary, deleted, unreadable).
    """
    language = _detect_language(file_path)
    content = _git_show_file(repo, sha, file_path)
    if content is None:
        return FileSummary(
            path=file_path,
            language=language,
            error="file unreadable at this commit (binary, deleted, or git error)",
        )
    extractor = _EXTRACTORS.get(language, _extract_unknown)
    raw = extractor(content)
    return FileSummary(
        path=file_path,
        language=language,
        top_doc=raw.get("top_doc", ""),
        classes=raw.get("classes", []),
        methods=raw.get("methods", []),
        properties=raw.get("properties", []),
        schema_lines=raw.get("schema_lines", []),
    )


def summarize_files(
    repo: Path, sha: str, files: list[str]
) -> tuple[list[FileSummary], int]:
    """Extract summaries for up to ``MAX_FILES_PER_CYCLE`` files at ``sha``.

    Returns ``(summaries, truncated_count)``. ``truncated_count`` is the
    number of files past the cap that were not inspected.
    """
    capped = files[:MAX_FILES_PER_CYCLE]
    truncated = max(0, len(files) - MAX_FILES_PER_CYCLE)
    return [extract_file_summary(repo, sha, f) for f in capped], truncated


def render_technical_section(
    summaries: list[FileSummary], truncated: int
) -> str:
    """Render extracted summaries as a Markdown ``## Analyse technique``
    body block. Pre-fills the section so the LLM has actual content to
    build on instead of a blank ``_(LLM TODO ...)_`` marker.
    """
    if not summaries:
        return (
            "_(no files inspected — perimeter empty or all files unreadable "
            "at this commit.)_"
        )

    grouped: dict[str, list[FileSummary]] = {}
    for s in summaries:
        grouped.setdefault(s.language, []).append(s)

    parts: list[str] = []
    parts.append(
        f"_{len(summaries)} file(s) inspected"
        + (f" (+ {truncated} more not inspected — cap "
           f"{MAX_FILES_PER_CYCLE})" if truncated else "")
        + "._"
    )
    parts.append("")

    for lang in sorted(grouped):
        files_in_lang = grouped[lang]
        parts.append(f"### {lang} ({len(files_in_lang)} file(s))")
        parts.append("")
        for s in files_in_lang:
            parts.append(f"- **`{s.path}`**")
            if s.error:
                parts.append(f"  - _({s.error})_")
                continue
            if s.top_doc:
                doc = s.top_doc.replace("\n", " ")[:160]
                parts.append(f"  - _doc_ : {doc}")
            if s.classes:
                parts.append(
                    f"  - _classes_ : "
                    + ", ".join(f"`{c}`" for c in s.classes[:8])
                    + (f" _(+{len(s.classes) - 8} more)_"
                       if len(s.classes) > 8 else "")
                )
            if s.properties:
                parts.append(
                    f"  - _properties_ : "
                    + ", ".join(f"`{p}`" for p in s.properties[:8])
                    + (f" _(+{len(s.properties) - 8} more)_"
                       if len(s.properties) > 8 else "")
                )
            if s.methods:
                parts.append(
                    f"  - _methods_ : "
                    + ", ".join(f"`{m}`" for m in s.methods[:8])
                    + (f" _(+{len(s.methods) - 8} more)_"
                       if len(s.methods) > 8 else "")
                )
            if s.schema_lines:
                parts.append(
                    f"  - _schema_ : "
                    + ", ".join(f"`{ln}`" for ln in s.schema_lines[:5])
                )
        parts.append("")

    parts.append(
        "_Mechanical extraction (regex-based, no AST). LLM verifier MAY "
        "augment this section with cross-file rationale + risk analysis._"
    )
    return "\n".join(parts)
