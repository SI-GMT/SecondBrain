# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Nature du dépôt

**SecondBrain — dépôt de développement.** Ce dossier contient le code source d'un kit qui donne aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) une mémoire persistante entre les sessions via un vault Markdown (visualisable avec Obsidian). Ce n'est **pas** un projet où on prend des notes — c'est le kit lui-même.

Langue de travail : **français** (code, commentaires, messages, procédures). Accents complets, pas d'ASCII volontaire.

## Architecture

```
core/procedures/              ← spec procédurale canonique, agnostique LLM
adapters/                     ← traductions vers chaque plateforme
  claude-code/
    skills/*.template.md      ← frontmatter + {{PROCEDURE}} (placeholder)
    commands/*.md             ← slash commands user-facing (shims vers skills)
    claude-md-block.md        ← bloc injecté dans ~/.claude/CLAUDE.md
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core et installe dans ~/.claude/
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter — `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique — pas qu'il faut la forker.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` — c'est la source de vérité.
2. Éditer le frontmatter dans `adapters/claude-code/skills/mem-{nom}.template.md` si le champ `description` doit changer (il contrôle le déclenchement automatique par Claude).
3. Éditer le shim dans `adapters/claude-code/commands/mem-{nom}.md` si l'invocation user-facing change.
4. Lancer `.\deploy.ps1` pour pousser vers `~/.claude/`.
5. Tester en tapant `/mem-{nom}` dans n'importe quelle session Claude Code.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Ajouter un nouvel adapter (Gemini CLI, Codex, MCP)

Créer `adapters/{plateforme}/` avec la structure propre à cette plateforme, puis étendre `deploy.ps1` pour détecter l'installation de la plateforme et y déployer. **Ne jamais modifier `core/`** pour accommoder une plateforme — `core/` reste neutre.

Phase 3 prévue : extraire la logique dans un serveur MCP `memory-kit`. Les adapters deviendront alors des thin wrappers qui délèguent au MCP ; une seule implémentation, tous les LLM compatibles.

### Gemini CLI : TOML literal strings (`'''`) pour `prompt`

Les templates `adapters/gemini-cli/commands/*.template.toml` doivent utiliser `prompt = '''...'''` (literal multi-line string), **jamais** `"""..."""` (basic multi-line string). Le Markdown des procédures `core/` contient des backslashes (`\/:*?"<>|`, regex, exemples de code Python/PowerShell) qui ne sont pas des séquences d'échappement TOML valides et cassent le parser Gemini (`FileCommandLoader: Failed to parse TOML`). Les literal strings ne processent rien — texte brut.

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `_index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, **immuables** (un par session complète)
- `projets/{nom}/contexte.md` — snapshot mutable du projet
- `projets/{nom}/historique.md` — fil chronologique avec liens vers les archives
- `.obsidian/` — config Obsidian (créée automatiquement à l'ouverture du vault par Obsidian)

**Fichiers Obsidian spéciaux** dans `memory/` : `.excalidraw.md`, `.canvas`, `.base` — ne pas éditer avec `Edit`/`Write`, passer par Obsidian.

## Conventions de déploiement

- Le script détecte automatiquement `$env:CLAUDE_CONFIG_DIR` puis `$HOME/.claude` — **jamais de chemin en dur** dans les fichiers à distribuer.
- Le chemin du vault est écrit dans `~/.claude/memory-kit.json` à l'installation, lu par les skills à l'exécution. Chaque poste a son propre chemin local.
- Le bloc injecté dans `~/.claude/CLAUDE.md` est délimité par `<!-- MEMORY-KIT:START -->` et `<!-- MEMORY-KIT:END -->` — idempotent, préserve le reste du contenu utilisateur.
- Le chemin du vault est ajouté à `permissions.additionalDirectories` dans `~/.claude/settings.json` (parse JSON → merge → réécrit). Idempotent ; le reste des settings est préservé. Indentation et ordre des clés peuvent changer au premier passage (coût normal d'un round-trip JSON via PowerShell).
