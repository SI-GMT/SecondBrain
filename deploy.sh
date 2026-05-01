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

# ============================================================
# Parsing des arguments
# ============================================================

VAULT_PATH=""
LANGUAGE=""
FORCE=false
SKIP_OBSIDIAN_STYLE=false
FORCE_OBSIDIAN_STYLE=false

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
        -h|--help)
            echo "Usage : $0 [--vault-path <chemin>] [--language en|fr|es|de|ru] [--force] [--skip-obsidian-style] [--force-obsidian-style]"
            echo ""
            echo "  --vault-path             Chemin absolu du vault memoire (defaut : auto-detection puis <racine du kit>/memory)"
            echo "  --language               Langue conversationnelle du LLM (defaut : detection systeme puis prompt)"
            echo "  --force                  Ecrase memory-kit.json meme s'il existe deja"
            echo "  --skip-obsidian-style    Ne deploie pas les configs canoniques Obsidian (graph palette)"
            echo "  --force-obsidian-style   Force le deploy Obsidian style meme si Obsidian semble ouvert"
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
# Assemblage d'une procedure core (resolution {{INCLUDE _bloc}} + {{CONFIG_FILE}})
# ============================================================
# Une procedure peut inclure des blocs reutilisables (encoding, concurrence,
# router, frontmatter-universel...) via {{INCLUDE _nom}}. Resolution recursive
# avec profondeur max 5 pour eviter les cycles.
#
# Args  : <procedure_path> <core_root> <config_file_ref>
# Stdout: contenu assemble (procedure + blocs inclus + CONFIG_FILE substitue)
# Exit  : 1 si bloc introuvable ou cycle detecte.

assemble_procedure() {
    local proc_path="$1"
    local core_root="$2"
    local config_file_ref="$3"
    python3 - "$proc_path" "$core_root" "$config_file_ref" << 'PYEOF'
import re, sys
from pathlib import Path

proc_path = Path(sys.argv[1])
core_root = Path(sys.argv[2])
config_file_ref = sys.argv[3]

INCLUDE_RE = re.compile(r'\{\{INCLUDE\s+(_\w+)\}\}')

def resolve(content, depth=0):
    if depth > 5:
        sys.stderr.write("Profondeur maximale d'inclusion depassee (5). Cycle suspecte.\n")
        sys.exit(1)
    def repl(match):
        name = match.group(1)
        path = core_root / f"{name}.md"
        if not path.exists():
            sys.stderr.write(f"Bloc d'inclusion introuvable : {{{{INCLUDE {name}}}}} -> {path}\n")
            sys.exit(1)
        return resolve(path.read_text(encoding='utf-8'), depth + 1)
    return INCLUDE_RE.sub(repl, content)

content = proc_path.read_text(encoding='utf-8')
content = resolve(content)
content = content.replace('{{CONFIG_FILE}}', config_file_ref)
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
    # Prompt si shell interactif
    if [[ -t 0 && -t 1 ]]; then
        echo "" >&2
        _cyan "Conversational language for the LLM (the vault structure stays English)" >&2
        printf '\033[0;90m  Supported: %s\033[0m\n' "${supported[*]}" >&2
        printf '  Choose language [%s]: ' "$detected" >&2
        local input
        read -r input
        if [[ -n "$input" ]]; then
            input="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
            for s in "${supported[@]}"; do
                if [[ "$s" == "$input" ]]; then
                    echo "$input"
                    return 0
                fi
            done
            _yellow "Unknown language '$input', falling back to '$detected'" >&2
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
    local sources=(
        "Claude Code|$claude_config/memory-kit.json"
        "Gemini CLI|$HOME/.gemini/memory-kit.json"
        "Codex|$HOME/.codex/memory-kit.json"
    )

    EXISTING_VAULTS=()
    for entry in "${sources[@]}"; do
        local source="${entry%%|*}"
        local config_file="${entry#*|}"
        [[ -f "$config_file" ]] || continue
        if command -v python3 &>/dev/null; then
            local vault
            vault="$(python3 -c "
import json, sys
try:
    with open('$config_file') as f:
        c = json.load(f)
    v = c.get('vault', '')
    if v:
        print(v)
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
        procedure_content="$(assemble_procedure "$procedure_path" "$core_source" "$config_file_ref")" || {
            _yellow "Echec assemblage procedure $skill_name (ignore)"
            continue
        }
        local template_content
        template_content="$(cat "$tpl")"
        local assembled="${template_content//\{\{PROCEDURE\}\}/$procedure_content}"
        printf '%s' "$assembled" > "$skills_target/$skill_name.md"
        _green "Skill   : $skill_name.md"
    done

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
# appellent mv/rm. On autorise les patterns Bash correspondants.
allow = perms.setdefault('allow', [])
mem_patterns = [
    'Bash(mv *)',
    'Bash(rm *)',
    'Bash(mv:*)',
    'Bash(rm:*)',
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
        procedure_content="$(assemble_procedure "$procedure_path" "$core_source" "$config_file_ref")" || {
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
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref")" || {
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
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref")" || {
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
            proc="$(assemble_procedure "$proc_path" "$core_source" "$config_file_ref")" || {
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
# 1. Resolution des chemins
# ============================================================

KIT_ROOT="$(cd "$(dirname "$0")" && pwd)"
_cyan "Racine du kit : $KIT_ROOT"

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
declare -a PLATFORM_NAMES=("claude-code" "gemini-cli" "codex" "mistral-vibe")
declare -a PLATFORM_DISPLAY=("Claude Code" "Gemini CLI" "Codex (OpenAI)" "Mistral Vibe")
declare -a PLATFORM_BINARIES=("claude" "gemini" "codex" "vibe")
declare -a PLATFORM_CONFIGS=(
    "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    "$HOME/.gemini"
    "$HOME/.codex"
    "$HOME/.vibe"
)
declare -a PLATFORM_FUNCS=("deploy_claude_code" "deploy_gemini_cli" "deploy_codex" "deploy_mistral_vibe")

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
    _info "Claude Code  : https://claude.com/claude-code"
    _info "Gemini CLI   : https://github.com/google-gemini/gemini-cli"
    _info "Codex        : https://github.com/openai/codex"
    _info "Mistral Vibe : (voir documentation Mistral AI)"
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
    for f in "$source_dir"/*.json; do
        [[ -e "$f" ]] || continue
        local fname
        fname=$(basename "$f")
        local target="$obsidian_dir/$fname"
        local src_content target_content
        src_content=$(cat "$f")
        if [[ ! -e "$target" ]]; then
            printf '%s' "$src_content" > "$target"
            _green "Ecrit (nouveau) : .obsidian/$fname"
            continue
        fi
        target_content=$(cat "$target")
        if [[ "$src_content" == "$target_content" ]]; then
            _gray ".obsidian/$fname — identique a la version canonique"
            continue
        fi
        # Cible existe et differe : marker canonique present -> backup + ecrase, sinon skip (personnalisation user)
        if grep -q '"_secondbrain_canonical"\s*:' "$target" 2>/dev/null; then
            cp "$target" "$target.bak-pre-style-$stamp"
            printf '%s' "$src_content" > "$target"
            _green "Mis a jour : .obsidian/$fname (backup -> $fname.bak-pre-style-$stamp)"
        else
            _gray ".obsidian/$fname — personnalise par l'utilisateur (pas de marker canonique). Pas touche."
            echo "  [i]    Pour reapppliquer la version canonique, supprimer manuellement la cible et relancer."
        fi
    done
}

if [[ "$SKIP_OBSIDIAN_STYLE" != "true" ]]; then
    echo ""
    deploy_obsidian_style "$KIT_ROOT" "$VAULT_PATH" "${FORCE_OBSIDIAN_STYLE:-false}"
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
            "Claude Code")    _cyan "  [Claude Code]  /mem-recall (dans une nouvelle session)" ;;
            "Gemini CLI")     _cyan "  [Gemini CLI]   /mem-recall (dans une nouvelle session)" ;;
            "Codex (OpenAI)") _cyan "  [Codex]        /mem-recall (dans une nouvelle session)" ;;
            "Mistral Vibe")   _cyan "  [Mistral Vibe] dis 'charge mon contexte memoire' (dans une nouvelle session)" ;;
        esac
    done
fi
