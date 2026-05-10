"""Tests for mem_help — localized help for mem-* commands.

Spec: core/procedures/mem-help.md.

Verifies general inventory, command-specific extraction, language fallback,
unknown command error, i18n wrapper labels for all 5 languages, and the
update-available banner.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client

from memory_kit_mcp.config import get_config
from memory_kit_mcp.update_check import UpdateInfo


def _seed_kit_repo_stub(
    tmp_path: Path, *, language: str = "en"
) -> Path:
    """Create a minimal kit_repo with a few procedures + i18n strings.

    Returns the kit_repo path. Updates ~/.memory-kit/config.json so
    `get_config().kit_repo` points at this stub.
    """
    kit_repo = tmp_path / "kit-stub"
    proc_dir = kit_repo / "core" / "procedures"
    proc_dir.mkdir(parents=True)
    (proc_dir / "mem-archeo.md").write_text(
        "# Procedure: Archeo (v0.7.0)\n\n"
        "Goal: orchestrate the three phases of archeo on a Git repository. "
        "Produces atoms across organizational, technical and temporal "
        "dimensions.\n\n"
        "## Trigger\n\n"
        "The user types `/mem-archeo [repo]` or says 'do an archeo of this'.\n\n"
        "Arguments:\n"
        "- `{repo}` (optional): path to local Git repo\n"
        "- `--depth {N}`: topology scan depth (default 2)\n",
        encoding="utf-8",
    )
    (proc_dir / "mem-recall.md").write_text(
        "# Procedure: Recall (v0.5)\n\n"
        "Goal: retrieve the work context from the vault after a /clear.\n\n"
        "## Trigger\n\n"
        "User says 'on continue' or types `/mem-recall [project]`.\n",
        encoding="utf-8",
    )
    # i18n strings stub — minimal help block per language
    i18n_dir = kit_repo / "core" / "i18n"
    i18n_dir.mkdir(parents=True)
    yaml_text = ""
    for lang_code, label_dict in [
        ("en", {
            "title_general": "SecondBrain — Help",
            "title_command": "SecondBrain — `{command}` Help",
            "intro_general": "Available commands.",
            "description_label": "Description",
            "triggers_label": "Triggers",
            "arguments_label": "Arguments",
            "examples_label": "Examples",
            "see_also_label": "See also",
            "no_section": "_(no `{section}` section)_",
            "unknown_command": "Unknown command : `{command}`.",
            "available_commands_label": "Available commands",
            "category_session": "Session cycle",
            "category_capture": "Capture & ingestion",
            "category_archeo": "Repo archeology",
            "category_vault": "Vault management",
            "category_hygiene": "Hygiene",
            "category_misc": "Miscellaneous",
            "table_command_header": "Command",
            "table_category_header": "Category",
            "footer": "Source : `core/procedures/{command}.md`.",
        }),
        ("fr", {
            "title_general": "SecondBrain — Aide",
            "title_command": "SecondBrain — Aide `{command}`",
            "intro_general": "Commandes disponibles.",
            "description_label": "Description",
            "triggers_label": "Déclenchement",
            "arguments_label": "Arguments",
            "examples_label": "Exemples",
            "see_also_label": "Voir aussi",
            "no_section": "_(pas de section `{section}`)_",
            "unknown_command": "Commande inconnue : `{command}`.",
            "available_commands_label": "Commandes disponibles",
            "category_session": "Cycle de session",
            "category_capture": "Capture & ingestion",
            "category_archeo": "Archeo de dépôt",
            "category_vault": "Gestion du vault",
            "category_hygiene": "Hygiène",
            "category_misc": "Divers",
            "table_command_header": "Commande",
            "table_category_header": "Catégorie",
            "footer": "Source : `core/procedures/{command}.md`.",
        }),
        ("es", {"title_general": "Ayuda", "intro_general": "Comandos.",
                "description_label": "Descripción", "triggers_label": "Activadores",
                "arguments_label": "Argumentos", "title_command": "Ayuda `{command}`",
                "see_also_label": "Ver también",
                "category_archeo": "Arqueología", "category_session": "Sesión",
                "category_capture": "Captura", "category_vault": "Bóveda",
                "category_hygiene": "Higiene", "category_misc": "Otros",
                "no_section": "_(sin `{section}`)_",
                "unknown_command": "Comando desconocido : `{command}`."}),
        ("de", {"title_general": "Hilfe", "intro_general": "Befehle.",
                "description_label": "Beschreibung", "triggers_label": "Auslöser",
                "arguments_label": "Argumente", "title_command": "Hilfe `{command}`",
                "see_also_label": "Siehe auch",
                "category_archeo": "Archäologie", "category_session": "Sitzung",
                "category_capture": "Erfassung", "category_vault": "Vault",
                "category_hygiene": "Hygiene", "category_misc": "Sonstiges",
                "no_section": "_(kein `{section}`)_",
                "unknown_command": "Unbekannter Befehl : `{command}`."}),
        ("ru", {"title_general": "Справка", "intro_general": "Команды.",
                "description_label": "Описание", "triggers_label": "Активаторы",
                "arguments_label": "Аргументы", "title_command": "Справка `{command}`",
                "see_also_label": "См. также",
                "category_archeo": "Археология", "category_session": "Сессия",
                "category_capture": "Захват", "category_vault": "Хранилище",
                "category_hygiene": "Гигиена", "category_misc": "Прочее",
                "no_section": "_(нет `{section}`)_",
                "update_banner": "⚠️ Обновление : v{latest} (установлена v{current}).",
                "unknown_command": "Неизвестная команда : `{command}`."}),
    ]:
        # Always inject FR/EN update_banner so update tests work regardless
        # of which language the test seeds.
        if "update_banner" not in label_dict:
            label_dict["update_banner"] = (
                "⚠️ Update : v{latest} (installed v{current})."
                if lang_code == "en"
                else "⚠️ Mise à jour : v{latest} (installée v{current})."
                if lang_code == "fr"
                else "⚠️ v{latest}"
            )
        yaml_text += f"{lang_code}:\n  help:\n"
        for k, v in label_dict.items():
            yaml_text += f'    {k}: "{v}"\n'
    (i18n_dir / "strings.yaml").write_text(yaml_text, encoding="utf-8")

    # Patch config to point at this stub
    config_path = Path(get_config().__class__.__module__)  # placeholder
    # Direct write to MEMORY_KIT_HOME's config.json via the conftest-set env
    import os
    home = Path(os.environ["MEMORY_KIT_HOME"])
    config_file = home / "config.json"
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    cfg["kit_repo"] = str(kit_repo)
    cfg["language"] = language
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    get_config.cache_clear()
    return kit_repo


# ---------------------------------------------------------------------------
# General help
# ---------------------------------------------------------------------------


async def test_general_help_lists_all_procedures(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool("mem_help", {})
    data = res.data
    assert data.command is None
    assert data.language == "en"
    commands = {c.command for c in data.commands}
    assert "mem-archeo" in commands
    assert "mem-recall" in commands
    # Categorization
    archeo = next(c for c in data.commands if c.command == "mem-archeo")
    assert archeo.category == "archeo"
    recall = next(c for c in data.commands if c.command == "mem-recall")
    assert recall.category == "session"
    # Description extracted from Goal: paragraph
    assert "orchestrate" in archeo.description.lower()


async def test_general_help_localized_fr(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path, language="fr")
    res = await client.call_tool("mem_help", {})
    md = res.data.summary_md
    assert "SecondBrain — Aide" in md
    assert "Cycle de session" in md
    assert "Archeo de dépôt" in md


async def test_general_help_renders_single_markdown_table(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool("mem_help", {})
    md = res.data.summary_md
    # Single table with header row + separator
    assert "| `/mem-archeo` |" in md
    assert "| `/mem-recall` |" in md
    assert "|---|---|---|" in md
    # Category surfaced as cell, not as section header
    assert "Session cycle" in md
    assert "Repo archeology" in md
    # No grouped section headers anymore
    assert "## Session cycle" not in md
    assert "## Repo archeology" not in md


# ---------------------------------------------------------------------------
# Command-specific help
# ---------------------------------------------------------------------------


async def test_command_help_extracts_sections(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool(
        "mem_help", {"command": "mem-archeo"}
    )
    data = res.data
    assert data.command == "mem-archeo"
    assert "orchestrate" in data.description.lower()
    assert "Trigger" not in data.triggers  # body only, no header
    assert "/mem-archeo" in data.triggers
    assert "--depth" in data.triggers  # arguments inline
    # see-also surfaced
    assert "mem-archeo-plan" in data.see_also


async def test_command_help_lang_param_overrides_config(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path, language="en")
    res = await client.call_tool(
        "mem_help", {"command": "mem-archeo", "lang": "fr"}
    )
    assert res.data.language == "fr"
    assert "Déclenchement" in res.data.summary_md


async def test_command_help_unknown_command_returns_error_message(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool(
        "mem_help", {"command": "mem-nonexistent"}
    )
    assert "Unknown command" in res.data.description


async def test_command_help_normalizes_input_without_prefix(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """Calling with 'archeo' (no mem- prefix) resolves to mem-archeo."""
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool(
        "mem_help", {"command": "archeo"}
    )
    assert res.data.command == "mem-archeo"
    assert "orchestrate" in res.data.description.lower()


async def test_lang_fallback_when_config_unset(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """No lang param + invalid config language → fallback to en."""
    _seed_kit_repo_stub(tmp_path, language="invalid-locale")
    res = await client.call_tool("mem_help", {})
    assert res.data.language == "en"


# ---------------------------------------------------------------------------
# Multi-language coverage
# ---------------------------------------------------------------------------


async def test_general_help_prepends_update_banner_when_available(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path, language="fr")
    fake = UpdateInfo(
        current_version="0.10.0",
        latest_version="0.11.0",
        update_available=True,
        last_checked=0.0,
        error=None,
    )
    with patch(
        "memory_kit_mcp.tools.help.check_for_update",
        return_value=fake,
    ):
        res = await client.call_tool("mem_help", {})
    md = res.data.summary_md
    # Banner present, before the table
    assert "Mise à jour" in md
    assert "v0.11.0" in md
    table_idx = md.find("|---|---|---|")
    banner_idx = md.find("Mise à jour")
    assert 0 < banner_idx < table_idx, (
        "banner must appear above the commands table"
    )


async def test_general_help_no_banner_when_no_update(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    _seed_kit_repo_stub(tmp_path)
    fake = UpdateInfo(
        current_version="0.11.0",
        latest_version="0.11.0",
        update_available=False,
        last_checked=0.0,
        error=None,
    )
    with patch(
        "memory_kit_mcp.tools.help.check_for_update",
        return_value=fake,
    ):
        res = await client.call_tool("mem_help", {})
    assert "Update" not in res.data.summary_md
    assert "Mise à jour" not in res.data.summary_md


async def test_server_instructions_carries_update_banner_when_available(
    tmp_path: Path,
) -> None:
    """MCP serverInfo.instructions surfaces the update banner at handshake."""
    import memory_kit_mcp.server as srv

    fake = UpdateInfo(
        current_version="0.10.0",
        latest_version="0.11.0",
        update_available=True,
        last_checked=0.0,
        error=None,
    )
    with patch.object(srv, "check_for_update", return_value=fake):
        instructions = srv._build_instructions()
    assert "update available" in instructions.lower() or "v0.11.0" in instructions
    assert "Memory Kit MCP" in instructions


async def test_server_instructions_no_banner_when_no_update() -> None:
    import memory_kit_mcp.server as srv

    fake = UpdateInfo(
        current_version="0.11.0",
        latest_version="0.11.0",
        update_available=False,
        last_checked=0.0,
        error=None,
    )
    with patch.object(srv, "check_for_update", return_value=fake):
        instructions = srv._build_instructions()
    assert "update available" not in instructions.lower()
    assert "Memory Kit MCP" in instructions


@pytest.mark.parametrize(
    "lang,expected_label",
    [
        ("en", "Description"),
        ("fr", "Description"),
        ("es", "Descripción"),
        ("de", "Beschreibung"),
        ("ru", "Описание"),
    ],
)
async def test_command_help_all_5_languages_render_correct_labels(
    client: Client, vault_tmp: Path, tmp_path: Path,
    lang: str, expected_label: str,
) -> None:
    _seed_kit_repo_stub(tmp_path)
    res = await client.call_tool(
        "mem_help", {"command": "mem-archeo", "lang": lang}
    )
    assert res.data.language == lang
    assert expected_label in res.data.summary_md
