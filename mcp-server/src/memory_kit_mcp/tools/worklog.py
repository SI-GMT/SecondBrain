"""mem_worklog — Collect a week's archives across all projects for a worklog.

Spec: core/procedures/mem-worklog.md

Deterministic collector. Given a reference date (``week_of``, default = today),
it resolves the Monday→Sunday ISO week, then walks EVERY project's (and
domain's) ``archives/`` folder, keeping the archives whose filename date prefix
falls inside that week. It groups them by day, parses a head excerpt + a
"next steps" block from each body, and computes a naive equal-split proration of
a configurable daily amplitude (default 7h) across the distinct projects active
each day.

The naive proration is a STARTING POINT — the LLM caller refines it with density
judgment (how much of each day a project actually consumed) and renders the final
report using the vault worklog template (``99-meta/worklog-template.md``) when
present. The tool stays purely mechanical: dates, collection, equal split. No
semantic weighting, no report prose.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import WorklogDay, WorklogResult, WorklogSession
from memory_kit_mcp.vault import frontmatter, paths

_DEFAULT_AMPLITUDE = 7.0
_HEAD_CHARS = 500
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# The worklog reports are themselves persisted as archives under this domain.
# They MUST be excluded from collection, otherwise each weekly worklog would be
# re-counted as a "session" of the following weeks — a self-referential loop.
_WORKLOG_DOMAIN = "worklogs"

# Default worklog template seeded into the vault on first use when none exists.
# It is a FORMAT, never a referential — it must NOT hardcode project codes,
# category labels or perimeters. Categories are derived at render time (default:
# the project slug upper-cased). Kept in sync with the "Default template" block
# of core/procedures/mem-worklog.md, which skills-fallback mode writes by hand.
_DEFAULT_TEMPLATE_FM: dict[str, object] = {
    "title": "Worklog template",
    "kind": "reference",
    "amplitude_default": 7,
}
_DEFAULT_TEMPLATE_BODY = """# Worklog template

Render format for `/mem-worklog` — the report STRUCTURE, not a referential.
This file describes how the weekly report looks; it never lists fixed project
codes or perimeters. Categories are derived at render time from the projects
active that week (default: the project slug, upper-cased). Edit this file to fit
your own format. Default amplitude: 7h/day (Mon–Fri, 35h).

## Report structure

```
TASK LIST
•  [CATEGORY]
   o  [SUBPROJECT] one line per work item

IN PROGRESS / DONE
•  [CATEGORY]
   o  [SUBPROJECT] item
       ▪ progress note (done / in progress)

HIGHLIGHTS
•  the 1–3 biggest deliverables of the week (or "none")

NEXT WEEK
•  [CATEGORY]
   o  [SUBPROJECT]  - P0|P1
       ▪ objective (from the "next steps" of the latest archives)
```

## Rules

- Always produce the daily hours table first (rows = weekdays, columns =
  projects, totals + %), then the report.
- `[CATEGORY]` = the project slug upper-cased by default; group several slugs
  under a broader label only when the week's content clearly justifies it —
  never from a hardcoded mapping.
- A session is often archived the next morning → attribute the work to the day
  it describes, not the file timestamp.
- The proration is an estimate from archive density/timestamps, not real
  time-tracking. State this at the end.
- P0 (blocking/urgent) / P1 (important, non-blocking) on the next-week section.
"""

# Filename pattern: 2026-06-05-17h58-{slug}-{subject}.md
_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{2}h\d{2})-"
    r"(?P<slug>[^-]+(?:-[^-]+)*?)-(?P<subject>.+)\.md$"
)

# Headings that introduce the "what's left / next" block, any language.
_NEXT_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:\d+\.\s*)?"
    r"(reste\s+à\s+faire|prochaines?\s+étapes?|à\s+faire|next\s+steps?|"
    r"reprise|semaine\s+prochaine|todo)\b.*$",
    re.IGNORECASE,
)
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S")


def _parse_filename(filename: str) -> tuple[str | None, str | None, str | None]:
    """Extract (date, time, subject) from an archive filename. Best-effort."""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None, None, None
    return m.group("date"), m.group("time"), m.group("subject").replace("-", " ")


def _parse_date(s: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _week_bounds(ref: _dt.date) -> tuple[_dt.date, _dt.date]:
    """Monday and Sunday of the ISO week containing ``ref``."""
    monday = ref - _dt.timedelta(days=ref.weekday())
    return monday, monday + _dt.timedelta(days=6)


def _head_excerpt(body: str, max_chars: int = _HEAD_CHARS) -> str:
    """First meaningful lines of the body, skipping headings and blockquotes."""
    lines = [
        ln for ln in body.strip().splitlines()
        if ln.strip()
        and not ln.strip().startswith(">")
        and not ln.strip().startswith("#")
    ]
    if not lines:
        return ""
    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _next_steps_block(body: str, max_chars: int = _HEAD_CHARS) -> str:
    """Extract the body of the first 'next steps / reste à faire' section."""
    lines = body.splitlines()
    out: list[str] = []
    capturing = False
    for ln in lines:
        if _NEXT_HEADING_RE.match(ln.strip()):
            capturing = True
            continue
        if capturing:
            # Stop at the next heading of any kind.
            if _ANY_HEADING_RE.match(ln.strip()):
                break
            out.append(ln)
    text = "\n".join(out).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _round_quarter(h: float) -> float:
    """Round to the nearest 0.25h."""
    return round(h * 4) / 4


def _collect(vault: Path, start: _dt.date, end: _dt.date) -> list[WorklogSession]:
    """Walk every project + domain archives/ folder within [start, end]."""
    sessions: list[WorklogSession] = []
    sources: list[tuple[str, str, Path]] = []
    for slug in paths.list_projects(vault):
        sources.append((slug, "project", paths.project_dir(vault, slug)))
    for slug in paths.list_domains(vault):
        if slug == _WORKLOG_DOMAIN:
            continue  # never count persisted worklogs as work sessions
        sources.append((slug, "domain", paths.domain_dir(vault, slug)))

    for slug, kind, folder in sources:
        archives_dir = folder / "archives"
        if not archives_dir.exists():
            continue
        for archive in sorted(archives_dir.glob("*.md")):
            date_str, time_str, subject = _parse_filename(archive.name)
            d = _parse_date(date_str) if date_str else None
            if d is None or d < start or d > end:
                continue
            try:
                _, body = frontmatter.read(archive)
            except (ValueError, OSError):
                body = ""
            sessions.append(
                WorklogSession(
                    date=date_str,  # type: ignore[arg-type]
                    time=time_str,
                    weekday=_WEEKDAYS[d.weekday()],
                    slug=slug,
                    kind=kind,
                    filename=archive.name,
                    subject=subject,
                    excerpt=_head_excerpt(body),
                    next_steps=_next_steps_block(body),
                )
            )
    sessions.sort(key=lambda s: (s.date, s.time or "", s.slug))
    return sessions


def _build_days(
    sessions: list[WorklogSession],
    start: _dt.date,
    end_inclusive: _dt.date,
    amplitude: float,
) -> tuple[list[WorklogDay], dict[str, float]]:
    """Per-day equal split of amplitude across distinct projects active that day."""
    by_date: dict[str, list[WorklogSession]] = {}
    for s in sessions:
        by_date.setdefault(s.date, []).append(s)

    days: list[WorklogDay] = []
    totals: dict[str, float] = {}
    cur = start
    while cur <= end_inclusive:
        iso = cur.isoformat()
        day_sessions = by_date.get(iso, [])
        # Distinct projects active that day, preserving first-seen order.
        projects: list[str] = []
        for s in day_sessions:
            if s.slug not in projects:
                projects.append(s.slug)
        hours_by_project: dict[str, float] = {}
        if projects:
            share = _round_quarter(amplitude / len(projects))
            for p in projects:
                hours_by_project[p] = share
                totals[p] = totals.get(p, 0.0) + share
        days.append(
            WorklogDay(
                date=iso,
                weekday=_WEEKDAYS[cur.weekday()],
                is_weekend=cur.weekday() >= 5,
                sessions=len(day_sessions),
                projects=projects,
                hours_by_project=hours_by_project,
            )
        )
        cur += _dt.timedelta(days=1)
    return days, totals


def _format_summary_md(res: WorklogResult) -> str:
    lines = [
        f"## Worklog — semaine {res.week_start} → {res.week_end}",
        "",
        f"_{res.sessions_total} session(s) archivée(s) sur "
        f"{len(res.projects)} projet(s). Amplitude {res.amplitude_hours:g}h/jour. "
        "Prorata naïf (split égal/jour) — à affiner selon la densité réelle._",
        "",
    ]
    # Daily table
    lines.append("| Jour | Date | Sessions | Projets actifs | Prorata naïf |")
    lines.append("|---|---|--:|---|---|")
    for d in res.days:
        if d.is_weekend and not res.include_weekend:
            continue
        if d.projects:
            split = ", ".join(
                f"{p} {d.hours_by_project[p]:g}h" for p in d.projects
            )
        else:
            split = "—"
        lines.append(
            f"| {d.weekday} | {d.date} | {d.sessions} | "
            f"{', '.join(d.projects) or '—'} | {split} |"
        )
    lines.append("")
    # Per-project totals
    lines.append("**Total prorata naïf par projet :**")
    if res.hours_by_project_total:
        grand = sum(res.hours_by_project_total.values()) or 1.0
        for p, h in sorted(
            res.hours_by_project_total.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"- {p} : {h:g}h ({h / grand * 100:.0f}%)")
    else:
        lines.append("- _(aucune session sur la période)_")
    lines.append("")
    if res.template_seeded:
        lines.append(
            "_Template par défaut déployé (première utilisation) → "
            "`99-meta/worklog-template.md`. C'est un **format** (structure), pas "
            "un référentiel : édite-le pour ton rendu. Catégories dérivées du "
            "slug projet._"
        )
    elif res.template_exists:
        lines.append(
            "_Template worklog trouvé dans le vault → suivre son **format** pour "
            "le rendu final (niveau `detailed`). Catégories dérivées au rendu, "
            "pas d'un référentiel figé._"
        )
    else:
        lines.append(
            "_Aucun template worklog dans le vault (99-meta/worklog-template.md) "
            "→ rendu générique._"
        )
    lines.append("")
    lines.append("### Rendu attendu — 3 niveaux de verbosité")
    lines.append(
        "Affine d'abord le prorata par densité, puis produis **trois** versions "
        "dans la langue de l'utilisateur :"
    )
    lines.append(
        "- **brief** — une ligne par projet actif (scan rapide / chat). Pas de "
        "tableau, pas de sections."
    )
    lines.append(
        "- **digest** — version courriel condensée : tableau d'heures + FAIT "
        "MARQUANT + 1 ligne par catégorie. Auto-suffisant, court."
    )
    lines.append(
        "- **detailed** — version réunion étoffée : rapport complet (LISTE DES "
        "TACHES, EN COURS/FAIT par session, FAIT MARQUANT, SEMAINE PROCHAINE "
        "P0/P1). Suit le template quand présent."
    )
    lines.append("")
    lines.append(
        "Puis **persiste** les trois dans une archive hebdo chronodatée : "
        "rappelle `mem_worklog` avec `phase=\"persist\"`, `week_of`, "
        "`brief_md`, `digest_md`, `detailed_md` (+ `hours_by_project` affiné et "
        "`amplitude_hours`). L'archive est écrite sous le domaine `worklogs` "
        "(créé au besoin), un fichier par semaine."
    )
    return "\n".join(lines)


def _persist(
    vault: Path,
    monday: _dt.date,
    sunday: _dt.date,
    brief_md: str,
    digest_md: str,
    detailed_md: str,
    amplitude_hours: float,
    hours_by_project: dict[str, float] | None,
) -> WorklogResult:
    """Write the week's worklog (3 verbosity sections) as a domain archive.

    Idempotent per ISO week: the filename is derived from the Monday date +
    ISO week number, so re-running for the same week overwrites the archive
    and patches (not duplicates) the history line. Auto-creates the
    ``worklogs`` domain skeleton on first run.
    """
    from memory_kit_mcp.tools.init_project import execute_init_project

    year, week_number, _ = monday.isocalendar()

    # Ensure the worklogs domain exists.
    files_created: list[str] = []
    if paths.resolve_slug(vault, _WORKLOG_DOMAIN) is None:
        rep = execute_init_project(
            vault,
            _WORKLOG_DOMAIN,
            kind="domain",
            scope="work",
            display="Worklogs",
        )
        files_created.extend(rep.files_created)

    folder = paths.domain_dir(vault, _WORKLOG_DOMAIN)
    archives_dir = folder / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)

    week_label = f"S{week_number:02d}"
    archive_filename = f"{monday.isoformat()}-worklog-{week_label}.md"
    archive_path = archives_dir / archive_filename
    is_update = archive_path.exists()

    totals = {k: _round_quarter(v) for k, v in (hours_by_project or {}).items()}
    week_span = f"{monday.isoformat()} → {sunday.isoformat()}"

    fm: dict[str, object] = {
        "domain": _WORKLOG_DOMAIN,
        "tags": [
            f"domain/{_WORKLOG_DOMAIN}",
            "zone/episodes",
            "kind/archive",
            "kind/worklog",
        ],
        "zone": "episodes",
        "kind": "archive",
        "slug": _WORKLOG_DOMAIN,
        "date": monday.isoformat(),
        "worklog": True,
        "week_number": week_number,
        "week_year": year,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "amplitude_hours": amplitude_hours,
        "hours_by_project": totals,
        "display": f"Worklog {year}-{week_label} ({week_span})",
    }

    body = (
        f"# Worklog — semaine {week_span} ({week_label})\n\n"
        f"## Brief\n\n{brief_md.strip()}\n\n"
        f"## Digest (courriel)\n\n{digest_md.strip()}\n\n"
        f"## Détaillé (réunion)\n\n{detailed_md.strip()}\n"
    )
    frontmatter.write(archive_path, fm, body)
    if is_update:
        files_modified = [archive_path.relative_to(vault).as_posix()]
    else:
        files_created.append(archive_path.relative_to(vault).as_posix())
        files_modified = []

    # history.md — prepend the week's line if not already present (idempotent).
    history_path = folder / "history.md"
    h_fm, h_body = frontmatter.read(history_path)
    history_line = (
        f"- [{monday.isoformat()} — Worklog {week_label} ({week_span})]"
        f"(archives/{archive_filename})"
    )
    if f"(archives/{archive_filename})" not in h_body:
        lines = h_body.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if not inserted and line.startswith("# "):
                out.append("")
                out.append(history_line)
                inserted = True
        if not inserted:
            out.append(history_line)
        h_body = "\n".join(out) + "\n"
        # Drop the "(no sessions yet …)" placeholder seeded by init_project.
        h_body = re.sub(
            r"\n?_\(no sessions yet[^\n]*\)_\n?", "\n", h_body
        )
        frontmatter.write(history_path, h_fm, h_body)
        files_modified.append(history_path.relative_to(vault).as_posix())

    # context.md — point at the latest worklog.
    ctx_path = folder / "context.md"
    ctx_fm, _ = frontmatter.read(ctx_path)
    ctx_fm["last-session"] = _dt.date.today().isoformat()
    ctx_fm["phase"] = f"dernier relevé {year}-{week_label}"
    ctx_body = (
        "> Snapshot mutable du domaine worklogs. "
        "Voir aussi : [historique](history.md) · [archives/](archives/)\n\n"
        "# Worklogs — Contexte actif\n\n"
        f"## Dernier relevé : {year}-{week_label}\n\n"
        f"- Semaine : {week_span}\n"
        f"- Amplitude : {amplitude_hours:g}h/jour\n"
        f"- Heures par projet : "
        + (
            ", ".join(f"{p} {h:g}h" for p, h in sorted(totals.items(), key=lambda kv: -kv[1]))
            if totals
            else "(non renseignées)"
        )
        + "\n\n"
        "Chaque archive hebdo contient 3 niveaux : **brief** (1 ligne/projet), "
        "**digest** (courriel), **détaillé** (réunion).\n"
    )
    frontmatter.write(ctx_path, ctx_fm, ctx_body)
    files_modified.append(ctx_path.relative_to(vault).as_posix())

    rel_archive = archive_path.relative_to(vault).as_posix()
    verb = "Mis à jour" if is_update else "Créé"
    summary = (
        f"**mem_worklog (persist)** — semaine {week_span} ({week_label})\n\n"
        f"- {verb} `{rel_archive}` (brief + digest + détaillé)\n"
        f"- Domaine `{_WORKLOG_DOMAIN}` : history.md + context.md à jour\n"
    )

    res = WorklogResult(
        week_start=monday.isoformat(),
        week_end=sunday.isoformat(),
        amplitude_hours=amplitude_hours,
        include_weekend=True,
        hours_by_project_total=totals,
        persisted=True,
        week_number=week_number,
        archive_path=rel_archive,
        files_created=files_created,
        files_modified=files_modified,
        summary_md=summary,
    )
    return res


def register(mcp: FastMCP) -> None:
    """Register mem_worklog with the FastMCP instance."""

    @mcp.tool()
    def mem_worklog(
        week_of: str = Field(
            "",
            description=(
                "Reference date (YYYY-MM-DD) anchoring the week. The tool uses "
                "the Monday→Sunday ISO week containing it. Empty = today."
            ),
        ),
        amplitude_hours: float = Field(
            _DEFAULT_AMPLITUDE,
            gt=0,
            le=24,
            description="Worked hours per day used for the naive proration (default 7).",
        ),
        include_weekend: bool = Field(
            False,
            description="Include Saturday/Sunday rows in the breakdown (default False).",
        ),
        phase: str = Field(
            "collect",
            description=(
                "'collect' (default, read-only): gather the week's archives + "
                "naive proration. 'persist': write the 3-verbosity weekly "
                "worklog (brief/digest/detailed) as a chronodated archive under "
                "the 'worklogs' domain. The persist phase requires brief_md, "
                "digest_md and detailed_md."
            ),
        ),
        brief_md: str = Field(
            "",
            description=(
                "persist phase only: the BRIEF rendering — one line per active "
                "project, no table. The LLM composes this after refining the "
                "proration."
            ),
        ),
        digest_md: str = Field(
            "",
            description=(
                "persist phase only: the DIGEST rendering — condensed email "
                "version (hours table + highlights + one line per category)."
            ),
        ),
        detailed_md: str = Field(
            "",
            description=(
                "persist phase only: the DETAILED rendering — full meeting "
                "report following the vault template when present."
            ),
        ),
        hours_by_project: dict[str, float] | None = Field(
            None,
            description=(
                "persist phase only: the LLM's density-refined hours per "
                "project for the week, stored in the archive frontmatter for "
                "later querying. Optional."
            ),
        ),
    ) -> WorklogResult:
        """Collect a week's archives, then persist a 3-verbosity worklog report.

        Two phases:

        - ``phase="collect"`` (default, read-only): returns every archived
          session of the Monday→Sunday week, grouped by day, each with a head
          excerpt + extracted next-steps block, plus a naive equal-split
          proration of ``amplitude_hours`` across the distinct projects active
          each day. ``summary_md`` renders a ready-to-display daily table +
          per-project totals + the 3-verbosity rendering brief. The LLM refines
          the proration by density and writes brief/digest/detailed using the
          vault worklog template (surfaced in ``template_md`` when present).

        - ``phase="persist"`` (writes): given the LLM-composed ``brief_md``,
          ``digest_md`` and ``detailed_md``, writes a single chronodated archive
          for the week under the ``worklogs`` domain (auto-created), with the
          three renderings as H2 sections, and updates that domain's history.md
          + context.md. Idempotent per ISO week (re-running overwrites).
        """
        config = get_config()
        vault = config.vault

        if week_of.strip():
            ref = _parse_date(week_of.strip())
            if ref is None:
                raise ValueError(
                    f"Invalid week_of date {week_of!r}; expected YYYY-MM-DD."
                )
        else:
            ref = _dt.date.today()

        monday, sunday = _week_bounds(ref)

        if phase == "persist":
            if not (brief_md.strip() and digest_md.strip() and detailed_md.strip()):
                raise ValueError(
                    "persist phase requires non-empty brief_md, digest_md and "
                    "detailed_md."
                )
            return _persist(
                vault,
                monday,
                sunday,
                brief_md,
                digest_md,
                detailed_md,
                amplitude_hours,
                hours_by_project,
            )
        if phase != "collect":
            raise ValueError(
                f"Unknown phase {phase!r}; expected 'collect' or 'persist'."
            )

        # Collection always spans the full week; the display window may stop on
        # Friday, but a Saturday/Sunday archive should still be collected so the
        # LLM is aware of weekend work even when include_weekend display is off.
        sessions = _collect(vault, monday, sunday)
        display_end = sunday if include_weekend else monday + _dt.timedelta(days=4)
        days, totals = _build_days(
            sessions, monday, sunday, amplitude_hours
        )

        projects = sorted({s.slug for s in sessions})
        totals_rounded = {k: _round_quarter(v) for k, v in totals.items()}

        template_path = vault / paths.ZONE_META / "worklog-template.md"
        template_seeded = False
        if not template_path.exists():
            # First use: deploy the default format-only template so the user has
            # a structure to build on. One-time config bootstrap, idempotent.
            template_path.parent.mkdir(parents=True, exist_ok=True)
            frontmatter.write(
                template_path, dict(_DEFAULT_TEMPLATE_FM), _DEFAULT_TEMPLATE_BODY
            )
            template_seeded = True
        template_exists = template_path.exists()
        template_md = ""
        if template_exists:
            try:
                template_md = template_path.read_text(encoding="utf-8")
            except OSError:
                template_exists = False

        res = WorklogResult(
            week_start=monday.isoformat(),
            week_end=display_end.isoformat(),
            amplitude_hours=amplitude_hours,
            include_weekend=include_weekend,
            sessions_total=len(sessions),
            projects=projects,
            sessions=sessions,
            days=days,
            hours_by_project_total=totals_rounded,
            template_exists=template_exists,
            template_md=template_md,
            template_seeded=template_seeded,
        )
        res.summary_md = _format_summary_md(res)
        return res
