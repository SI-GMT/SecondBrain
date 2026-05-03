# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Nature du dépôt

**SecondBrain — dépôt de développement.** Ce dossier contient le code source d'un kit qui donne aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe, GitHub Copilot CLI) une mémoire persistante entre les sessions via un vault Markdown (visualisable avec Obsidian). Ce n'est **pas** un projet où on prend des notes — c'est le kit lui-même.

Langue de travail : **français** (code, commentaires, messages, procédures). Accents complets, pas d'ASCII volontaire.

## Architecture

```
core/procedures/              ← spec procédurale canonique, agnostique LLM
                                (inclut _mcp-first.md depuis v0.8.0)
adapters/                     ← traductions vers chaque plateforme
  claude-code/
    skills/*.template.md      ← frontmatter + {{PROCEDURE}} (placeholder)
    commands/*.md             ← slash commands user-facing (shims vers skills)
    claude-md-block.md        ← bloc injecté dans ~/.claude/CLAUDE.md
mcp-server/                   ← serveur MCP Python (v0.8.0)
  pyproject.toml              ← hatchling + fastmcp ≥2.13 + Pydantic v2
  src/memory_kit_mcp/
    server.py                 ← FastMCP instance + main() entry stdio
    config.py                 ← lit ~/.memory-kit/config.json
    tools/X.py                ← 24 outils mem_X (1-pour-1 avec les skills)
    vault/                    ← primitives partagées (paths, frontmatter,
                                atomic_io UTF-8/LF/hash, scanner)
  tests/                      ← pytest, 114 tests, 94% coverage via
                                fastmcp.Client in-memory
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core, installe dans ~/.claude/,
                                installe le serveur MCP via pipx, inject la
                                déclaration MCP dans 7 cibles compatibles
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter — `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique — pas qu'il faut la forker.

**Depuis v0.8.0 (Phase 3 MCP)** : la procédure `core/procedures/mem-X.md` reste la **source de vérité fonctionnelle** et a maintenant un double emploi :
- Lue par les LLM en mode **skills fallback** (CLI sans MCP, ou serveur indisponible).
- Spec d'implémentation pour le module Python `mcp-server/src/memory_kit_mcp/tools/X.py` qui expose la logique comme outil MCP.

Discipline de cohérence : tout changement dans une procédure doit s'accompagner d'un changement dans le module Python correspondant (et vice-versa) dans le même commit. Le bloc `_mcp-first.md` est prepended automatiquement par `deploy.ps1` au-dessus de chaque procédure résolue ; il indique au LLM d'invoquer `mcp__secondbrain-memory-kit__mem_X` si disponible, sinon d'exécuter la procédure ci-dessous.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` — c'est la source de vérité.
2. Éditer le frontmatter dans `adapters/claude-code/skills/mem-{nom}.template.md` si le champ `description` doit changer (il contrôle le déclenchement automatique par Claude).
3. Éditer le shim dans `adapters/claude-code/commands/mem-{nom}.md` si l'invocation user-facing change.
4. Lancer `.\deploy.ps1` pour pousser vers `~/.claude/`.
5. Tester en tapant `/mem-{nom}` dans n'importe quelle session Claude Code.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Discipline de cohérence `deploy.ps1` ↔ `deploy.sh`

Le kit fournit deux scripts de déploiement jumeaux : `deploy.ps1` (PowerShell, cible Windows native) et `deploy.sh` (Bash, cible macOS/Linux et Git Bash sur Windows). Tout ajout ou modification dans l'un doit être co-commité dans l'autre — même comportement, mêmes flags, mêmes patterns d'idempotence. Si un comportement diverge, c'est généralement justifié par la plateforme cible (ex : patterns `allow` `settings.json` PowerShell-style côté `.ps1`, Bash-style côté `.sh`) — documenter la divergence en commentaire dans les deux scripts.

Limitation connue de `deploy.sh` sous Git Bash Windows : les heredocs Python utilisent `python` natif Windows qui ne traduit pas les chemins MSYS (`/tmp/...` côté shell vs `C:\...` côté Python). Pas un blocker en production : la cible primaire de `deploy.sh` est macOS/Linux où shell et Python partagent la même vision filesystem.

## Ajouter un nouvel adapter (Gemini CLI, Codex, Copilot CLI, etc.)

Créer `adapters/{plateforme}/` avec la structure propre à cette plateforme, puis étendre **les deux scripts de déploiement** (`deploy.ps1` et `deploy.sh`) pour détecter l'installation de la plateforme et y déployer. **Ne jamais modifier `core/`** pour accommoder une plateforme — `core/` reste neutre.

## Ajouter un nouvel outil MCP

Pour qu'un nouveau skill `mem-Y` apparaisse aussi côté MCP server :
1. Créer `mcp-server/src/memory_kit_mcp/tools/Y.py` avec une fonction `register(mcp)` qui définit `@mcp.tool() def mem_Y(...) -> ResultModel`.
2. Étendre `tools/__init__.py` pour importer + appeler `Y.register(mcp)`.
3. Ajouter le test correspondant dans `tests/test_Y.py` (utilise la fixture `client` de `conftest.py` qui pointe sur un vault temporaire).
4. Tourner `pytest --cov-fail-under=80` pour vérifier.
5. Vérifier que `core/procedures/mem-Y.md` décrit fonctionnellement le même comportement (source de vérité).

## Ajouter une nouvelle cible MCP (CLI ou app desktop)

Si une nouvelle CLI/app supporte MCP via un fichier de config dédié, étendre `Deploy-McpServer` dans `deploy.ps1` **et** `deploy_mcp_server` dans `deploy.sh` :
- Si format JSON `{"mcpServers": {...}}` (pattern Claude Code, Copilot CLI, Claude Desktop, Gemini CLI), réutiliser `Add-McpServerToJsonConfig` / `add_mcp_server_to_json_config`.
- Si format TOML `[mcp_servers.X]` (Codex), réutiliser `Add-McpServerToTomlConfig` / `add_mcp_server_to_toml_config`.
- Si format TOML `[[mcp_servers]]` (Vibe), réutiliser `Add-McpServerToVibeTomlConfig` / `add_mcp_server_to_vibe_toml_config`.
- Si format différent : créer une nouvelle fonction sur le même pattern (markers idempotents) dans les deux scripts.

### Gemini CLI : TOML literal strings (`'''`) pour `prompt`

Les templates `adapters/gemini-cli/commands/*.template.toml` doivent utiliser `prompt = '''...'''` (literal multi-line string), **jamais** `"""..."""` (basic multi-line string). Le Markdown des procédures `core/` contient des backslashes (`\/:*?"<>|`, regex, exemples de code Python/PowerShell) qui ne sont pas des séquences d'échappement TOML valides et cassent le parser Gemini (`FileCommandLoader: Failed to parse TOML`). Les literal strings ne processent rien — texte brut.

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, **immuables** (un par session complète)
- `projets/{nom}/context.md` — snapshot mutable du projet
- `projets/{nom}/history.md` — fil chronologique avec liens vers les archives
- `.obsidian/` — config Obsidian (créée automatiquement à l'ouverture du vault par Obsidian)

**Fichiers Obsidian spéciaux** dans `memory/` : `.excalidraw.md`, `.canvas`, `.base` — ne pas éditer avec `Edit`/`Write`, passer par Obsidian.

## Conventions de déploiement

- Le script détecte automatiquement `$env:CLAUDE_CONFIG_DIR` puis `$HOME/.claude` — **jamais de chemin en dur** dans les fichiers à distribuer.
- Le chemin du vault est écrit dans `~/.claude/memory-kit.json` à l'installation, lu par les skills à l'exécution. Chaque poste a son propre chemin local.
- Le bloc injecté dans `~/.claude/CLAUDE.md` est délimité par `<!-- MEMORY-KIT:START -->` et `<!-- MEMORY-KIT:END -->` — idempotent, préserve le reste du contenu utilisateur.
- Le chemin du vault est ajouté à `permissions.additionalDirectories` dans `~/.claude/settings.json` (parse JSON → merge → réécrit). Idempotent ; le reste des settings est préservé. Indentation et ordre des clés peuvent changer au premier passage (coût normal d'un round-trip JSON via PowerShell).
