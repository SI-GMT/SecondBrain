#!/usr/bin/env bash
#
# deploy.sh — Deploie le kit memoire dans chaque CLI IA detectee sur le poste.
#
# Detecte les CLI IA installees (Claude Code, Gemini CLI, Codex, Mistral Vibe)
# et deploie l'adapter correspondant pour chacune. Ne plante pas si une CLI
# est absente : elle est simplement skippee. Si aucune CLI n'est trouvee,
# un message amical explique quoi installer.
#
# Premiere installation : le vault est cree a {racine du kit}/memory sauf si
# --vault-path est fourni.
#
# Mise a jour : si une installation precedente est detectee (via les
# memory-kit.json presents dans les dossiers de config des CLI), son vault
# est reutilise automatiquement. Le script peut donc etre relance depuis
# n'importe quel repertoire de travail sans avoir a repreciser le chemin.
#
# Utiliser --vault-path pour forcer un autre vault (migration).
#
# Usage :
#   ./deploy.sh
#   ./deploy.sh --vault-path /chemin/vers/vault
#   ./deploy.sh --force

set -euo pipefail

# Force UTF-8 pour les heredocs Python : sans ca, Windows + Python 3.x
# par defaut en cp1252 plante sur les caracteres comme '→' (UnicodeEncodeError).
# No-op sur Linux/macOS deja en UTF-8.
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# ============================================================
# Parsing des arguments
# ============================================================

VAULT_PATH=""
LANGUAGE=""
FORCE=false
SKIP_OBSIDIAN_STYLE=false
FORCE_OBSIDIAN_STYLE=false
SKIP_MCP_SERVER=false
REPAIR_MCP=false
AUTO_UPDATE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vault-path)
            VAULT_PATH="$2"
            shift 2
            ;;
        --language)
            LANGUAGE="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --skip-obsidian-style)
            SKIP_OBSIDIAN_STYLE=true
            shift
            ;;
        --force-obsidian-style)
            FORCE_OBSIDIAN_STYLE=true
            shift
            ;;
        --skip-mcp-server)
            SKIP_MCP_SERVER=true
            shift
            ;;
        --repair-mcp)
            REPAIR_MCP=true
            shift
            ;;
        --auto-update)
            AUTO_UPDATE=true
            shift
            ;;
        -h|--help|-\?|--\?)
            echo "Usage : $0 [--vault-path <chemin>] [--language en|fr|es|de|ru] [--force] [--skip-obsidian-style] [--force-obsidian-style] [--skip-mcp-server] [--repair-mcp] [--auto-update] [-h|--help|-?|--?]"
            echo ""
            echo "  --vault-path             Chemin absolu du vault memoire (defaut : auto-detection puis <racine du kit>/memory)"
            echo "  --language               Langue conversationnelle du LLM (defaut : detection systeme puis prompt)"
            echo "  --force                  Ecrase memory-kit.json meme s'il existe deja"
            echo "  --skip-obsidian-style    Ne deploie pas les configs canoniques Obsidian (graph palette)"
            echo "  --force-obsidian-style   Force le deploy Obsidian style meme si Obsidian semble ouvert"
            echo "  --skip-mcp-server        Ne deploie pas le serveur MCP Python (CLI restent en mode skills fallback)"
            echo "  --repair-mcp             Desinstalle pipx puis reinstall propre du serveur MCP (utile si install corrompue)"
            echo "  --auto-update            git pull --ff-only avant de deployer (refuse si pas un repo git, branche != main, ou working tree dirty)"
            echo "  -h, --help, -?, --?      Affiche cette aide et quitte"
            exit 0
            ;;
        *)
            echo "Argument inconnu : $1" >&2
            exit 1
            ;;
    esac
done


# ============================================================
# Helpers d'affichage
# ============================================================

_cyan()     { printf '\033[0;36m%s\033[0m\n' "$1"; }
_green()    { printf '\033[0;32m  [OK] %s\033[0m\n' "$1"; }
_yellow()   { printf '\033[0;33m  [!]  %s\033[0m\n' "$1"; }
_gray()     { printf '\033[0;90m  [--] %s\033[0m\n' "$1"; }
_info()     { printf '\033[0;96m  [i]  %s\033[0m\n' "$1"; }

# ============================================================
# Resolution Python 3 cross-platform
# ============================================================
# Sur Git Bash Windows, 'python3' peut rediriger vers le stub Microsoft Store
# qui ne fait qu'afficher un message d'install. Sur macOS/Linux, 'python3' est
# nominal. On detecte le cas et on shadow par une fonction shell qui delegue a
# 'python' ou 'py -3' si disponibles. Aucun effet sur les OS ou python3 marche.

if ! python3 -c 'import sys' >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
        python3() { command python "$@"; }
        export -f python3
    elif command -v py >/dev/null 2>&1 && py -3 -c 'import sys' >/dev/null 2>&1; then
        python3() { command py -3 "$@"; }
        export -f python3
    fi
fi

# ============================================================
# Assemblage d'une procedure core (resolution {{INCLUDE _bloc}} + {{CONFIG_FILE}}
# + prepend MCP-first v0.8.0)
# ============================================================
# Une procedure peut inclure des blocs reutilisables (encoding, concurrence,
# router, frontmatter-universel...) via {{INCLUDE _nom}}. Resolution recursive
# avec profondeur max 5 pour eviter les cycles.
#
# Si skill_name est fourni (4e arg), le bloc core/procedures/_mcp-first.md est
# prepend en tete avec {{TOOL_NAME}} substitue par la variante snake_case du
# skill (mem-recall -> mem_recall). Indique au LLM d'invoquer l'outil MCP
# correspondant si disponible, sinon d'executer la procedure ci-dessous.
#
# Args  : <procedure_path> <core_root> <config_file_ref> [skill_name]
# Stdout: contenu assemble (procedure + blocs inclus + CONFIG_FILE substitue
#         + prepend MCP-first si skill_name fourni)
# Exit  : 1 si bloc introuvable ou cycle detecte.

assemble_procedure() {
    local proc_path="$1"
    local core_root="$2"
    local config_file_ref="$3"
    local skill_name="${4:-}"
    python3 - "$proc_path" "$core_root" "$config_file_ref" "$skill_name" << 'PYEOF'
import re, sys
from pathlib import Path

proc_path = Path(sys.argv[1])
core_root = Path(sys.argv[2])
config_file_ref = sys.argv[3]
skill_name = sys.argv[4] if len(sys.argv) > 4 else ""

# Include names can contain hyphens (_repo-topology, _repo-paths,
# _frontmatter-archeo, …) — match [\w-], not just \w, else the directive is
# left unresolved (literal {{INCLUDE …}} leaks into the deployed skill).
INCLUDE_RE = re.compile(r'\{\{INCLUDE\s+(_[\w-]+)\}\}')

def resolve(content, depth=0, ancestors=()):
    if depth > 10:
        sys.stderr.write("Profondeur maximale d'inclusion depassee (10). Cycle suspecte.\n")
        sys.exit(1)
    def repl(match):
        name = match.group(1)
        # Cycle guard: if the block is already being expanded up the chain,
        # leave the directive LITERAL. Some doctrine blocks (_repo-topology,
        # _archived, _when-to-script) cite their own name as a syntax example.
        if name in ancestors:
            return match.group(0)
        path = core_root / f"{name}.md"
        if not path.exists():
            sys.stderr.write(f"Bloc d'inclusion introuvable : {{{{INCLUDE {name}}}}} -> {path}\n")
            sys.exit(1)
        return resolve(path.read_text(encoding='utf-8'), depth + 1, ancestors + (name,))
    return INCLUDE_RE.sub(repl, content)

content = proc_path.read_text(encoding='utf-8')
content = resolve(content)
content = content.replace('{{CONFIG_FILE}}', config_file_ref)

# v0.8.0 : prepend du bloc _mcp-first.md si skill_name fourni et bloc present
if skill_name:
    mcp_block_path = core_root / "_mcp-first.md"
    if mcp_block_path.exists():
        block = resolve(mcp_block_path.read_text(encoding='utf-8'))
        # Convention kebab->snake : mem-recall <-> mem_recall (cf. doc archi v0.8.0 §5).
        tool_name = skill_name.replace('-', '_')
        block = block.replace('{{TOOL_NAME}}', tool_name)
        content = block + content

sys.stdout.write(content)
PYEOF
}

# ============================================================
# Ecriture / mise a jour de memory-kit.json
# ============================================================
# Le fichier porte le chemin du vault et la valeur par defaut du scope (perso|pro).
# Comportement :
#   - Fichier absent ou --force => creation avec vault + default_scope (defaut: pro)
#   - Fichier present sans --force => preservation, mais patch silencieux si
#     default_scope est absent (cas migration v0.4 -> v0.5).
#
# Args : <path> <vault> [default_scope=pro]
# Affiche le statut via les helpers de log.

write_memory_kit_json() {
    local path="$1"
    local vault="$2"
    local kit_repo="$3"
    local default_scope="${4:-work}"
    local language="${5:-en}"
    local force_flag="$FORCE"

    if ! command -v python3 &>/dev/null; then
        # Fallback sans python : ecriture brute (perd le patch silencieux mais reste fonctionnel).
        if [[ -f "$path" && "$force_flag" == "false" ]]; then
            _gray "memory-kit.json preserve (utiliser --force pour ecraser ; python3 absent, patch silencieux indisponible)"
            return 0
        fi
        printf '{\n  "vault": "%s",\n  "default_scope": "%s",\n  "language": "%s",\n  "kit_repo": "%s"\n}' "$vault" "$default_scope" "$language" "$kit_repo" > "$path"
        _green "memory-kit.json -> vault = $vault, default_scope = $default_scope, language = $language, kit_repo = $kit_repo"
        return 0
    fi

    local result
    local _tmpout
    _tmpout="$(mktemp)"
    python3 - "$path" "$vault" "$default_scope" "$language" "$kit_repo" "$force_flag" > "$_tmpout" << 'PYEOF'
import json, sys
from pathlib import Path

path, vault, default_scope, language, kit_repo, force_str = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
force = force_str == "true"
p = Path(path)

if p.exists() and not force:
    try:
        existing = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"ERR|{e}")
        sys.exit(0)
    patched_fields = []
    if 'default_scope' not in existing:
        existing['default_scope'] = default_scope
        patched_fields.append(f"default_scope={default_scope}")
    if 'language' not in existing:
        existing['language'] = language
        patched_fields.append(f"language={language}")
    if 'kit_repo' not in existing:
        existing['kit_repo'] = kit_repo
        patched_fields.append(f"kit_repo={kit_repo}")
    if patched_fields:
        merged = {
            'vault': existing.get('vault', vault),
            'default_scope': existing['default_scope'],
            'language': existing['language'],
            'kit_repo': existing['kit_repo'],
        }
        p.write_text(json.dumps(merged, indent=2), encoding='utf-8')
        print("PATCHED|" + ",".join(patched_fields))
    else:
        print("SKIP")
    sys.exit(0)

# Creation ou ecrasement complet (ordre des cles preserve)
data = {'vault': vault, 'default_scope': default_scope, 'language': language, 'kit_repo': kit_repo}
p.write_text(json.dumps(data, indent=2), encoding='utf-8')
print(f"WRITTEN|{vault}|{default_scope}|{language}|{kit_repo}")
PYEOF
    result="$(cat "$_tmpout")"
    rm -f "$_tmpout"

    case "$result" in
        WRITTEN\|*)
            _green "memory-kit.json -> vault = $vault, default_scope = $default_scope, language = $language, kit_repo = $kit_repo"
            ;;
        PATCHED\|*)
            _green "memory-kit.json patche : ${result#PATCHED|}"
            ;;
        SKIP)
            _gray "memory-kit.json preserve (utiliser --force pour ecraser)"
            ;;
        ERR\|*)
            _yellow "memory-kit.json existant illisible (${result#ERR|})"
            ;;
    esac
}

# ============================================================
# Resolution de la langue conversationnelle
# ============================================================
# Priorite : --language > $LANG/$LC_ALL > prompt interactif > "en"
resolve_language() {
    local explicit="$1"
    local supported=("en" "fr" "es" "de" "ru")
    if [[ -n "$explicit" ]]; then
        echo "$explicit"
        return 0
    fi
    # Detection systeme
    local raw="${LC_ALL:-${LANG:-en}}"
    local code="${raw:0:2}"
    code="$(printf '%s' "$code" | tr '[:upper:]' '[:lower:]')"
    local detected="en"
    for s in "${supported[@]}"; do
        [[ "$s" == "$code" ]] && detected="$s" && break
    done
    # Prompt si controlling terminal accessible. On utilise /dev/tty plutot
    # que [[ -t 0 && -t 1 ]] : la fonction est appelee dans un command
    # substitution ($(resolve_language ...)) qui redirige stdout vers le pipe
    # de capture, donc [[ -t 1 ]] est false alors que l'utilisateur est bien
    # sur un terminal interactif. /dev/tty pointe toujours sur le terminal
    # controlant, independamment des redirections de fd.
    if [[ -r /dev/tty && -w /dev/tty ]]; then
        {
            echo ""
            printf '\033[0;36m%s\033[0m\n' "Conversational language for the LLM (the vault structure stays English)"
            printf '\033[0;90m  Supported: %s\033[0m\n' "${supported[*]}"
            printf '  Choose language [%s]: ' "$detected"
        } >/dev/tty
        local input=""
        read -r input </dev/tty || true
        if [[ -n "$input" ]]; then
            input="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
            for s in "${supported[@]}"; do
                if [[ "$s" == "$input" ]]; then
                    echo "$input"
                    return 0
                fi
            done
            printf '\033[1;33mUnknown language '\''%s'\'', falling back to '\''%s'\''\033[0m\n' "$input" "$detected" >/dev/tty
        fi
    fi
    echo "$detected"
}

# ============================================================
# Detection des CLI IA
# ============================================================

cli_installed() {
    local binary="$1"
    local config_dir="$2"
    # CLI consideree installee si le binaire est sur le PATH OU si le dossier
    # de config existe (= elle a deja tourne sur ce poste).
    command -v "$binary" &>/dev/null && return 0
    [[ -n "$config_dir" && -d "$config_dir" ]] && return 0
    return 1
}

# ============================================================
# Detection d'une installation SecondBrain existante
# ============================================================

# Parcourt les emplacements ou un memory-kit.json a pu etre ecrit par une
# installation precedente. Ecrit dans EXISTING_VAULTS un tableau de lignes
# "Source|ConfigFile|Vault" pour chaque fichier trouve et parsable.
#
# Mistral Vibe n'a pas de memory-kit.json (son vault est injecte en clair
# dans AGENTS.md), il n'est pas scanne ici.

declare -a EXISTING_VAULTS=()

get_existing_vault_paths() {
    local claude_config="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    local copilot_config="${COPILOT_HOME:-$HOME/.copilot}"
    local sources=(
        "Claude Code|$claude_config/memory-kit.json"
        "Gemini CLI|$HOME/.gemini/memory-kit.json"
        "Codex|$HOME/.codex/memory-kit.json"
        "Copilot CLI|$copilot_config/memory-kit.json"
        "Antigravity CLI|$HOME/.gemini/antigravity-cli/memory-kit.json"
        "Antigravity Desktop|$HOME/.gemini/antigravity/memory-kit.json"
    )

    EXISTING_VAULTS=()
    for entry in "${sources[@]}"; do
        local source="${entry%%|*}"
        local config_file="${entry#*|}"
        [[ -f "$config_file" ]] || continue
        if command -v python3 &>/dev/null; then
            local vault
            vault="$(python3 -c "
import json, sys, os
try:
    with open('$config_file') as f:
        c = json.load(f)
    v = c.get('vault', '')
    if v:
        print(os.path.normpath(v))
except Exception:
    pass
" 2>/dev/null)" || true
            if [[ -n "$vault" ]]; then
                EXISTING_VAULTS+=("$source|$config_file|$vault")
            fi
        fi
    done
}

# ============================================================
# Cleanup migration v0.4 -> v0.5
# ============================================================
# Supprime les skills/commandes/templates obsoletes apres renommages :
#   recall             -> mem-recall            (pre-v0.4)
#   archive            -> mem-archive           (pre-v0.4)
#   mem-list-projects  -> mem-list              (v0.5)
#   mem-rename-project -> mem-rename            (v0.5)
#   mem-merge-projects -> mem-merge             (v0.5)
# Idempotent : si les fichiers ont deja ete supprimes, ne fait rien.
#
# Args : aucun (utilise DETECTED_IDX et PLATFORM_* en globaux).

remove_deprecated_v04_files() {
    local obsolete=("recall" "archive" "mem-list-projects" "mem-rename-project" "mem-merge-projects")
    local count=0

    for i in "${DETECTED_IDX[@]}"; do
        local cli="${PLATFORM_NAMES[$i]}"
        local config="${PLATFORM_CONFIGS[$i]}"
        [[ -d "$config" ]] || continue

        for name in "${obsolete[@]}"; do
            case "$cli" in
                claude-code)
                    if [[ -f "$config/skills/$name.md" ]]; then
                        rm -f "$config/skills/$name.md"
                        _green "Cleanup v0.4 : Claude/skills/$name.md supprime"
                        count=$((count+1))
                    fi
                    if [[ -f "$config/commands/$name.md" ]]; then
                        rm -f "$config/commands/$name.md"
                        _green "Cleanup v0.4 : Claude/commands/$name.md supprime"
                        count=$((count+1))
                    fi
                    ;;
                gemini-cli)
                    if [[ -f "$config/extensions/memory-kit/commands/$name.toml" ]]; then
                        rm -f "$config/extensions/memory-kit/commands/$name.toml"
                        _green "Cleanup v0.4 : Gemini/extensions/memory-kit/commands/$name.toml supprime"
                        count=$((count+1))
                    fi
                    ;;
                codex)
                    if [[ -f "$config/prompts/$name.md" ]]; then
                        rm -f "$config/prompts/$name.md"
                        _green "Cleanup v0.4 : Codex/prompts/$name.md supprime"
                        count=$((count+1))
                    fi
                    if [[ -d "$config/skills/$name" ]]; then
                        rm -rf "$config/skills/$name"
                        _green "Cleanup v0.4 : Codex/skills/$name/ supprime"
                        count=$((count+1))
                    fi
                    ;;
                mistral-vibe)
                    if [[ -d "$config/skills/$name" ]]; then
                        rm -rf "$config/skills/$name"
                        _green "Cleanup v0.4 : Vibe/skills/$name/ supprime"
                        count=$((count+1))
                    fi
                    ;;
                copilot-cli)
                    if [[ -d "$config/skills/$name" ]]; then
                        rm -rf "$config/skills/$name"
                        _green "Cleanup v0.4 : Copilot/skills/$name/ supprime"
                        count=$((count+1))
                    fi
                    ;;
                antigravity-cli|antigravity-desktop)
                    if [[ -d "$config/skills/$name" ]]; then
                        rm -rf "$config/skills/$name"
                        _green "Cleanup v0.4 : $cli/skills/$name/ supprime"
                        count=$((count+1))
                    fi
                    ;;
            esac
        done
    done

    if [[ $count -eq 0 ]]; then
        _gray "Cleanup v0.4 : rien a supprimer (deja a jour)"
    fi
}

# ============================================================
# Adapter : Claude Code
# ============================================================

deploy_claude_code() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Claude Code"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Claude Code introuvable ($config_dir). Lance Claude Code au moins une fois."
        return 1
    fi

    # Sous-dossiers cibles
    local commands_target="$config_dir/commands"
    local skills_target="$config_dir/skills"
    mkdir -p "$commands_target" "$skills_target"

    # Commands (copie directe)
    local commands_source="$kit_root/adapters/claude-code/commands"
    for f in "$commands_source"/*.md; do
        [[ -f "$f" ]] || continue
        cp "$f" "$commands_target/$(basename "$f")"
        _green "Command : $(basename "$f")"
    done

    # Skills (template + procedure core + substitution CONFIG_FILE)
    local skills_source="$kit_root/adapters/claude-code/skills"
    local core_source="$kit_root/core/procedures"
    local config_file_ref='`~/.claude/memory-kit.json` (ou `$CLAUDE_CONFIG_DIR/memory-kit.json` si defini)'

    for tpl in "$skills_source"/*.template.md; do
        [[ -f "$tpl" ]] || continue
        local skill_name
        skill_name="$(basename "$tpl" .template.md)"
        local procedure_path="$core_source/$skill_name.md"
        if [[ ! -f "$procedure_path" ]]; then
            _yellow "Procedure core manquante pour $skill_name (ignore)"
            continue
        fi
        local procedure_content
        procedure_content="$(assemble_procedure "$procedure_path" "$core_source" "$config_file_ref" "$skill_name")" || {
            _yellow "Echec assemblage procedure $skill_name (ignore)"
            continue
        }
        local template_content
        template_content="$(cat "$tpl")"
        local assembled="${template_content//\{\{PROCEDURE\}\}/$procedure_content}"
        printf '%s' "$assembled" > "$skills_target/$skill_name.md"
        _green "Skill   : $skill_name.md"
    done

    # Agents (subagents enregistres) — frontmatter du template + resolution des
    # includes core. L'expander wrappe {{INCLUDE _archive-expander}} (le contrat
    # partage avec la procedure mem-archive). assemble_procedure sans skill_name
    # (4e arg vide) = includes-only, pas de prepend MCP-first : un agent n'est
    # pas un skill. Claude Code est la seule plateforme au mecanisme d'agent
    # enregistre connu du kit ; les autres CLI recoivent le meme contrat inline
    # dans leur skill mem-archive (cf. _archive-expander.md).
    local agents_source="$kit_root/adapters/claude-code/agents"
    if [[ -d "$agents_source" ]]; then
        local agents_target="$config_dir/agents"
        mkdir -p "$agents_target"
        for atpl in "$agents_source"/*.template.md; do
            [[ -f "$atpl" ]] || continue
            local agent_name
            agent_name="$(basename "$atpl" .template.md)"
            local agent_content
            agent_content="$(assemble_procedure "$atpl" "$core_source" "" "")" || {
                _yellow "Echec assemblage agent $agent_name (ignore)"
                continue
            }
            printf '%s' "$agent_content" > "$agents_target/$agent_name.md"
            _green "Agent   : $agent_name.md"
        done
    fi

    # memory-kit.json
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    # Bloc MEMORY-KIT dans CLAUDE.md utilisateur (idempotent)
    local claude_md_target="$config_dir/CLAUDE.md"
    local block_path="$kit_root/adapters/claude-code/claude-md-block.md"
    local block_content
    block_content="$(cat "$block_path")"
    local start_marker='<!-- MEMORY-KIT:START -->'
    local end_marker='<!-- MEMORY-KIT:END -->'

    local existing=""
    if [[ -f "$claude_md_target" ]]; then
        existing="$(cat "$claude_md_target")"
    fi
    # Supprimer l'ancien bloc s'il existe (perl compatible macOS + Linux)
    local cleaned
    cleaned="$(printf '%s' "$existing" | perl -0777 -pe "s/\Q${start_marker}\E[\s\S]*?\Q${end_marker}\E//g")"
    cleaned="$(echo "$cleaned" | sed -e 's/[[:space:]]*$//')"
    local final
    if [[ -n "$cleaned" ]]; then
        final="${cleaned}

${block_content}"
    else
        final="$block_content"
    fi
    printf '%s' "$final" > "$claude_md_target"
    _green "CLAUDE.md utilisateur : bloc MEMORY-KIT injecte"

    # Permissions : settings.json (idempotent, via python3)
    local settings_file="$config_dir/settings.json"
    if [[ ! -f "$settings_file" ]]; then
        printf '%s' '{}' > "$settings_file"
    fi

    if command -v python3 &>/dev/null; then
        local _perm_result
        _perm_result="$(python3 << PYEOF
import json

settings_file = '$settings_file'
vault = '$vault_path'

with open(settings_file, 'r') as f:
    settings = json.load(f)

perms = settings.setdefault('permissions', {})
changed = False
messages = []

# additionalDirectories : ajout du vault (idempotent)
dirs = perms.setdefault('additionalDirectories', [])
if vault not in dirs:
    dirs.append(vault)
    changed = True
    messages.append('dir_added')
else:
    messages.append('dir_exists')

# allow : patterns pour les operations vault des skills mem-*
# Les procedures mem-rename-project, mem-merge-projects et mem-rollback-archive
# appellent mv/rm cote shell, ou Rename-Item/Remove-Item/Move-Item via pwsh
# (sur Windows ou cas hybrides Git Bash + pwsh). On autorise les deux familles.
allow = perms.setdefault('allow', [])
mem_patterns = [
    'Bash(mv:*)',
    'Bash(rm:*)',
    'Bash(pwsh -Command Rename-Item:*)',
    'Bash(pwsh -Command Remove-Item:*)',
    'Bash(pwsh -Command Move-Item:*)',
]
added_count = 0
for pat in mem_patterns:
    if pat not in allow:
        allow.append(pat)
        added_count += 1
        changed = True

if added_count:
    messages.append('allow_added:' + str(added_count))
else:
    messages.append('allow_exists')

if changed:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)

print('|'.join(messages))
PYEOF
)"
        # Affichage conditionnel selon le resultat
        if [[ "$_perm_result" == *"dir_added"* ]]; then
            _green "settings.json : additionalDirectories += $vault_path"
        else
            _gray "settings.json : additionalDirectories deja present"
        fi
        if [[ "$_perm_result" == *"allow_added"* ]]; then
            local _count="${_perm_result##*allow_added:}"
            _count="${_count%%|*}"
            _green "settings.json : allow += $_count pattern(s) mem-*"
        else
            _gray "settings.json : patterns allow mem-* deja presents"
        fi
    else
        _yellow "python3 non disponible — permissions settings.json non modifiees"
    fi

    return 0
}

# ============================================================
# Adapter : Gemini CLI
# ============================================================

deploy_gemini_cli() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Gemini CLI"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Gemini introuvable ($config_dir). Lance 'gemini' au moins une fois."
        return 1
    fi

    # ~/.gemini/extensions/memory-kit/{commands}
    local ext_dir="$config_dir/extensions/memory-kit"
    local cmd_dir="$ext_dir/commands"
    mkdir -p "$cmd_dir"

    local adapter_dir="$kit_root/adapters/gemini-cli"

    # Manifest + GEMINI.md (copie directe)
    cp "$adapter_dir/gemini-extension.json" "$ext_dir/"
    _green "gemini-extension.json"
    cp "$adapter_dir/GEMINI.md" "$ext_dir/"
    _green "GEMINI.md"

    # Commands (template + procedure core + substitution CONFIG_FILE)
    local core_source="$kit_root/core/procedures"
    local config_file_ref='`~/.gemini/memory-kit.json`'

    for tpl in "$adapter_dir/commands"/*.template.toml; do
        [[ -f "$tpl" ]] || continue
        local command_name
        command_name="$(basename "$tpl" .template.toml)"
        local procedure_path="$core_source/$command_name.md"
        if [[ ! -f "$procedure_path" ]]; then
            _yellow "Procedure core manquante pour $command_name (ignore)"
            continue
        fi
        local procedure_content
        procedure_content="$(assemble_procedure "$procedure_path" "$core_source" "$config_file_ref" "$command_name")" || {
            _yellow "Echec assemblage procedure $command_name (ignore)"
            continue
        }
        local template_content
        template_content="$(cat "$tpl")"
        local assembled="${template_content//\{\{PROCEDURE\}\}/$procedure_content}"
        printf '%s' "$assembled" > "$cmd_dir/$command_name.toml"
        _green "Command : $command_name.toml"
    done

    # memory-kit.json au niveau utilisateur
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    # Activer l'extension dans extension-enablement.json (idempotent)
    local enablement_file="$config_dir/extensions/extension-enablement.json"
    local home_pattern="$HOME/*"

    if command -v python3 &>/dev/null; then
        python3 << PYEOF
import json, os

enablement_file = '$enablement_file'
home_pattern = '$home_pattern'

if os.path.exists(enablement_file):
    with open(enablement_file, 'r') as f:
        enablement = json.load(f)
else:
    enablement = {}

if 'memory-kit' not in enablement:
    enablement['memory-kit'] = {"overrides": [home_pattern]}
    with open(enablement_file, 'w') as f:
        json.dump(enablement, f, indent=2)
PYEOF
        if python3 -c "
import json
with open('$enablement_file') as f:
    e = json.load(f)
exit(0 if 'memory-kit' in e else 1)
"; then
            _green "extension-enablement.json : memory-kit active"
        fi
    else
        _yellow "python3 non disponible — activation extension manuelle requise"
    fi

    return 0
}

# ============================================================
# Adapter : Codex (OpenAI)
# ============================================================

deploy_codex() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Codex (OpenAI)"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Codex introuvable ($config_dir). Lance 'codex' au moins une fois."
        return 1
    fi

    local prompts_target="$config_dir/prompts"
    local skills_target="$config_dir/skills"
    mkdir -p "$prompts_target" "$skills_target"

    local adapter_dir="$kit_root/adapters/codex"
    local core_source="$kit_root/core/procedures"
    local config_file_ref='`~/.codex/memory-kit.json`'

    # Prompts (slash commands user-level)
    local prompts_source="$adapter_dir/prompts"
    if [[ -d "$prompts_source" ]]; then
        for tpl in "$prompts_source"/*.template.md; do
            [[ -f "$tpl" ]] || continue
            local name
            name="$(basename "$tpl" .template.md)"
            local proc_path="$core_source/$name.md"
            if [[ ! -f "$proc_path" ]]; then
                _yellow "Procedure core manquante pour prompt $name (ignore)"
                continue
            fi
            local proc
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref" "$name")" || {
                _yellow "Echec assemblage procedure $name (ignore)"
                continue
            }
            local tpl_content
            tpl_content="$(cat "$tpl")"
            local assembled="${tpl_content//\{\{PROCEDURE\}\}/$proc}"
            printf '%s' "$assembled" > "$prompts_target/$name.md"
            _green "Prompt  : $name.md"
        done
    fi

    # Skills (format Anthropic : skills/{nom}/SKILL.md)
    local skills_source="$adapter_dir/skills"
    if [[ -d "$skills_source" ]]; then
        for skill_dir in "$skills_source"/*/; do
            [[ -d "$skill_dir" ]] || continue
            local name
            name="$(basename "$skill_dir")"
            local tpl_file="$skill_dir/SKILL.md.template"
            if [[ ! -f "$tpl_file" ]]; then
                _yellow "SKILL.md.template manquant pour $name (ignore)"
                continue
            fi
            local proc_path="$core_source/$name.md"
            if [[ ! -f "$proc_path" ]]; then
                _yellow "Procedure core manquante pour skill $name (ignore)"
                continue
            fi
            local tpl_content
            tpl_content="$(cat "$tpl_file")"
            local proc
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref" "$name")" || {
                _yellow "Echec assemblage procedure $name (ignore)"
                continue
            }
            local assembled="${tpl_content//\{\{PROCEDURE\}\}/$proc}"
            local dest_dir="$skills_target/$name"
            mkdir -p "$dest_dir"
            printf '%s' "$assembled" > "$dest_dir/SKILL.md"
            _green "Skill   : $name/SKILL.md"
        done
    fi

    # memory-kit.json au niveau utilisateur
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    return 0
}

# ============================================================
# Adapter : Mistral Vibe
# ============================================================

deploy_mistral_vibe() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Mistral Vibe"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Vibe introuvable ($config_dir). Lance 'vibe' au moins une fois."
        return 1
    fi

    local adapter_dir="$kit_root/adapters/mistral-vibe"
    local start_marker='<!-- MEMORY-KIT:START -->'
    local end_marker='<!-- MEMORY-KIT:END -->'

    # --- Migration : cleanup de l'ancien bloc dans instructions.md ---
    # L'adapter visait initialement ~/.vibe/instructions.md en assumant que Vibe
    # le chargerait comme un system prompt, ce qui etait faux. On retire le
    # bloc pour que l'utilisateur ne se retrouve pas avec deux copies.
    local legacy_file="$config_dir/instructions.md"
    if [[ -f "$legacy_file" ]]; then
        local legacy_content
        legacy_content="$(cat "$legacy_file")"
        if [[ "$legacy_content" == *"$start_marker"* ]]; then
            local cleaned
            cleaned="$(printf '%s' "$legacy_content" | perl -0777 -pe "s/\Q${start_marker}\E[\s\S]*?\Q${end_marker}\E//g")"
            cleaned="$(echo "$cleaned" | sed -e 's/[[:space:]]*$//')"
            if [[ -z "$cleaned" ]]; then
                rm "$legacy_file"
                _info "instructions.md : fichier legacy supprime (ne contenait que le bloc MEMORY-KIT)"
            else
                printf '%s' "$cleaned" > "$legacy_file"
                _info "instructions.md : bloc MEMORY-KIT retire (reste du contenu preserve)"
            fi
        fi
    fi

    # --- Injection du bloc dans ~/.vibe/AGENTS.md (vrai fichier charge par Vibe) ---
    # Source : vibe/core/system_prompt.py charge ~/.vibe/AGENTS.md comme
    # user-level instructions a chaque session.
    local block_path="$adapter_dir/instructions-block.md"
    if [[ ! -f "$block_path" ]]; then
        _yellow "instructions-block.md manquant : $block_path"
        return 1
    fi
    local block_content
    block_content="$(cat "$block_path")"
    block_content="${block_content//\{\{VAULT_PATH\}\}/$vault_path}"

    local agents_file="$config_dir/AGENTS.md"
    local existing=""
    if [[ -f "$agents_file" ]]; then
        existing="$(cat "$agents_file")"
    fi
    local cleaned
    cleaned="$(printf '%s' "$existing" | perl -0777 -pe "s/\Q${start_marker}\E[\s\S]*?\Q${end_marker}\E//g")"
    cleaned="$(echo "$cleaned" | sed -e 's/[[:space:]]*$//')"
    local final
    if [[ -n "$cleaned" ]]; then
        final="${cleaned}

${block_content}"
    else
        final="$block_content"
    fi
    printf '%s' "$final" > "$agents_file"
    _green "AGENTS.md : bloc MEMORY-KIT injecte"

    # --- Skills (format ~/.vibe/skills/{nom}/SKILL.md) ---
    local skills_target="$config_dir/skills"
    mkdir -p "$skills_target"
    local skills_source="$adapter_dir/skills"
    local core_source="$kit_root/core/procedures"
    local config_file_ref='`~/.vibe/AGENTS.md` (bloc MEMORY-KIT)'
    if [[ -d "$skills_source" ]]; then
        for skill_dir in "$skills_source"/*/; do
            [[ -d "$skill_dir" ]] || continue
            local name
            name="$(basename "$skill_dir")"
            local tpl_file="$skill_dir/SKILL.md.template"
            if [[ ! -f "$tpl_file" ]]; then
                _yellow "SKILL.md.template manquant pour $name (ignore)"
                continue
            fi
            local proc_path="$core_source/$name.md"
            if [[ ! -f "$proc_path" ]]; then
                _yellow "Procedure core manquante pour skill $name (ignore)"
                continue
            fi
            local tpl_content
            tpl_content="$(cat "$tpl_file")"
            local proc
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref" "$name")" || {
                _yellow "Echec assemblage procedure $name (ignore)"
                continue
            }
            local assembled="${tpl_content//\{\{PROCEDURE\}\}/$proc}"
            local dest_dir="$skills_target/$name"
            mkdir -p "$dest_dir"
            printf '%s' "$assembled" > "$dest_dir/SKILL.md"
            _green "Skill   : $name/SKILL.md"
        done
    fi

    return 0
}

# ============================================================
# Adapter : GitHub Copilot CLI (v0.7.5)
# ============================================================
# Surface confirmee :
#   - skills/{nom}/SKILL.md format Anthropic (frontmatter name + description),
#     auto-decouvert depuis ~/.copilot/skills/. Chaque skill expose nativement
#     son slash command /{name}.
#   - Instructions user-level dans ~/.copilot/copilot-instructions.md
#     (equivalent CLAUDE.md / GEMINI.md / AGENTS.md cote user).
#   - Pas de couche prompts/ separee comme Codex : le skill EST le slash command.
#   - Override config dir via $COPILOT_HOME.

deploy_copilot_cli() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : GitHub Copilot CLI"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Copilot CLI introuvable ($config_dir). Lance 'copilot' au moins une fois."
        return 1
    fi

    local adapter_dir="$kit_root/adapters/copilot-cli"
    local core_source="$kit_root/core/procedures"

    # --- Skills (format Anthropic : skills/{nom}/SKILL.md) ---
    local skills_target="$config_dir/skills"
    mkdir -p "$skills_target"
    local skills_source="$adapter_dir/skills"
    local config_file_ref='`~/.copilot/memory-kit.json` (ou `$COPILOT_HOME/memory-kit.json` si defini)'
    if [[ -d "$skills_source" ]]; then
        for skill_dir in "$skills_source"/*/; do
            [[ -d "$skill_dir" ]] || continue
            local name
            name="$(basename "$skill_dir")"
            local tpl_file="$skill_dir/SKILL.md.template"
            if [[ ! -f "$tpl_file" ]]; then
                _yellow "SKILL.md.template manquant pour $name (ignore)"
                continue
            fi
            local proc_path="$core_source/$name.md"
            if [[ ! -f "$proc_path" ]]; then
                _yellow "Procedure core manquante pour skill $name (ignore)"
                continue
            fi
            local tpl_content
            tpl_content="$(cat "$tpl_file")"
            local proc
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref" "$name")" || {
                _yellow "Echec assemblage procedure $name (ignore)"
                continue
            }
            local assembled="${tpl_content//\{\{PROCEDURE\}\}/$proc}"
            local dest_dir="$skills_target/$name"
            mkdir -p "$dest_dir"
            printf '%s' "$assembled" > "$dest_dir/SKILL.md"
            _green "Skill   : $name/SKILL.md"
        done
    fi

    # --- Bloc d'instructions dans ~/.copilot/copilot-instructions.md ---
    # Note : Copilot CLI accepte aussi AGENTS.md repo-level, mais cote user
    # c'est copilot-instructions.md qui est canonique.
    local block_path="$adapter_dir/copilot-instructions-block.md"
    if [[ ! -f "$block_path" ]]; then
        _yellow "copilot-instructions-block.md manquant : $block_path"
        return 1
    fi
    local block_content
    block_content="$(cat "$block_path")"
    block_content="${block_content//\{\{VAULT_PATH\}\}/$vault_path}"

    local instructions_file="$config_dir/copilot-instructions.md"
    local start_marker='<!-- MEMORY-KIT:START -->'
    local end_marker='<!-- MEMORY-KIT:END -->'
    local existing=""
    if [[ -f "$instructions_file" ]]; then
        existing="$(cat "$instructions_file")"
    fi
    local cleaned
    cleaned="$(printf '%s' "$existing" | perl -0777 -pe "s/\Q${start_marker}\E[\s\S]*?\Q${end_marker}\E//g")"
    cleaned="$(echo "$cleaned" | sed -e 's/[[:space:]]*$//')"
    local final
    if [[ -n "$cleaned" ]]; then
        final="${cleaned}

${block_content}"
    else
        final="$block_content"
    fi
    printf '%s' "$final" > "$instructions_file"
    _green "copilot-instructions.md : bloc MEMORY-KIT injecte"

    # --- memory-kit.json au niveau utilisateur ---
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    return 0
}

# ============================================================
# Adapter : Antigravity (CLI + Desktop)
# ============================================================
# Antigravity (CLI et Desktop) charge skills + MCP via un layout plugin :
#   {config_dir}/plugins/memory-kit/
#     plugin.json                       ← {"name": "memory-kit"}
#     skills/{nom}/SKILL.md             ← Anthropic-style frontmatter
# Le mcp_config.json plugin-side n'est pas honore par Antigravity Desktop ;
# la declaration MCP doit aller dans le fichier global ~/.gemini/config/mcp_config.json
# (cf. deploy_mcp_server).

_deploy_antigravity_plugin_layout() {
    local kit_root="$1"
    local config_dir="$2"
    local config_file_ref="$3"

    local plugin_dir="$config_dir/plugins/memory-kit"
    local skills_target="$plugin_dir/skills"
    mkdir -p "$skills_target"

    printf '{\n  "name": "memory-kit"\n}\n' > "$plugin_dir/plugin.json"

    # Cleanup legacy layout (skills ecrits directement dans {config_dir}/skills
    # par les versions <= v0.12.x : Antigravity les ignore).
    local legacy_skills="$config_dir/skills"
    if [[ -d "$legacy_skills" ]]; then
        find "$legacy_skills" -mindepth 1 -maxdepth 1 -type d -name 'mem*' -exec rm -rf {} + 2>/dev/null || true
        rmdir "$legacy_skills" 2>/dev/null || true
    fi
    local legacy_mcp="$config_dir/mcp_config.json"
    if [[ -f "$legacy_mcp" ]]; then
        rm -f "$legacy_mcp"
    fi

    local adapter_dir="$kit_root/adapters/codex"
    local core_source="$kit_root/core/procedures"
    local skills_source="$adapter_dir/skills"
    [[ -d "$skills_source" ]] || return 0

    for skill_dir in "$skills_source"/*/; do
        [[ -d "$skill_dir" ]] || continue
        local name
        name="$(basename "$skill_dir")"
        local tpl_file="$skill_dir/SKILL.md.template"
        if [[ ! -f "$tpl_file" ]]; then
            _yellow "SKILL.md.template manquant pour $name (ignore)"
            continue
        fi
        local proc_path="$core_source/$name.md"
        if [[ ! -f "$proc_path" ]]; then
            _yellow "Procedure core manquante pour skill $name (ignore)"
            continue
        fi
        local tpl_content
        tpl_content="$(cat "$tpl_file")"
        local proc
        proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref" "$name")" || {
            _yellow "Echec assemblage procedure $name (ignore)"
            continue
        }
        local assembled="${tpl_content//\{\{PROCEDURE\}\}/$proc}"
        local dest_dir="$skills_target/$name"
        mkdir -p "$dest_dir"
        printf '%s' "$assembled" > "$dest_dir/SKILL.md"
        _green "Skill   : $name/SKILL.md"
    done
}

deploy_antigravity_cli() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Antigravity CLI"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Antigravity CLI introuvable ($config_dir). Lance 'agy' au moins une fois."
        return 1
    fi

    _deploy_antigravity_plugin_layout "$kit_root" "$config_dir" '`~/.gemini/antigravity-cli/memory-kit.json`'
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    return 0
}

deploy_antigravity_desktop() {
    local kit_root="$1"
    local config_dir="$2"
    local vault_path="$3"

    echo ""
    _cyan "> Deploiement : Antigravity Desktop"

    if [[ ! -d "$config_dir" ]]; then
        _yellow "Dossier Antigravity Desktop introuvable ($config_dir)."
        return 1
    fi

    _deploy_antigravity_plugin_layout "$kit_root" "$config_dir" '`~/.gemini/antigravity/memory-kit.json`'
    write_memory_kit_json "$config_dir/memory-kit.json" "$vault_path" "$kit_root" "work" "$LANGUAGE"

    return 0
}


# ============================================================
# Deploy-McpServer (v0.8.0) — install pipx + sync configs MCP
# ============================================================
# Installe le serveur Python memory-kit-mcp via pipx (fallback pip --user),
# ecrit ~/.memory-kit/config.json, et inject la declaration MCP dans les
# configs des CLI compatibles (Claude Code, Codex, Copilot CLI, Gemini CLI,
# Mistral Vibe + Claude Desktop). Codex Desktop herite de Codex CLI (meme
# fichier ~/.codex/config.toml).

# Tente d'installer pipx automatiquement si absent. Strategie cascadee :
# 1. macOS + brew : `brew install pipx` (sans sudo, geste natif).
# 2. Linux + gestionnaire systeme + sudo non-interactif : apt/dnf/pacman.
# 3. Fallback universel : `python3 -m pip install --user pipx` (avec
#    --break-system-packages si PEP 668 le requiert).
# Apres install, ajoute ~/.local/bin au PATH de la session courante si pipx
# n'est pas encore visible (pipx ensurepath ne touche que le profil shell).
# Retour : 0 si pipx est dispo en sortie, 1 sinon.
ensure_pipx() {
    if command -v pipx &>/dev/null; then
        return 0
    fi
    _cyan "Installation automatique de pipx..."

    local os
    os="$(uname -s)"

    if [[ "$os" == "Darwin" ]] && command -v brew &>/dev/null; then
        if brew install pipx >/dev/null 2>&1; then
            _green "pipx installe via brew"
            _ensure_pipx_on_path
            command -v pipx &>/dev/null && return 0
        else
            _yellow "brew install pipx a echoue, tentative fallback pip --user..."
        fi
    fi

    if [[ "$os" == "Linux" ]] && command -v sudo &>/dev/null; then
        local pkg_cmd=""
        if command -v apt-get &>/dev/null; then
            pkg_cmd="apt-get install -y pipx"
        elif command -v dnf &>/dev/null; then
            pkg_cmd="dnf install -y pipx"
        elif command -v pacman &>/dev/null; then
            pkg_cmd="pacman -S --noconfirm python-pipx"
        fi
        if [[ -n "$pkg_cmd" ]] && sudo -n $pkg_cmd >/dev/null 2>&1; then
            _green "pipx installe via gestionnaire systeme"
            _ensure_pipx_on_path
            command -v pipx &>/dev/null && return 0
        fi
    fi

    local python_bin=""
    if command -v python3 &>/dev/null; then
        python_bin="python3"
    elif command -v python &>/dev/null; then
        python_bin="python"
    fi
    if [[ -z "$python_bin" ]]; then
        _yellow "python introuvable — impossible d'installer pipx automatiquement"
        return 1
    fi

    if "$python_bin" -m pip install --user pipx >/dev/null 2>&1; then
        _green "pipx installe via pip --user"
    elif "$python_bin" -m pip install --user --break-system-packages pipx >/dev/null 2>&1; then
        _green "pipx installe via pip --user --break-system-packages"
    else
        _yellow "Echec install automatique de pipx."
        return 1
    fi
    _ensure_pipx_on_path
    command -v pipx &>/dev/null && return 0
    _yellow "pipx installe mais introuvable sur PATH meme apres ajout ~/.local/bin."
    return 1
}

# pipx ensurepath ajoute ~/.local/bin (ou equivalent) au profil shell, mais
# pas au PATH de la session courante. On l'ajoute manuellement pour que la
# suite du script puisse appeler pipx immediatement.
_ensure_pipx_on_path() {
    if ! command -v pipx &>/dev/null; then
        for candidate in "$HOME/.local/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
            if [[ -x "$candidate/pipx" ]]; then
                export PATH="$candidate:$PATH"
                break
            fi
        done
    fi
    if command -v pipx &>/dev/null; then
        pipx ensurepath >/dev/null 2>&1 || true
    fi
}

install_mcp_server_package() {
    local kit_root="$1"
    local repair="${2:-false}"
    local mcp_server_dir="$kit_root/mcp-server"
    if [[ ! -d "$mcp_server_dir" ]]; then
        _gray "mcp-server/ absent du kit (skip silencieux)"
        return 1
    fi

    # --repair-mcp : nettoie l'install pipx avant de reinstaller. Couvre les
    # cas d'incoherence (shim cree par une install recente mais venv reste
    # sur une ancienne version, ModuleNotFoundError sur un module recent...).
    if [[ "$repair" == "true" ]] && command -v pipx &>/dev/null; then
        _cyan "Mode --repair-mcp : nettoyage de l'install pipx avant reinstall..."
        # Kill les process avant uninstall pour eviter les locks Windows.
        local mcp_pids
        mcp_pids="$(pgrep -f 'memory-kit-mcp|memory_kit_mcp\.server' 2>/dev/null | tr '\n' ' ' || true)"
        if [[ -n "$mcp_pids" ]]; then
            local pid_count
            pid_count="$(printf '%s\n' "$mcp_pids" | wc -w | tr -d ' ')"
            _info "Fermeture de $pid_count process(s) memory-kit-mcp actif(s)..."
            # shellcheck disable=SC2086
            kill $mcp_pids 2>/dev/null || true
            sleep 1
            # shellcheck disable=SC2086
            kill -9 $mcp_pids 2>/dev/null || true
        fi
        if pipx uninstall memory-kit-mcp &>/dev/null; then
            _green "Ancien package memory-kit-mcp desinstalle"
        else
            _gray "pipx uninstall n'a pas trouve d'install precedente (ou install corrompue) — on continue"
        fi
    fi

    local already_installed=false
    if command -v memory-kit-mcp &>/dev/null; then
        already_installed=true
    fi

    # Determine la version cible (depuis pyproject.toml du kit) et la version
    # actuellement installee via pipx (si applicable). Permet de signaler
    # CLAIREMENT a l'utilisateur quand une session active bloque l'upgrade.
    local target_version=""
    if [[ -f "$mcp_server_dir/pyproject.toml" ]]; then
        target_version="$(grep -E '^[[:space:]]*version[[:space:]]*=' "$mcp_server_dir/pyproject.toml" | head -n1 | sed -E 's/.*"([^"]+)".*/\1/')"
    fi
    local installed_version=""
    if [[ "$already_installed" == "true" ]] && command -v pipx &>/dev/null; then
        installed_version="$(pipx list --short 2>/dev/null | awk '$1 == "memory-kit-mcp" {print $2; exit}')"
    fi

    ensure_pipx || true

    if command -v pipx &>/dev/null; then
        _cyan "Install/upgrade memory-kit-mcp via pipx..."
        if [[ -n "$target_version" && -n "$installed_version" && "$target_version" != "$installed_version" ]]; then
            _info "Pipx package version: $installed_version installed, $target_version required."
        fi
        local pipx_output
        if pipx_output="$(pipx install --force "$mcp_server_dir" 2>&1)"; then
            _green "memory-kit-mcp installe via pipx (version $target_version)"
            return 0
        fi

        # Detect file-in-use error (mostly Windows under Git Bash; rare on
        # macOS/Linux but possible if a process holds a lock).
        local is_in_use=false
        if printf '%s' "$pipx_output" | grep -qiE "in use|cannot access|deleteme|text file busy|winerror 32"; then
            is_in_use=true
        fi
        local versions_match=false
        if [[ -n "$target_version" && -n "$installed_version" && "$target_version" == "$installed_version" ]]; then
            versions_match=true
        fi

        # No-op safe : versions identiques, fichier verrouille → accepte.
        if [[ "$already_installed" == "true" && "$is_in_use" == "true" && "$versions_match" == "true" ]]; then
            _gray "memory-kit-mcp deja a la bonne version ($installed_version) — upgrade no-op"
            return 0
        fi

        # Upgrade requis et fichier verrouille : kill les process memory-kit-mcp*
        # actifs (clients MCP qui ont charge le serveur via stdio), puis retry.
        # Les CLI clients reconnecteront automatiquement au prochain appel d'outil.
        if [[ "$already_installed" == "true" && "$is_in_use" == "true" ]]; then
            local pids
            pids="$(pgrep -f 'memory-kit-mcp|memory_kit_mcp\.server' 2>/dev/null | tr '\n' ' ' || true)"
            if [[ -n "$pids" ]]; then
                local pid_count
                pid_count="$(printf '%s\n' "$pids" | wc -w | tr -d ' ')"
                _info "Upgrade requis ($installed_version -> $target_version). Fermeture de $pid_count process(s) memory-kit-mcp actif(s)..."
                _info "Les sessions CLI (Claude Code / Codex / Copilot / Vibe / Desktop) reconnecteront au prochain outil MCP appele."
                # shellcheck disable=SC2086
                kill $pids 2>/dev/null || true
                sleep 1
                # Force kill si process encore vivants
                # shellcheck disable=SC2086
                kill -9 $pids 2>/dev/null || true
            fi
            local pipx_output2
            if pipx_output2="$(pipx install --force "$mcp_server_dir" 2>&1)"; then
                _green "memory-kit-mcp upgrade vers $target_version (apres fermeture des sessions actives)"
                return 0
            fi
            _yellow "Upgrade encore bloque apres fermeture des process MCP. Sortie pipx :"
            printf '    \033[0;90m%s\033[0m\n' "$pipx_output2"
            _yellow "Le serveur MCP reste sur la version $installed_version. Tente : reboot du poste, puis relance deploy.sh."
            return 0
        fi
        _yellow "pipx install a echoue."
        if [[ "$already_installed" == "true" ]]; then
            _info "Binaire memory-kit-mcp deja sur PATH — utilisation de la version existante."
            return 0
        fi
        _cyan "Tentative fallback pip --user..."
    else
        _yellow "pipx indisponible apres tentative d'auto-install."
        if [[ "$already_installed" == "true" ]]; then
            _gray "Binaire memory-kit-mcp deja sur PATH — pas d'install pip --user."
            return 0
        fi
        _cyan "Tentative install via pip --user..."
    fi

    local python_bin
    if command -v python3 &>/dev/null; then
        python_bin="python3"
    elif command -v python &>/dev/null; then
        python_bin="python"
    else
        _yellow "python introuvable. Install MCP server skip."
        [[ "$already_installed" == "true" ]] && return 0 || return 1
    fi

    if "$python_bin" -m pip install --user --upgrade "$mcp_server_dir" >/dev/null 2>&1; then
        _green "memory-kit-mcp installe via pip --user"
        return 0
    fi
    _yellow "pip install a echoue."
    [[ "$already_installed" == "true" ]] && return 0 || return 1
}

write_mcp_server_config() {
    local vault_path="$1"
    local kit_repo="$2"
    local language="$3"
    # Cf. doc d'archi v0.8.0 §8 : ~/.memory-kit/config.json est la source de
    # verite cote MCP server (override via $MEMORY_KIT_HOME).
    local mcp_home="${MEMORY_KIT_HOME:-$HOME/.memory-kit}"
    mkdir -p "$mcp_home"
    local config_path="$mcp_home/config.json"
    # Force ecrasement : la config MCP server est centrale et doit refleter le
    # vault courant. write_memory_kit_json gere le force via la variable globale
    # FORCE — on la met temporairement a true.
    local _saved_force="$FORCE"
    FORCE=true
    write_memory_kit_json "$config_path" "$vault_path" "$kit_repo" "work" "$language"
    FORCE="$_saved_force"
}

# Injection idempotente d'une declaration MCP dans un fichier JSON au format
# {"mcpServers": {"<name>": {"command": ..., "args": [...]}}} (Claude Code,
# Copilot CLI, Claude Desktop, Gemini CLI). Cleanup des noms legacy fournis
# (migration rename, ex 'memory-kit' -> 'secondbrain-memory-kit').
#
# Args : <config_path> <server_name> <command> <label> [legacy_name1 legacy_name2 ...]

add_mcp_server_to_json_config() {
    local config_path="$1"
    local server_name="$2"
    local command_name="$3"
    local label="$4"
    shift 4
    local legacy_names=("$@")

    if ! command -v python3 &>/dev/null; then
        _yellow "python3 indisponible — injection MCP $server_name dans $config_path skipee"
        return 1
    fi

    local label_tag=""
    [[ -n "$label" ]] && label_tag=" ($label)"

    local legacy_csv=""
    if [[ ${#legacy_names[@]} -gt 0 ]]; then
        legacy_csv="$(IFS=,; echo "${legacy_names[*]}")"
    fi

    local result
    result="$(python3 - "$config_path" "$server_name" "$command_name" "$legacy_csv" << 'PYEOF'
import json, os, sys
from pathlib import Path
from collections import OrderedDict

config_path = Path(sys.argv[1])
server_name = sys.argv[2]
command_name = sys.argv[3]
legacy_names = [n for n in sys.argv[4].split(',') if n]

if config_path.exists():
    try:
        existing = json.loads(config_path.read_text(encoding='utf-8'), object_pairs_hook=OrderedDict)
    except Exception as e:
        print(f"ERR|{e}")
        sys.exit(0)
else:
    existing = OrderedDict()
    config_path.parent.mkdir(parents=True, exist_ok=True)

if 'mcpServers' not in existing:
    existing['mcpServers'] = OrderedDict()
servers = existing['mcpServers']

removed_legacy = []
for legacy in legacy_names:
    if legacy != server_name and legacy in servers:
        del servers[legacy]
        removed_legacy.append(legacy)

new_server = OrderedDict([('command', command_name), ('args', [])])
status = ""

if server_name in servers:
    current = servers[server_name]
    if current.get('command') != command_name:
        servers[server_name] = new_server
        status = "UPDATED"
    else:
        status = "SKIP"
else:
    servers[server_name] = new_server
    status = "ADDED"

if status in ("UPDATED", "ADDED") or removed_legacy:
    config_path.write_text(json.dumps(existing, indent=2), encoding='utf-8')

print(f"{status}|{','.join(removed_legacy)}")
PYEOF
)"

    case "$result" in
        ERR\|*)
            _yellow "$config_path illisible (${result#ERR|}). Inject MCP skip."
            return 1
            ;;
    esac

    local status="${result%%|*}"
    local removed="${result#*|}"

    if [[ -n "$removed" ]]; then
        IFS=',' read -ra _legacy_arr <<< "$removed"
        for _l in "${_legacy_arr[@]}"; do
            _green "$config_path$label_tag : mcpServers.$_l supprime (legacy)"
        done
    fi

    case "$status" in
        ADDED)   _green "$config_path$label_tag : mcpServers.$server_name ajoute" ;;
        UPDATED) _green "$config_path$label_tag : mcpServers.$server_name mis a jour" ;;
        SKIP)    _gray  "$config_path$label_tag : mcpServers.$server_name deja present" ;;
    esac
    return 0
}

# Injection idempotente d'une section TOML [mcp_servers.<name>] (format Codex).
# Pas de parser TOML natif bash : on utilise des markers MEMORY-KIT:START/END.
#
# Args : <config_path> <section_name> <command> <label>

add_mcp_server_to_opendesign_config() {
    local config_path="$1"
    local server_name="$2"
    local command_name="$3"
    local label="$4"
    shift 4
    local legacy_names=("$@")

    if ! command -v python3 &>/dev/null; then
        _yellow "python3 indisponible — injection MCP $server_name dans $config_path skipee"
        return 1
    fi

    local label_tag=""
    [[ -n "$label" ]] && label_tag=" ($label)"

    local legacy_csv=""
    if [[ ${#legacy_names[@]} -gt 0 ]]; then
        legacy_csv="$(IFS=,; echo "${legacy_names[*]}")"
    fi

    local result
    result="$(python3 - "$config_path" "$server_name" "$command_name" "$legacy_csv" << 'PYEOF'
import json, os, sys
from pathlib import Path
from collections import OrderedDict

config_path = Path(sys.argv[1])
server_name = sys.argv[2]
command_name = sys.argv[3]
legacy_names = [n for n in sys.argv[4].split(',') if n]

if config_path.exists():
    try:
        existing = json.loads(config_path.read_text(encoding='utf-8'), object_pairs_hook=OrderedDict)
    except Exception as e:
        print(f"ERR|{e}")
        sys.exit(0)
else:
    existing = OrderedDict()
    config_path.parent.mkdir(parents=True, exist_ok=True)

if 'servers' not in existing or not isinstance(existing['servers'], list):
    existing['servers'] = []

servers = existing['servers']

removed_legacy = []
for legacy in legacy_names:
    for i in range(len(servers)-1, -1, -1):
        if servers[i].get('id') == legacy and legacy != server_name:
            servers.pop(i)
            if legacy not in removed_legacy:
                removed_legacy.append(legacy)

new_server = OrderedDict([
    ('id', server_name),
    ('transport', 'stdio'),
    ('enabled', True),
    ('label', server_name),
    ('command', command_name),
    ('args', [])
])

status = "ADDED"
for i, s in enumerate(servers):
    if s.get('id') == server_name:
        if s.get('command') != command_name:
            servers[i] = new_server
            status = "UPDATED"
        else:
            status = "SKIP"
        break
else:
    servers.append(new_server)

if status in ("UPDATED", "ADDED") or removed_legacy:
    config_path.write_text(json.dumps(existing, indent=2), encoding='utf-8')

print(f"{status}|{','.join(removed_legacy)}")
PYEOF
)"

    case "$result" in
        ERR\|*)
            _yellow "$config_path illisible (${result#ERR|}). Inject MCP skip."
            return 1
            ;;
    esac

    local status="${result%%|*}"
    local removed="${result#*|}"

    if [[ -n "$removed" ]]; then
        IFS=',' read -ra _legacy_arr <<< "$removed"
        for _l in "${_legacy_arr[@]}"; do
            _green "$config_path$label_tag : servers.$_l supprime (legacy)"
        done
    fi

    case "$status" in
        ADDED)   _green "$config_path$label_tag : servers.$server_name ajoute" ;;
        UPDATED) _green "$config_path$label_tag : servers.$server_name mis a jour" ;;
        SKIP)    _gray  "$config_path$label_tag : servers.$server_name deja present" ;;
    esac
    return 0
}

add_mcp_server_to_toml_config() {
    local config_path="$1"
    local section_name="$2"
    local command_name="$3"
    local label="$4"

    local label_tag=""
    [[ -n "$label" ]] && label_tag=" ($label)"

    local start_marker='# MEMORY-KIT:START'
    local end_marker='# MEMORY-KIT:END'
    # TOML literal string (single-quote) pour le path Windows : sinon les
    # backslashes sont interpretes comme escapes par le parser TOML strict de
    # Codex (`\U` -> unicode escape attendu, parse error).
    local block
    block="$(printf "%s\n[mcp_servers.%s]\ncommand = '%s'\nargs = []\n%s" \
        "$start_marker" "$section_name" "$command_name" "$end_marker")"

    if [[ ! -f "$config_path" ]]; then
        local parent
        parent="$(dirname "$config_path")"
        mkdir -p "$parent"
        printf '%s' "$block" > "$config_path"
        _green "$config_path$label_tag : section [mcp_servers.$section_name] cree (nouveau fichier)"
        return 0
    fi

    local existing
    existing="$(cat "$config_path")"

    # Migration : retirer toute section orpheline `[mcp_servers.<section_name>]`
    # (et ses sous-tables) qui ne serait PAS deja dans le bloc fenced — sinon
    # une install precedente sans markers + une nouvelle injection avec markers
    # produiraient un duplicate-key TOML refuse par Codex. On retire d'abord le
    # bloc fenced (s'il existe) du contenu temporaire, puis on supprime tout
    # `[mcp_servers.SECTION]` ou `[mcp_servers.SECTION.foo.bar]` orphelin.
    # Extraire le bloc MEMORY-KIT-PERMS (auto-approve par outil) avant
    # detection orphan, pour qu'il ne soit ni traite comme orphelin (sous-tables
    # [mcp_servers.SECTION.tools.X]) ni perdu lors de la reconstruction.
    local perms_start='# MEMORY-KIT-PERMS:START'
    local perms_end='# MEMORY-KIT-PERMS:END'
    local perms_block
    perms_block="$(perl -0777 -ne '
        if (/(\Q'"$perms_start"'\E[\s\S]*?\Q'"$perms_end"'\E)/) { print $1 }
    ' <<< "$existing")"

    local existing_no_fenced
    existing_no_fenced="$(perl -0777 -pe '
        s/\Q'"$start_marker"'\E[\s\S]*?\Q'"$end_marker"'\E//g;
        s/\Q'"$perms_start"'\E[\s\S]*?\Q'"$perms_end"'\E//g;
    ' <<< "$existing")"

    local cleaned
    cleaned="$(SECTION="$section_name" perl -0777 -pe '
        my $s = quotemeta $ENV{SECTION};
        s/^[ \t]*\[mcp_servers\.${s}(\.[^\]\r\n]*)?\][\s\S]*?(?=(\r?\n[ \t]*\[)|\z)//mg;
    ' <<< "$existing_no_fenced")"

    # Trim trailing whitespace for stable separator handling.
    cleaned="$(printf '%s' "$cleaned" | sed -e 's/[[:space:]]*$//')"
    local existing_no_fenced_trimmed
    existing_no_fenced_trimmed="$(printf '%s' "$existing_no_fenced" | sed -e 's/[[:space:]]*$//')"
    local had_orphan="false"
    [[ "$cleaned" != "$existing_no_fenced_trimmed" ]] && had_orphan="true"

    if printf '%s' "$existing" | grep -q "^${start_marker}$" && [[ "$had_orphan" == "false" ]]; then
        # Cas commun : aucune orpheline, fenced presente. Update in place.
        local new_content
        new_content="$(BLOCK="$block" perl -0777 -pe '
            my $b = $ENV{BLOCK};
            s/\Q'"$start_marker"'\E[\s\S]*?\Q'"$end_marker"'\E/$b/g;
        ' <<< "$existing")"
        if [[ "$new_content" == "$existing" ]]; then
            _gray "$config_path$label_tag : section MEMORY-KIT deja a jour"
            return 0
        fi
        printf '%s' "$new_content" > "$config_path"
        _green "$config_path$label_tag : section MEMORY-KIT mise a jour"
        return 0
    fi

    # Soit pas de fenced, soit on a detecte une orpheline a purger : on
    # reconstruit le fichier proprement avec une seule section fenced finale,
    # suivie du bloc MEMORY-KIT-PERMS preserve s'il existait.
    local sep=""
    [[ -n "$cleaned" ]] && sep=$'\n\n'
    if [[ -n "$perms_block" ]]; then
        printf '%s%s%s\n\n%s\n' "$cleaned" "$sep" "$block" "$perms_block" > "$config_path"
    else
        printf '%s%s%s\n' "$cleaned" "$sep" "$block" > "$config_path"
    fi
    if [[ "$had_orphan" == "true" ]]; then
        _green "$config_path$label_tag : section orpheline [mcp_servers.$section_name] purgee + section MEMORY-KIT injectee"
    else
        _green "$config_path$label_tag : section MEMORY-KIT injectee"
    fi
}

# Injection idempotente d'une entree TOML [[mcp_servers]] (format Mistral Vibe,
# table d'arrays). Pattern verifie en lisant la config existante de
# mcp-iris-connector qui s'installe deja dans ~/.vibe/config.toml.
#
# Args : <config_path> <server_name> <command> <label>

add_mcp_server_to_vibe_toml_config() {
    local config_path="$1"
    local server_name="$2"
    local command_name="$3"
    local label="$4"

    local label_tag=""
    [[ -n "$label" ]] && label_tag=" ($label)"

    local start_marker='# MEMORY-KIT:START'
    local end_marker='# MEMORY-KIT:END'
    local block
    block="$(printf '%s\n[[mcp_servers]]\nname = "%s"\ntransport = "stdio"\ncommand = "%s"\nargs = []\n%s' \
        "$start_marker" "$server_name" "$command_name" "$end_marker")"

    if [[ ! -f "$config_path" ]]; then
        local parent
        parent="$(dirname "$config_path")"
        mkdir -p "$parent"
        printf '%s' "$block" > "$config_path"
        _green "$config_path$label_tag : entry [[mcp_servers]] cree (nouveau fichier)"
        return 0
    fi

    local existing
    existing="$(cat "$config_path")"
    if printf '%s' "$existing" | grep -q "^${start_marker}$"; then
        local new_content
        new_content="$(BLOCK="$block" perl -0777 -pe '
            my $b = $ENV{BLOCK};
            s/\Q'"$start_marker"'\E[\s\S]*?\Q'"$end_marker"'\E/$b/g;
        ' <<< "$existing")"
        if [[ "$new_content" == "$existing" ]]; then
            _gray "$config_path$label_tag : section MEMORY-KIT deja a jour"
            return 0
        fi
        printf '%s' "$new_content" > "$config_path"
        _green "$config_path$label_tag : section MEMORY-KIT mise a jour"
    else
        local trimmed="${existing%$'\n'}"
        trimmed="$(printf '%s' "$trimmed" | sed -e 's/[[:space:]]*$//')"
        local sep=""
        [[ -n "$trimmed" ]] && sep=$'\n\n'
        printf '%s%s%s\n' "$trimmed" "$sep" "$block" > "$config_path"
        _green "$config_path$label_tag : entry [[mcp_servers]] injectee"
    fi
}

# Resolution du chemin Claude Desktop config selon l'OS.
# - macOS  : ~/Library/Application Support/Claude/claude_desktop_config.json
# - Linux  : ~/.config/Claude/claude_desktop_config.json
# - Windows (Git Bash / WSL) : $APPDATA/Claude/claude_desktop_config.json

claude_desktop_config_path() {
    case "$(uname -s)" in
        Darwin)
            echo "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
            ;;
        Linux)
            echo "$HOME/.config/Claude/claude_desktop_config.json"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            local appdata="${APPDATA:-$HOME/AppData/Roaming}"
            echo "$appdata/Claude/claude_desktop_config.json"
            ;;
        *)
            echo "$HOME/.config/Claude/claude_desktop_config.json"
            ;;
    esac
}

# ============================================================
# sync_local_venv (dev-side) — aligne mcp-server/.venv/ sur pyproject.toml
# ============================================================
# Le venv local mcp-server/.venv/ sert au dev (pytest, archeo-topology direct,
# REPL). Pas utilise par les utilisateurs (pipx). Mais quand pyproject.toml
# bump et que le venv n'est pas reinstalle, la CLI standalone retourne un
# __version__ stale via importlib.metadata, et tout code base sur la version
# courante embarque une valeur incoherente. Cette fonction detecte le venv
# local s'il existe, compare la version installee a celle du pyproject, et
# reinstalle via pip install -e . si diverge. Idempotent. Skip silencieux
# si pas de venv local (cas user standard).

sync_local_venv() {
    local kit_root="$1"
    local mcp_server_dir="$kit_root/mcp-server"

    # Detection venv (Windows path Git Bash + Unix).
    local venv_python=""
    if [[ -x "$mcp_server_dir/.venv/Scripts/python.exe" ]]; then
        venv_python="$mcp_server_dir/.venv/Scripts/python.exe"
    elif [[ -x "$mcp_server_dir/.venv/bin/python" ]]; then
        venv_python="$mcp_server_dir/.venv/bin/python"
    else
        _gray "Pas de venv dev local (mcp-server/.venv/) -- skip"
        return 0
    fi

    local pyproject="$mcp_server_dir/pyproject.toml"
    if [[ ! -f "$pyproject" ]]; then
        _gray "pyproject.toml absent -- skip sync venv local"
        return 0
    fi

    local target_version
    target_version=$(
        grep -E '^[[:space:]]*version[[:space:]]*=' "$pyproject" \
            | head -n 1 \
            | sed -E 's/.*"([^"]+)".*/\1/'
    )
    if [[ -z "$target_version" ]]; then
        _gray "Version introuvable dans pyproject.toml -- skip sync venv local"
        return 0
    fi

    # Detecte le gestionnaire approprie pour ce venv :
    #   - uv  : venv cree par `uv venv`, sans pip embarque. Utiliser
    #           `uv pip ... --python <venv_python>`.
    #   - pip : venv cree par `python -m venv`. Utiliser `python -m pip`.
    local use_uv=false
    if command -v uv >/dev/null 2>&1; then
        if ! "$venv_python" -c "import pip" >/dev/null 2>&1; then
            use_uv=true
        fi
    fi

    local installed_version=""
    if [[ "$use_uv" == "true" ]]; then
        installed_version=$(
            uv pip show memory-kit-mcp --python "$venv_python" 2>/dev/null \
                | grep -E '^Version:' \
                | head -n 1 \
                | awk '{print $2}'
        )
    else
        installed_version=$(
            "$venv_python" -m pip show memory-kit-mcp 2>/dev/null \
                | grep -E '^Version:' \
                | head -n 1 \
                | awk '{print $2}'
        )
    fi

    if [[ "$installed_version" == "$target_version" ]]; then
        _gray "Venv dev local a jour (memory-kit-mcp $target_version)"
        return 0
    fi

    local manager
    if [[ "$use_uv" == "true" ]]; then manager="uv pip"; else manager="pip"; fi

    if [[ -n "$installed_version" ]]; then
        _cyan "Venv dev local: $installed_version -> $target_version. $manager install -e . ..."
    else
        _cyan "Venv dev local: package absent. $manager install -e . ..."
    fi

    local install_ok=false
    if [[ "$use_uv" == "true" ]]; then
        if (cd "$mcp_server_dir" && uv pip install -e . --python "$venv_python" >/dev/null 2>&1); then
            install_ok=true
        fi
    else
        if (cd "$mcp_server_dir" && "$venv_python" -m pip install -e . --quiet >/dev/null 2>&1); then
            install_ok=true
        fi
    fi

    if [[ "$install_ok" == "true" ]]; then
        _green "Venv dev local synchronise a v$target_version (via $manager)"
    else
        _yellow "$manager install -e . a echoue dans le venv dev (skip silencieux)"
    fi
}

deploy_mcp_server() {
    local kit_root="$1"
    local vault_path="$2"
    local repair="${3:-false}"

    echo ""
    # Read the kit's target version dynamically from pyproject.toml — avoid
    # the silent-drift trap where a hardcoded version stays while the package
    # bumps.
    local kit_target_version=""
    if [[ -f "$kit_root/mcp-server/pyproject.toml" ]]; then
        kit_target_version="$(grep -E '^[[:space:]]*version[[:space:]]*=' "$kit_root/mcp-server/pyproject.toml" | head -n1 | sed -E 's/.*"([^"]+)".*/\1/')"
    fi
    if [[ -n "$kit_target_version" ]]; then
        _cyan "> Deploiement : MCP server secondbrain-memory-kit (v$kit_target_version)"
    else
        _cyan "> Deploiement : MCP server secondbrain-memory-kit"
    fi

    if ! install_mcp_server_package "$kit_root" "$repair"; then
        _yellow "MCP server non installe. Les CLI restent en mode skills (fallback)."
        return 0
    fi

    if ! command -v memory-kit-mcp &>/dev/null; then
        # pipx ensurepath persiste l'ajout au profil shell (.bashrc/.zshrc).
        # On l'exécute systématiquement et on rafraîchit le PATH de la
        # session courante via PIPX_BIN_DIR pour que la verification ci-dessous
        # passe sans avoir à ouvrir un nouveau terminal.
        _cyan "Activation du PATH pipx (pipx ensurepath + injection session)..."
        pipx ensurepath >/dev/null 2>&1 || true
        local pipx_bin_dir=""
        pipx_bin_dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || true)"
        [[ -z "$pipx_bin_dir" ]] && pipx_bin_dir="$HOME/.local/bin"
        if [[ -d "$pipx_bin_dir" ]]; then
            export PATH="$pipx_bin_dir:$PATH"
        fi
        if command -v memory-kit-mcp &>/dev/null; then
            _green "memory-kit-mcp accessible apres pipx ensurepath"
        else
            _yellow "Binaire 'memory-kit-mcp' introuvable meme apres pipx ensurepath."
            _info "Ouvre un nouveau terminal ou ajoute manuellement '$pipx_bin_dir' au PATH."
        fi
    fi

    write_mcp_server_config "$vault_path" "$kit_root" "$LANGUAGE"

    # Inject MCP server dans les configs CLI compatibles
    local server_name='secondbrain-memory-kit'
    local server_command='memory-kit-mcp'
    if command -v memory-kit-mcp &>/dev/null; then
        server_command="$(command -v memory-kit-mcp)"
    else
        local pipx_bin_dir=""
        pipx_bin_dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || true)"
        [[ -z "$pipx_bin_dir" ]] && pipx_bin_dir="$HOME/.local/bin"
        if [[ -f "$pipx_bin_dir/memory-kit-mcp" ]]; then
            server_command="$pipx_bin_dir/memory-kit-mcp"
        fi
    fi

    # Claude Code (~/.claude.json — note : different de ~/.claude/memory-kit.json)
    for i in "${DETECTED_IDX[@]}"; do
        case "${PLATFORM_NAMES[$i]}" in
            claude-code)
                add_mcp_server_to_json_config "$HOME/.claude.json" "$server_name" "$server_command" "Claude Code" "memory-kit"
                ;;
            codex)
                add_mcp_server_to_toml_config "${PLATFORM_CONFIGS[$i]}/config.toml" "$server_name" "$server_command" "Codex"
                ;;
            copilot-cli)
                add_mcp_server_to_json_config "${PLATFORM_CONFIGS[$i]}/mcp-config.json" "$server_name" "$server_command" "Copilot CLI" "memory-kit"
                ;;
            mistral-vibe)
                add_mcp_server_to_vibe_toml_config "${PLATFORM_CONFIGS[$i]}/config.toml" "$server_name" "$server_command" "Mistral Vibe"
                ;;
            gemini-cli)
                add_mcp_server_to_json_config "${PLATFORM_CONFIGS[$i]}/settings.json" "$server_name" "$server_command" "Gemini CLI" "memory-kit"
                ;;
            antigravity-cli|antigravity-desktop)
                # Antigravity (CLI et Desktop) lit ses serveurs MCP depuis le
                # fichier partage ~/.gemini/config/mcp_config.json (cf. log
                # language_server : "Failed to load JSON config file
                # C:\Users\bdubois\.gemini\config\mcp_config.json"). Les paths
                # per-app ~/.gemini/antigravity{,-cli}/mcp_config.json sont
                # ignores par Antigravity Desktop. Une seule ecriture suffit ;
                # on garde l'idempotence en s'appuyant sur le marker dejaInjecte
                # du config JSON.
                if [[ -z "${_antigravity_mcp_done:-}" ]]; then
                    local shared_mcp="$HOME/.gemini/config/mcp_config.json"
                    mkdir -p "$(dirname "$shared_mcp")"
                    add_mcp_server_to_json_config "$shared_mcp" "$server_name" "$server_command" "Antigravity (shared config)" "memory-kit"
                    _antigravity_mcp_done=1
                fi
                ;;
        esac
    done
    unset _antigravity_mcp_done

    # Cibles desktop : detection independante des CLI command-line.
    local claude_desktop_config
    claude_desktop_config="$(claude_desktop_config_path)"
    local claude_desktop_dir
    claude_desktop_dir="$(dirname "$claude_desktop_config")"
    if [[ -d "$claude_desktop_dir" ]]; then
        add_mcp_server_to_json_config "$claude_desktop_config" "$server_name" "$server_command" "Claude Desktop" "memory-kit"
    else
        _gray "Claude Desktop non detecte ($claude_desktop_dir absent)"
    fi

    local opendesign_config
    if [[ "$OSTYPE" == "darwin"* ]]; then
        opendesign_config="$HOME/Library/Application Support/Open Design/namespaces/release-stable/data/mcp-config.json"
    else
        opendesign_config="$HOME/.od/mcp-config.json"
    fi
    local opendesign_dir="$(dirname "$opendesign_config")"
    if [[ -d "$opendesign_dir" ]]; then
        add_mcp_server_to_opendesign_config "$opendesign_config" "$server_name" "$server_command" "OpenDesign" "memory-kit"
    else
        # Fallback pour vérifier aussi .od au cas où
        local fallback_config="$HOME/.od/mcp-config.json"
        local fallback_dir="$(dirname "$fallback_config")"
        if [[ -d "$fallback_dir" ]]; then
            add_mcp_server_to_opendesign_config "$fallback_config" "$server_name" "$server_command" "OpenDesign" "memory-kit"
        else
            _gray "OpenDesign non detecte ($opendesign_dir et $fallback_dir absents)"
        fi
    fi

    # Codex Desktop : herite automatiquement de Codex CLI via le meme
    # fichier ~/.codex/config.toml (confirme par utilisateur). Pas d'action
    # supplementaire requise.

    # Pre-seed des allow-lists / auto-approve pour reduire les prompts MCP
    # au strict minimum sur les 37 outils mem* du serveur secondbrain-memory-kit.
    set_mcp_auto_approve_permissions
}

# ============================================================
# set_mcp_auto_approve_permissions — patch idempotent allow-lists/auto-approve
# par client pour minimiser les prompts utilisateur sur les outils MCP du
# serveur secondbrain-memory-kit. Liste statique des 37 outils.
# ============================================================

_secondbrain_mcp_tool_names() {
    cat <<'EOF'
mem
mem_archeo
mem_archeo_atlassian
mem_archeo_context
mem_archeo_context_finalize
mem_archeo_git
mem_archeo_index_files
mem_archeo_plan
mem_archeo_project_topology
mem_archeo_stack
mem_archive
mem_check_update
mem_digest
mem_doc
mem_get_topology
mem_goal
mem_health_repair
mem_health_scan
mem_help
mem_historize
mem_init_project
mem_list
mem_merge
mem_migrate
mem_note
mem_person
mem_principle
mem_promote_domain
mem_read_archive
mem_read_context
mem_read_history
mem_recall
mem_reclass
mem_rename
mem_rollback_archive
mem_search
mem_update_phase
EOF
}

add_claude_mcp_allow_pattern() {
    local config_path="$1"
    [[ -f "$config_path" ]] || return 0
    python3 - "$config_path" <<'PY' || _yellow "Claude allow pattern : echec patch"
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
allow = d.setdefault("permissions", {}).setdefault("allow", [])
pat = "mcp__secondbrain-memory-kit__*"
if pat in allow:
    print(f"[--] {p} (Claude Code) : pattern allow {pat} deja present")
else:
    allow.append(pat)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"[OK] {p} (Claude Code) : permissions.allow += {pat}")
PY
}

enable_gemini_permanent_approval() {
    local config_path="$1"
    local label="$2"
    [[ -f "$config_path" ]] || return 0
    python3 - "$config_path" "$label" <<'PY' || _yellow "Gemini permanent approval : echec patch"
import json, sys
p, label = sys.argv[1], sys.argv[2]
d = json.load(open(p, encoding="utf-8"))
sec = d.setdefault("security", {})
if sec.get("enablePermanentToolApproval") is True:
    print(f"[--] {p} ({label}) : enablePermanentToolApproval deja true")
else:
    sec["enablePermanentToolApproval"] = True
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"[OK] {p} ({label}) : security.enablePermanentToolApproval = true")
PY
}

set_copilot_mcp_tools_wildcard() {
    local config_path="$1"
    [[ -f "$config_path" ]] || return 0
    python3 - "$config_path" <<'PY' || _yellow "Copilot MCP wildcard : echec patch"
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
sb = d.get("mcpServers", {}).get("secondbrain-memory-kit")
if sb is None:
    sys.exit(0)
if sb.get("tools") == ["*"]:
    print(f"[--] {p} (Copilot CLI) : tools=['*'] deja present")
else:
    sb["tools"] = ["*"]
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"[OK] {p} (Copilot CLI) : secondbrain-memory-kit.tools = ['*']")
PY
}

set_vibe_mcp_auto_approve() {
    local config_path="$1"
    [[ -f "$config_path" ]] || return 0
    local tools
    tools="$(_secondbrain_mcp_tool_names | tr '\n' ',' | sed 's/,$//')"
    python3 - "$config_path" "$tools" <<'PY' || _yellow "Vibe auto_approve : echec patch"
import re, sys
p, tools_csv = sys.argv[1], sys.argv[2]
tools = [t for t in tools_csv.split(",") if t]
with open(p, encoding="utf-8") as f:
    txt = f.read()
m = re.search(r"(\[mcp\.auto_approve\]\s*\ntools\s*=\s*\[)([^\]]*)(\])", txt, re.M)
if not m:
    print(f"[--] {p} (Mistral Vibe) : [mcp.auto_approve] tools = [...] introuvable")
    sys.exit(0)
existing = set(re.findall(r'"([^"]+)"', m.group(2)))
to_add = [t for t in tools if t not in existing]
if not to_add:
    print(f"[--] {p} (Mistral Vibe) : mem_* deja dans [mcp.auto_approve]")
    sys.exit(0)
new_inner = m.group(2).rstrip().rstrip(",")
for t in to_add:
    new_inner += f',\n    "{t}"'
new_inner += "\n"
new = txt[:m.start()] + m.group(1) + new_inner + m.group(3) + txt[m.end():]
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(new)
print(f"[OK] {p} (Mistral Vibe) : +{len(to_add)} outils mem_* dans [mcp.auto_approve]")
PY
}

set_codex_mcp_tool_approval_block() {
    local config_path="$1"
    [[ -f "$config_path" ]] || return 0
    local tools
    tools="$(_secondbrain_mcp_tool_names | tr '\n' ',' | sed 's/,$//')"
    python3 - "$config_path" "$tools" <<'PY' || _yellow "Codex MEMORY-KIT-PERMS : echec patch"
import sys
p, tools_csv = sys.argv[1], sys.argv[2]
tools = [t for t in tools_csv.split(",") if t]
marker_start = "# MEMORY-KIT-PERMS:START"
marker_end = "# MEMORY-KIT-PERMS:END"
lines = [marker_start]
for t in tools:
    lines.append(f"[mcp_servers.secondbrain-memory-kit.tools.{t}]")
    lines.append('approval_mode = "auto"')
    lines.append("")
lines.append(marker_end)
block = "\n".join(lines)
with open(p, encoding="utf-8") as f:
    txt = f.read()
start = txt.find(marker_start)
if start >= 0:
    end_search = txt.find(marker_end, start)
    if end_search < 0:
        # Marker START orphelin (END perdu par un cleanup precedent).
        # Recovery : retirer la ligne START seule, puis reinjecter en fin.
        import re as _re
        txt = _re.sub(r'(?m)^[ \t]*' + _re.escape(marker_start) + r'[ \t]*\r?\n?', '', txt)
        if not txt.endswith("\n"):
            txt += "\n"
        txt += "\n" + block + "\n"
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)
        print(f"[OK] {p} (Codex) : marker START orphelin nettoye + bloc MEMORY-KIT-PERMS reinsere ({len(tools)} outils)")
        sys.exit(0)
    end = end_search + len(marker_end)
    new = txt[:start] + block + txt[end:]
    if new == txt:
        print(f"[--] {p} (Codex) : bloc MEMORY-KIT-PERMS deja a jour")
        sys.exit(0)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print(f"[OK] {p} (Codex) : bloc MEMORY-KIT-PERMS refresh ({len(tools)} outils)")
else:
    if not txt.endswith("\n"):
        txt += "\n"
    txt += "\n" + block + "\n"
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print(f"[OK] {p} (Codex) : bloc MEMORY-KIT-PERMS insere ({len(tools)} outils)")
PY
}

set_mcp_auto_approve_permissions() {
    echo ""
    _cyan "> Pre-seed auto-approve / allow-lists MCP secondbrain-memory-kit"
    local i
    for i in "${!PLATFORM_NAMES[@]}"; do
        local platform="${PLATFORM_NAMES[$i]}"
        local cfg="${PLATFORM_CONFIGS[$i]}"
        [[ -d "$cfg" ]] || continue
        case "$platform" in
            claude-code)  add_claude_mcp_allow_pattern "$cfg/settings.json" ;;
            gemini-cli)   enable_gemini_permanent_approval "$cfg/settings.json" "Gemini CLI / Antigravity Desktop" ;;
            copilot-cli)  set_copilot_mcp_tools_wildcard "$cfg/mcp-config.json" ;;
            mistral-vibe) set_vibe_mcp_auto_approve "$cfg/config.toml" ;;
            codex)        set_codex_mcp_tool_approval_block "$cfg/config.toml" ;;
        esac
    done
}

# ============================================================
# invoke_auto_update (--auto-update) — git pull avant deploy
# ============================================================
# Refuse silencieusement si pas un repo git, branche != main, ou working tree
# dirty. Si pull effectif, le main script se relance depuis la source pullee
# pour eviter de deployer avec une logique deploy.sh obsolete deja chargee.

invoke_auto_update() {
    local kit_root="$1"
    local pushd_pwd
    pushd_pwd="$(pwd)"
    cd "$kit_root" || return 1

    local rc=1  # 1 = no update applied (skip), 0 = updated

    if ! command -v git >/dev/null 2>&1; then
        _gray "git introuvable sur PATH : --auto-update ignore"
        cd "$pushd_pwd"
        return 1
    fi

    local is_git
    is_git="$(git rev-parse --is-inside-work-tree 2>/dev/null || true)"
    if [[ "$is_git" != "true" ]]; then
        _gray "Pas dans un git repo : --auto-update ignore"
        cd "$pushd_pwd"
        return 1
    fi

    local branch
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "$branch" != "main" ]]; then
        _yellow "Branche actuelle : '$branch' (attendu : main). --auto-update refuse pour ne pas pull une autre branche."
        cd "$pushd_pwd"
        return 1
    fi

    if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
        _yellow "Working tree dirty (changements non commites). --auto-update refuse — commit ou stash d'abord."
        cd "$pushd_pwd"
        return 1
    fi

    _cyan "git fetch origin --tags..."
    if ! git fetch origin --tags --quiet >/dev/null 2>&1; then
        _yellow "git fetch a echoue : --auto-update ignore"
        cd "$pushd_pwd"
        return 1
    fi

    local behind
    behind="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "")"
    if [[ -z "$behind" ]]; then
        _gray "Comparaison HEAD..origin/main impossible (origin/main absent ?)"
        cd "$pushd_pwd"
        return 1
    fi

    if [[ "$behind" == "0" ]]; then
        local local_tag
        local_tag="$(git describe --tags --abbrev=0 HEAD 2>/dev/null || true)"
        if [[ -n "$local_tag" ]]; then
            _gray "Deja a jour avec origin/main (tag local : $local_tag)"
        else
            _gray "Deja a jour avec origin/main"
        fi
        cd "$pushd_pwd"
        return 1
    fi

    local latest_tag
    latest_tag="$(git describe --tags --abbrev=0 origin/main 2>/dev/null || true)"
    if [[ -n "$latest_tag" ]]; then
        _cyan "Update disponible : $behind commit(s) en arriere — dernier tag remote : $latest_tag. git pull --ff-only..."
    else
        _cyan "Update disponible : $behind commit(s) en arriere. git pull --ff-only..."
    fi

    if ! git pull --ff-only 2>&1 | while IFS= read -r line; do _info "$line"; done; then
        _yellow "git pull --ff-only a echoue : --auto-update ignore (deploy continue avec la version en memoire)"
        cd "$pushd_pwd"
        return 1
    fi

    _green "Kit mis a jour depuis origin/main"
    rc=0
    cd "$pushd_pwd"
    return $rc
}

# Reconstruit les args du re-exec sans --auto-update (evite la boucle).
build_reexec_args() {
    local args=()
    [[ -n "$VAULT_PATH" ]] && args+=(--vault-path "$VAULT_PATH")
    [[ -n "$LANGUAGE" ]] && args+=(--language "$LANGUAGE")
    [[ "$FORCE" == true ]] && args+=(--force)
    [[ "$SKIP_OBSIDIAN_STYLE" == true ]] && args+=(--skip-obsidian-style)
    [[ "$FORCE_OBSIDIAN_STYLE" == true ]] && args+=(--force-obsidian-style)
    [[ "$SKIP_MCP_SERVER" == true ]] && args+=(--skip-mcp-server)
    [[ "$REPAIR_MCP" == true ]] && args+=(--repair-mcp)
    if [[ ${#args[@]} -gt 0 ]]; then
        printf '%s\n' "${args[@]}"
    fi
}

# ============================================================
# 1. Resolution des chemins
# ============================================================

KIT_ROOT="$(cd "$(dirname "$0")" && pwd)"
_cyan "Racine du kit : $KIT_ROOT"

# --auto-update : tente un git pull --ff-only avant de poursuivre. Si update
# effectif, on relance le script depuis la source mise a jour pour eviter
# de deployer avec une logique deploy.sh obsolete deja chargee en memoire.
if [[ "$AUTO_UPDATE" == true ]]; then
    echo ""
    _cyan "Mode --auto-update : verification des updates remote..."
    if invoke_auto_update "$KIT_ROOT"; then
        _cyan "Re-execution de deploy.sh depuis la source mise a jour..."
        # Recupere les args reconstruits (un par ligne) dans un array.
        readarray -t reexec_args < <(build_reexec_args)
        if [[ ${#reexec_args[@]} -gt 0 ]]; then
            exec "$0" "${reexec_args[@]}"
        else
            exec "$0"
        fi
    fi
fi

# Resolution du VaultPath avec priorites :
#   1. --vault-path explicite            (override utilisateur)
#   2. Installation precedente detectee  (mise a jour)
#   3. Fallback : {kitRoot}/memory       (premiere install en local)

if [[ -n "$VAULT_PATH" ]]; then
    _info "Vault force via --vault-path : $VAULT_PATH"
else
    get_existing_vault_paths
    if [[ ${#EXISTING_VAULTS[@]} -eq 0 ]]; then
        VAULT_PATH="$KIT_ROOT/memory"
        _info "Aucune installation existante detectee. Premiere install : $VAULT_PATH"
    else
        # Extraire les vaults distincts via python3 (evite les pieges bash avec set -u)
        _resolve_result="$(python3 -c "
entries = '''$(printf '%s\n' "${EXISTING_VAULTS[@]}")'''.strip().splitlines()
vaults = {}
sources = []
for e in entries:
    parts = e.split('|')
    src, vault = parts[0], parts[2]
    sources.append(src)
    vaults[vault] = True
if len(vaults) == 1:
    v = list(vaults.keys())[0]
    print('OK|' + ', '.join(sources) + '|' + v)
else:
    print('CONFLICT')
    for e in entries:
        parts = e.split('|')
        print(parts[0] + '|' + parts[2])
")"
        if [[ "$_resolve_result" == OK\|* ]]; then
            _sources="${_resolve_result#OK|}"
            VAULT_PATH="${_sources#*|}"
            _sources="${_sources%%|*}"
            _info "Installation existante detectee ($_sources) : reprise du vault $VAULT_PATH"
        else
            echo ""
            printf '\033[0;33m%s\033[0m\n' "Des vaults differents sont enregistres dans les CLIs :"
            while IFS='|' read -r _src _vlt; do
                [[ "$_src" == "CONFLICT" ]] && continue
                printf '  - %-12s : %s\n' "$_src" "$_vlt"
            done <<< "$_resolve_result"
            echo ""
            echo "Erreur : Impossible de choisir automatiquement. Relance avec --vault-path <chemin>." >&2
            exit 1
        fi
    fi
fi

# Resoudre en chemin absolu
if [[ "$VAULT_PATH" != /* ]]; then
    VAULT_PATH="$(cd "$(dirname "$VAULT_PATH")" 2>/dev/null && pwd)/$(basename "$VAULT_PATH")"
fi

if [[ ! -d "$VAULT_PATH" ]]; then
    echo ""
    echo "Erreur : Vault introuvable : $VAULT_PATH" >&2
    echo "Cree le dossier ou passe --vault-path <chemin>." >&2
    exit 1
fi

_cyan "Vault memoire : $VAULT_PATH"

# Resolution de la langue conversationnelle (param explicite, detection systeme, ou prompt interactif)
LANGUAGE="$(resolve_language "$LANGUAGE")"
_cyan "Langue conversationnelle : $LANGUAGE"

# ============================================================
# 2. Detection des CLI IA
# ============================================================

echo ""
_cyan "Detection des CLI IA..."
echo ""

# Plateformes : nom|affichage|binaire|config_dir|fonction
declare -a PLATFORM_NAMES=("claude-code" "gemini-cli" "codex" "mistral-vibe" "copilot-cli" "antigravity-cli" "antigravity-desktop")
declare -a PLATFORM_DISPLAY=("Claude Code" "Gemini CLI" "Codex (OpenAI)" "Mistral Vibe" "GitHub Copilot CLI" "Antigravity CLI" "Antigravity Desktop")
declare -a PLATFORM_BINARIES=("claude" "gemini" "codex" "vibe" "copilot" "agy" "")
declare -a PLATFORM_CONFIGS=(
    "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    "$HOME/.gemini"
    "$HOME/.codex"
    "$HOME/.vibe"
    "${COPILOT_HOME:-$HOME/.copilot}"
    "$HOME/.gemini/antigravity-cli"
    "$HOME/.gemini/antigravity"
)
declare -a PLATFORM_FUNCS=("deploy_claude_code" "deploy_gemini_cli" "deploy_codex" "deploy_mistral_vibe" "deploy_copilot_cli" "deploy_antigravity_cli" "deploy_antigravity_desktop")

declare -a DETECTED_IDX=()

for i in "${!PLATFORM_NAMES[@]}"; do
    if cli_installed "${PLATFORM_BINARIES[$i]}" "${PLATFORM_CONFIGS[$i]}"; then
        _green "${PLATFORM_DISPLAY[$i]}"
        DETECTED_IDX+=("$i")
    else
        _gray "${PLATFORM_DISPLAY[$i]}"
    fi
done

# ============================================================
# 3. Cas : aucune CLI detectee (message amical)
# ============================================================

if [[ ${#DETECTED_IDX[@]} -eq 0 ]]; then
    echo ""
    printf '\033[0;33m%s\033[0m\n' "Aucune CLI IA detectee sur ce poste."
    echo ""
    printf '\033[0;90m%s\033[0m\n' "Sans CLI IA, un second cerveau pour IA va etre... plutot theorique (haha)."
    echo ""
    printf '\033[0;37m%s\033[0m\n' "Installe au moins une des CLI suivantes, puis relance ce script :"
    _info "Claude Code        : https://claude.com/claude-code"
    _info "Gemini CLI         : https://github.com/google-gemini/gemini-cli"
    _info "Codex              : https://github.com/openai/codex"
    _info "Mistral Vibe       : (voir documentation Mistral AI)"
    _info "GitHub Copilot CLI : https://github.com/github/copilot-cli"
    echo ""
    exit 0
fi

# ============================================================
# 4. Cleanup migration v0.4 -> v0.5 (idempotent)
# ============================================================

echo ""
_cyan "Cleanup migration v0.4 -> v0.5 (skills renommes)..."
remove_deprecated_v04_files

# ============================================================
# 5. Deploiement par plateforme detectee
# ============================================================

declare -a DEPLOYED=()
declare -a PENDING=()

for i in "${DETECTED_IDX[@]}"; do
    local_adapter_dir="$KIT_ROOT/adapters/${PLATFORM_NAMES[$i]}"
    if [[ ! -d "$local_adapter_dir" ]]; then
        echo ""
        _yellow "${PLATFORM_DISPLAY[$i]} : dossier adapter manquant ($local_adapter_dir)"
        PENDING+=("${PLATFORM_DISPLAY[$i]}")
        continue
    fi

    if ${PLATFORM_FUNCS[$i]} "$KIT_ROOT" "${PLATFORM_CONFIGS[$i]}" "$VAULT_PATH"; then
        DEPLOYED+=("${PLATFORM_DISPLAY[$i]}")
    else
        PENDING+=("${PLATFORM_DISPLAY[$i]}")
    fi
done

# ============================================================
# 6. Scaffold du vault si vide (premiere installation)
# ============================================================
# Si le vault ne contient pas la zone canonique 10-episodes/, on considere
# que c'est une premiere install et on appelle scripts/scaffold-vault.py
# pour creer la structure des 9 zones + index.md (i18n via memory-kit.json).

echo ""
if [[ ! -d "$VAULT_PATH/10-episodes" ]]; then
    _cyan "Vault vierge detecte : scaffolding de la structure v0.5..."
    if command -v python3 &>/dev/null; then
        if python3 "$KIT_ROOT/scripts/scaffold-vault.py" --vault "$VAULT_PATH" --language "$LANGUAGE"; then
            :
        else
            _yellow "scaffold-vault.py a echoue (vault partiellement initialise)"
        fi
    else
        _yellow "python3 introuvable : scaffold ignore. Cree manuellement les zones via scripts/scaffold-vault.py."
    fi
else
    _gray "Vault deja peuple (10-episodes/ present), scaffold ignore"
fi

# ============================================================
# 6.5. Deploy-ObsidianStyle (v0.7.2, opt-out via --skip-obsidian-style)
# ============================================================
# Copie les configs canoniques de adapters/obsidian-style/ vers
# {vault}/.obsidian/ avec backup horodate avant ecrasement. Refuse si
# Obsidian est ouvert (sauf --force-obsidian-style). Idempotent.

deploy_obsidian_style() {
    local kit_root="$1"
    local vault_path="$2"
    local force_flag="$3"   # "true" or "false"

    local source_dir="$kit_root/adapters/obsidian-style"
    if [[ ! -d "$source_dir" ]]; then
        _gray "Adapter obsidian-style absent du kit (skip silencieux)"
        return 0
    fi

    _cyan "> Deploiement : Obsidian style (graph palette + assets canoniques)"

    local obsidian_dir="$vault_path/.obsidian"
    if [[ ! -d "$obsidian_dir" ]]; then
        _gray "$obsidian_dir absent — Obsidian n'a pas encore ouvert ce vault. Skip."
        return 0
    fi

    # Detection Obsidian ouvert
    local is_running=false
    if pgrep -x "Obsidian" &>/dev/null || pgrep -f "/obsidian" &>/dev/null; then
        is_running=true
    fi
    local workspace_file="$obsidian_dir/workspace.json"
    if [[ -f "$workspace_file" ]]; then
        local now mtime diff
        now=$(date +%s)
        if mtime=$(stat -c %Y "$workspace_file" 2>/dev/null || stat -f %m "$workspace_file" 2>/dev/null); then
            diff=$((now - mtime))
            if [[ "$diff" -lt 60 ]]; then
                is_running=true
            fi
        fi
    fi

    if [[ "$is_running" == "true" && "$force_flag" != "true" ]]; then
        _yellow "Obsidian semble ouvert ou actif sur $vault_path. Skip pour eviter une corruption."
        echo "  [i]  Fermer Obsidian puis relancer, ou passer --force-obsidian-style pour bypass."
        return 0
    fi

    local stamp
    stamp=$(date +%Y-%m-%d-%H%M%S)
    local f
    # v0.7.3 : recurse dans les sous-dossiers (ex: plugins/obsidian-front-matter-title-plugin/data.json)
    # pour pouvoir patcher les configs des plugins community sans casser la convention "miroir".
    while IFS= read -r -d '' f; do
        local rel_path
        rel_path="${f#$source_dir/}"
        local target="$obsidian_dir/$rel_path"
        local target_parent
        target_parent="$(dirname "$target")"
        mkdir -p "$target_parent"
        local fname
        fname="$(basename "$f")"
        local src_content target_content
        src_content=$(cat "$f")
        if [[ ! -e "$target" ]]; then
            printf '%s' "$src_content" > "$target"
            _green "Ecrit (nouveau) : .obsidian/$rel_path"
            continue
        fi
        target_content=$(cat "$target")
        if [[ "$src_content" == "$target_content" ]]; then
            _gray ".obsidian/$rel_path — identique a la version canonique"
            continue
        fi
        # Cible existe et differe : marker canonique present -> backup + ecrase, sinon skip (personnalisation user)
        if grep -q '"_secondbrain_canonical"\s*:' "$target" 2>/dev/null; then
            cp "$target" "$target.bak-pre-style-$stamp"
            printf '%s' "$src_content" > "$target"
            _green "Mis a jour : .obsidian/$rel_path (backup -> $fname.bak-pre-style-$stamp)"
        else
            _gray ".obsidian/$rel_path — personnalise par l'utilisateur (pas de marker canonique). Pas touche."
            echo "  [i]    Pour reapppliquer la version canonique, supprimer manuellement la cible et relancer."
        fi
    done < <(find "$source_dir" -type f -name '*.json' -print0)
}

if [[ "$SKIP_OBSIDIAN_STYLE" != "true" ]]; then
    echo ""
    deploy_obsidian_style "$KIT_ROOT" "$VAULT_PATH" "${FORCE_OBSIDIAN_STYLE:-false}"
fi

# ============================================================
# 6.6. Deploy-McpServer (v0.8.0, opt-out via --skip-mcp-server)
# ============================================================

if [[ "$SKIP_MCP_SERVER" != "true" ]]; then
    deploy_mcp_server "$KIT_ROOT" "$VAULT_PATH" "$REPAIR_MCP"
fi

# ============================================================
# 6.6.5. sync_local_venv (v0.10.x) -- alignement venv dev sur pyproject
# ============================================================
# Le venv local mcp-server/.venv/ (utilise pour pytest et la CLI standalone
# en dev) peut diverger de pyproject.toml apres un bump si le dev oublie de
# rerun pip install -e .. Resultat : __version__ stale dans toutes les
# sorties de la CLI standalone (atomes archeo, mem_check_update, etc.).
# Cette etape detecte le drift et reinstalle silencieusement. Skip si pas
# de venv local (cas user standard).

if [[ "$SKIP_MCP_SERVER" != "true" ]]; then
    sync_local_venv "$KIT_ROOT"
fi

# ============================================================
# 6.7. Vault schema migrations (v0.9.4, opt-out via --skip-mcp-server)
# ============================================================
# Detect pending vault schema migrations and run them automatically.
# Idempotent: a vault already on the target schema version is skipped.
# An auto-backup is taken before any apply (capped at 500 MiB; user must
# pass --skip-backup if their vault is bigger).

if [[ "$SKIP_MCP_SERVER" != "true" ]]; then
    echo ""
    printf '\033[0;36m%s\033[0m\n' "Vault schema migrations..."

    # Resolve the migrate command (entry-point installed by pipx).
    # Priority: memory-kit-migrate on PATH, then {pipx-bin-dir}/memory-kit-migrate
    MIGRATE_CMD=""
    if command -v memory-kit-migrate >/dev/null 2>&1; then
        MIGRATE_CMD="memory-kit-migrate"
    elif command -v pipx >/dev/null 2>&1; then
        PIPX_BIN_DIR="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || true)"
        if [[ -n "$PIPX_BIN_DIR" && -x "$PIPX_BIN_DIR/memory-kit-migrate" ]]; then
            MIGRATE_CMD="$PIPX_BIN_DIR/memory-kit-migrate"
        fi
    fi

    if [[ -n "$MIGRATE_CMD" ]]; then
        MIGRATE_DRY="$($MIGRATE_CMD --quiet 2>&1)" || true
        if [[ "$MIGRATE_DRY" =~ "No pending migrations" ]] || [[ "$MIGRATE_DRY" =~ "Nothing to migrate" ]]; then
            printf '  \033[0;90m[--] %s\033[0m\n' "Vault schema already up to date."
        else
            printf '  \033[0;36m[i]  %s\033[0m\n' "Pending migrations detected — applying with auto-backup..."
            if "$MIGRATE_CMD" --apply; then
                printf '  \033[0;32m[OK] %s\033[0m\n' "Vault migrations applied successfully."
            else
                printf '  \033[1;33m[!]  %s\033[0m\n' "Migration failed. Check the output above. Backup is preserved under ~/.memory-kit/backups/."
            fi
        fi
    else
        printf '  \033[0;90m[--] %s\033[0m\n' "memory-kit-migrate not found (pipx package not installed yet?). Run manually: memory-kit-migrate --apply"
    fi
fi

# ============================================================
# 7. Resume final
# ============================================================

echo ""
printf '\033[0;35m%s\033[0m\n' "=== Deploiement termine ==="
echo "Vault : $VAULT_PATH"
if [[ ${#DEPLOYED[@]} -gt 0 ]]; then
    printf '\033[0;32mDeploye    : %s\033[0m\n' "$(IFS=', '; echo "${DEPLOYED[*]}")"
fi
if [[ ${#PENDING[@]} -gt 0 ]]; then
    printf '\033[0;33mEn attente : %s (adapter a implementer)\033[0m\n' "$(IFS=', '; echo "${PENDING[*]}")"
fi
echo ""
if [[ ${#DEPLOYED[@]} -gt 0 ]]; then
    _cyan "Test :"
    for d in "${DEPLOYED[@]}"; do
        case "$d" in
            "Claude Code")        _cyan "  [Claude Code]        /mem-recall (dans une nouvelle session)" ;;
            "Gemini CLI")         _cyan "  [Gemini CLI]         /mem-recall (dans une nouvelle session)" ;;
            "Codex (OpenAI)")     _cyan "  [Codex]              /mem-recall (dans une nouvelle session)" ;;
            "Mistral Vibe")       _cyan "  [Mistral Vibe]       dis 'charge mon contexte memoire' (Vibe expose le MCP secondbrain-memory-kit + skills mais pas de slash commands)" ;;
            "GitHub Copilot CLI") _cyan "  [Copilot CLI]        /mem-recall (dans une nouvelle session)" ;;
        esac
    done
fi
