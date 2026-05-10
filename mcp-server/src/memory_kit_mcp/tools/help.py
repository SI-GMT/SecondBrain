"""mem_help — Localized help for ``mem-*`` commands.

Spec: core/procedures/mem-help.md.

Reads the procedure files in ``{kit_repo}/core/procedures/mem-*.md`` and
returns a structured help payload (title + description + triggers +
arguments + examples + see-also). Wrapper labels are localized via
``core/i18n/strings.yaml`` (en/fr/es/de/ru). Procedure body content stays
in canonical English (the procedures are the LLM-side source of truth and
must remain precise EN).

Two modes :

- ``mem_help()`` (no command) — returns a categorized inventory of all
  ``mem-*`` commands with one-line descriptions.
- ``mem_help(command="mem-archeo")`` — returns the help for that specific
  command : description, triggers (langage naturel + slash invocations),
  arguments, examples, see-also.

Language resolution priority :

1. Explicit ``lang`` parameter when provided.
2. ``language`` field of ``~/.memory-kit/config.json``.
3. Fallback to ``en``.

Doctrine : the body content of the procedures (their natural-language
explanations, examples, doctrine) is intentionally NOT translated — the
procedures are read by LLMs that perform best on EN. Only the surrounding
chrome (titles, section labels, navigation) translates so the user sees
their language while the LLM sees its EN substrate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import HelpResult, _CommandEntry
from memory_kit_mcp.update_check import check_for_update

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


# ---------------------------------------------------------------------------
# Categorization — used by general help to group commands
# ---------------------------------------------------------------------------

_CATEGORY_OF: dict[str, str] = {
    # Session cycle
    "mem-recall": "session",
    "mem-archive": "session",
    # Capture & ingestion
    "mem": "capture",
    "mem-doc": "capture",
    "mem-note": "capture",
    "mem-principle": "capture",
    "mem-goal": "capture",
    "mem-person": "capture",
    "mem-historize": "capture",
    # Repo archeology
    "mem-archeo": "archeo",
    "mem-archeo-plan": "archeo",
    "mem-archeo-context": "archeo",
    "mem-archeo-stack": "archeo",
    "mem-archeo-git": "archeo",
    "mem-archeo-atlassian": "archeo",
    "mem-archeo-index-files": "archeo",
    # Vault management
    "mem-list": "vault",
    "mem-search": "vault",
    "mem-rename": "vault",
    "mem-merge": "vault",
    "mem-reclass": "vault",
    "mem-promote-domain": "vault",
    "mem-init-project": "vault",
    "mem-update-phase": "vault",
    "mem-digest": "vault",
    "mem-rollback-archive": "vault",
    "mem-read-archive": "vault",
    "mem-read-context": "vault",
    "mem-read-history": "vault",
    "mem-get-topology": "vault",
    "mem-migrate": "vault",
    # Hygiene
    "mem-health-scan": "hygiene",
    "mem-health-repair": "hygiene",
    "mem-check-update": "hygiene",
    "mem-help": "misc",
}


# ---------------------------------------------------------------------------
# Procedure parsing — extract description + sections
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"^#\s+(.+?)$", re.MULTILINE)
_GOAL_RE = re.compile(r"^Goal:\s*(.+?)(?=\n\n|\n##\s)", re.DOTALL | re.MULTILINE)


def _extract_description(text: str) -> str:
    """First sentence of the Goal: paragraph (or first paragraph after title)."""
    m = _GOAL_RE.search(text)
    if m:
        para = m.group(1).strip()
    else:
        # Fallback : first non-title paragraph
        lines = text.splitlines()
        # Skip title lines + blank
        body_start = 0
        for i, ln in enumerate(lines):
            if ln.startswith("# ") or not ln.strip():
                body_start = i + 1
            else:
                break
        para = " ".join(
            ln for ln in lines[body_start:body_start + 5] if ln.strip()
        )
    # Take first sentence (period-bounded) for compactness in general help.
    para = re.sub(r"\s+", " ", para).strip()
    sentences = re.split(r"(?<=[.!?])\s+", para)
    if sentences:
        return sentences[0].strip()
    return para[:200]


def _extract_section(text: str, section_title: str) -> str:
    """Extract the body of a ``## {section_title}`` section.

    Stops at the next ``## `` header or EOF. Returns empty string when
    the section is absent.
    """
    pattern = rf"^##\s+{re.escape(section_title)}\s*$\n+(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    return m.group(1).rstrip()


def _resolve_kit_repo() -> Path | None:
    """Resolve kit_repo path from config.json. None when not configured."""
    config = get_config()
    kit_repo = getattr(config, "kit_repo", None)
    if kit_repo:
        path = Path(str(kit_repo)).expanduser()
        if path.is_dir():
            return path
    return None


def _load_strings() -> dict[str, Any]:
    """Load core/i18n/strings.yaml from the kit repo. Empty dict on failure."""
    if yaml is None:
        return {}
    kit_repo = _resolve_kit_repo()
    if kit_repo is None:
        return {}
    strings_path = kit_repo / "core" / "i18n" / "strings.yaml"
    if not strings_path.is_file():
        return {}
    try:
        return yaml.safe_load(strings_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _resolve_language(explicit: str | None) -> str:
    """Resolve language with priority : explicit > config > 'en'."""
    if explicit:
        lang = explicit.lower().strip()
        if lang in {"en", "fr", "es", "de", "ru"}:
            return lang
    config = get_config()
    cfg_lang = getattr(config, "language", None)
    if cfg_lang and cfg_lang.lower() in {"en", "fr", "es", "de", "ru"}:
        return cfg_lang.lower()
    return "en"


def _help_strings(strings: dict[str, Any], lang: str) -> dict[str, Any]:
    """Return the ``help`` block for ``lang``, falling back to ``en``."""
    block = strings.get(lang, {}).get("help") or strings.get("en", {}).get(
        "help"
    ) or {}
    return block


# ---------------------------------------------------------------------------
# General help — categorized inventory
# ---------------------------------------------------------------------------


def _list_procedures(kit_repo: Path) -> list[Path]:
    """List all ``mem-*.md`` procedures in the kit repo."""
    proc_dir = kit_repo / "core" / "procedures"
    if not proc_dir.is_dir():
        return []
    return sorted(proc_dir.glob("mem-*.md"))


def _build_update_banner(help_strings: dict[str, Any]) -> str:
    """Compose the localized update banner. Empty string when no update."""
    template = help_strings.get("update_banner")
    if not template:
        return ""
    try:
        info = check_for_update()
    except Exception:  # noqa: BLE001
        return ""
    if not info.update_available or not info.latest_version:
        return ""
    return template.format(
        latest=info.latest_version,
        current=info.current_version,
    )


def _build_general_help(lang: str, strings: dict[str, Any]) -> HelpResult:
    h = _help_strings(strings, lang)
    kit_repo = _resolve_kit_repo()
    entries: list[_CommandEntry] = []
    if kit_repo is not None:
        for proc_path in _list_procedures(kit_repo):
            command = proc_path.stem
            text = proc_path.read_text(encoding="utf-8", errors="replace")
            description = _extract_description(text)
            category = _CATEGORY_OF.get(command, "misc")
            entries.append(
                _CommandEntry(
                    command=command,
                    description=description,
                    category=category,
                )
            )

    title = h.get("title_general", "SecondBrain — Help")
    intro = h.get(
        "intro_general",
        "Available `mem-*` commands grouped by category.",
    )
    cat_labels = {
        "session": h.get("category_session", "Session cycle"),
        "capture": h.get("category_capture", "Capture & ingestion"),
        "archeo": h.get("category_archeo", "Repo archeology"),
        "vault": h.get("category_vault", "Vault management"),
        "hygiene": h.get("category_hygiene", "Hygiene"),
        "misc": h.get("category_misc", "Miscellaneous"),
    }
    cat_order = {
        "session": 0, "capture": 1, "archeo": 2,
        "vault": 3, "hygiene": 4, "misc": 5,
    }
    sorted_entries = sorted(
        entries,
        key=lambda e: (cat_order.get(e.category, 99), e.command),
    )

    # Single Markdown table — denser + scannable than the previous
    # grouped-bullets layout. Category column lets the user scan visually
    # without the section header overhead.
    cmd_label = h.get("table_command_header", "Command")
    cat_label_header = h.get("table_category_header", "Category")
    desc_label = h.get("description_label", "Description")

    lines: list[str] = [f"# {title}", ""]

    # Update-available banner — prepended above the intro so a user
    # consulting `/mem-help` gets the notification even if the MCP server
    # has been running for hours (cache may have refreshed since the
    # initialize handshake banner was sent).
    banner = _build_update_banner(h)
    if banner:
        lines += [f"> {banner}", ""]

    lines += [intro, ""]
    lines.append(f"| {cmd_label} | {cat_label_header} | {desc_label} |")
    lines.append("|---|---|---|")
    for e in sorted_entries:
        desc = e.description if e.description else "_(no description)_"
        # Escape pipes in description to keep the table valid.
        desc_safe = desc.replace("|", "\\|").replace("\n", " ").strip()
        cat_label = cat_labels.get(e.category, e.category)
        lines.append(f"| `/{e.command}` | {cat_label} | {desc_safe} |")
    summary_md = "\n".join(lines).rstrip() + "\n"

    return HelpResult(
        command=None,
        language=lang,
        title=title,
        commands=entries,
        summary_md=summary_md,
    )


# ---------------------------------------------------------------------------
# Command-specific help
# ---------------------------------------------------------------------------


def _build_command_help(
    command: str, lang: str, strings: dict[str, Any]
) -> HelpResult:
    h = _help_strings(strings, lang)
    kit_repo = _resolve_kit_repo()
    if kit_repo is None:
        return HelpResult(
            command=command,
            language=lang,
            title=command,
            description=(
                "kit_repo not configured in ~/.memory-kit/config.json — "
                "cannot resolve procedure source."
            ),
            summary_md=f"_kit_repo unavailable for `{command}`._\n",
        )
    proc_path = kit_repo / "core" / "procedures" / f"{command}.md"
    if not proc_path.is_file():
        msg = h.get(
            "unknown_command", "Unknown command : `{command}`."
        ).format(command=command)
        return HelpResult(
            command=command,
            language=lang,
            title=command,
            description=msg,
            summary_md=f"_{msg}_\n",
        )
    text = proc_path.read_text(encoding="utf-8", errors="replace")

    description = _extract_description(text)
    triggers = _extract_section(text, "Trigger")
    # Arguments often live inside the Trigger section as bullet lists, but
    # some procedures break them out. Try both.
    arguments = _extract_section(text, "Arguments")
    examples = _extract_section(text, "Examples") or _extract_section(
        text, "Example"
    )
    see_also = _extract_see_also(command)

    title_tpl = h.get("title_command", "SecondBrain — `{command}` Help")
    title = title_tpl.format(command=command)
    desc_label = h.get("description_label", "Description")
    trig_label = h.get("triggers_label", "Triggers")
    args_label = h.get("arguments_label", "Arguments")
    ex_label = h.get("examples_label", "Examples")
    sa_label = h.get("see_also_label", "See also")
    no_section = h.get("no_section", "_(no `{section}` section)_")
    footer_tpl = h.get(
        "footer",
        "Procedures source of truth : `core/procedures/{command}.md`.",
    )

    lines: list[str] = [f"# {title}", ""]
    if description:
        lines += [f"## {desc_label}", "", description, ""]
    if triggers:
        lines += [f"## {trig_label}", "", triggers.strip(), ""]
    else:
        lines += [
            f"## {trig_label}",
            "",
            no_section.format(section="Trigger"),
            "",
        ]
    if arguments:
        lines += [f"## {args_label}", "", arguments.strip(), ""]
    if examples:
        lines += [f"## {ex_label}", "", examples.strip(), ""]
    if see_also:
        lines += [
            f"## {sa_label}",
            "",
            ", ".join(f"`/{c}`" for c in see_also),
            "",
        ]
    lines += ["---", "", footer_tpl.format(
        command=command.removeprefix("mem-").replace("-", "_") or command
    )]
    summary_md = "\n".join(lines).rstrip() + "\n"

    return HelpResult(
        command=command,
        language=lang,
        title=title,
        description=description,
        triggers=triggers,
        arguments=arguments,
        examples=examples,
        see_also=see_also,
        summary_md=summary_md,
    )


def _extract_see_also(command: str) -> list[str]:
    """Hardcoded see-also map for navigation. Cheap and explicit."""
    related = {
        "mem-archeo": ["mem-archeo-plan", "mem-archeo-git", "mem-archeo-stack", "mem-archeo-context"],
        "mem-archeo-plan": ["mem-archeo", "mem-archeo-git"],
        "mem-archeo-git": ["mem-archeo", "mem-archeo-plan"],
        "mem-archeo-stack": ["mem-archeo", "mem-archeo-plan"],
        "mem-archeo-context": ["mem-archeo", "mem-archeo-plan"],
        "mem-recall": ["mem-archive", "mem-list"],
        "mem-archive": ["mem-recall", "mem-rollback-archive"],
        "mem-rollback-archive": ["mem-archive"],
        "mem-list": ["mem-search", "mem-recall"],
        "mem-search": ["mem-list"],
        "mem-rename": ["mem-merge", "mem-reclass"],
        "mem-merge": ["mem-rename", "mem-reclass"],
        "mem-reclass": ["mem-rename", "mem-merge"],
        "mem-doc": ["mem"],
        "mem": ["mem-doc", "mem-note", "mem-principle", "mem-goal", "mem-person"],
        "mem-health-scan": ["mem-health-repair"],
        "mem-health-repair": ["mem-health-scan"],
        "mem-check-update": [],
        "mem-help": [],
    }
    return related.get(command, [])


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_help(
        command: str | None = Field(
            None,
            description=(
                "Specific command (e.g. 'mem-archeo'). When omitted, returns "
                "the categorized inventory of all mem-* commands."
            ),
        ),
        lang: str | None = Field(
            None,
            description=(
                "Language code (en/fr/es/de/ru). When omitted, falls back to "
                "the value of 'language' in ~/.memory-kit/config.json (then "
                "'en' as ultimate default)."
            ),
        ),
    ) -> HelpResult:
        """Display localized help for SecondBrain mem-* commands.

        Two modes :

        - **General help** : ``mem_help()`` returns the inventory of all
          ``mem-*`` commands grouped by category (session / capture /
          archeo / vault / hygiene), each with a one-line description.
        - **Command help** : ``mem_help(command="mem-archeo")`` returns
          the description + triggers + arguments + examples + see-also
          for that command, extracted from
          ``core/procedures/{command}.md``.

        Wrapper labels (titles, section names, category labels) are
        localized via ``core/i18n/strings.yaml`` in 5 languages
        (en/fr/es/de/ru). Procedure body content stays in canonical
        English — the procedures are read by LLMs that perform best on
        EN, so only the surrounding chrome translates.
        """
        resolved_lang = _resolve_language(lang)
        strings = _load_strings()
        if command is None or not str(command).strip():
            return _build_general_help(resolved_lang, strings)
        cmd = str(command).strip()
        if not cmd.startswith("mem-"):
            cmd = f"mem-{cmd.lstrip('/').strip()}"
        return _build_command_help(cmd, resolved_lang, strings)
