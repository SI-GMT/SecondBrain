# GEMINI.md

Ce fichier fournit des conseils à la Gemini CLI lorsqu'elle travaille sur le code de ce dépôt.

## Nature du dépôt

**SecondBrain — dépôt de développement.** Ce dossier contient le code source d'un kit qui donne aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) une mémoire persistante entre les sessions via un vault Markdown (visualisable avec Obsidian). Ce n'est **pas** un projet où on prend des notes — c'est le kit lui-même.

Langue de travail : **français** (code, commentaires, messages, procédures). Accents complets, pas d'ASCII volontaire.

## Architecture

```
core/procedures/              ← spec procédurale canonique, agnostique LLM
adapters/                     ← traductions vers chaque plateforme
  gemini-cli/
    commands/*.template.toml  ← frontmatter + {{PROCEDURE}} (placeholder)
    gemini-extension.json     ← manifeste de l'extension Gemini
    GEMINI.md                 ← bloc injecté dans ~/.gemini/extensions/memory-kit/GEMINI.md
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core et installe dans ~/.gemini/
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter — `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique — pas qu'il faut la forker.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` — c'est la source de vérité.
2. Éditer le frontmatter dans `adapters/gemini-cli/commands/mem-{nom}.template.toml` si le champ `description` doit changer (il contrôle le déclenchement automatique par Gemini).
3. Lancer `.\deploy.ps1` pour pousser vers `~/.gemini/extensions/memory-kit/`.
4. Tester en tapant `/mem-{nom}` dans n'importe quelle session Gemini CLI.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Spécificités Gemini CLI

- L'extension est installée dans `~/.gemini/extensions/memory-kit/`.
- Le fichier `gemini-extension.json` définit le nom et la version de l'extension.
- Les commandes sont définies dans des fichiers `.toml` qui sont interprétés par la CLI.
- Le fichier `GEMINI.md` de l'extension contient les instructions de base pour le déclenchement automatique via langage naturel.

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `_index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, **immuables** (un par session complète)
- `projets/{nom}/contexte.md` — snapshot mutable du projet
- `projets/{nom}/historique.md` — fil chronologique avec liens vers les archives

**Note importante** : Pour les opérations sur le vault (souvent situé hors du workspace), utiliser `run_shell_command` avec des commandes PowerShell (`cat`, `ls`, `mkdir`, etc.).

## Conventions de déploiement

- Le script détecte automatiquement `$HOME/.gemini` — **jamais de chemin en dur** dans les fichiers à distribuer.
- Le chemin du vault est écrit dans `~/.gemini/memory-kit.json` à l'installation, lu par les commandes à l'exécution.
- L'extension est activée via `~/.gemini/extension-enablement.json`.
