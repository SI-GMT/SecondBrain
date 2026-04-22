# MISTRAL.md

This file provides guidance to Mistral Vibe when working with code in this repository.

## Nature du dépôt

**SecondBrain — dépôt de développement.** Ce dossier contient le code source d'un kit qui donne aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) une mémoire persistante entre les sessions via un vault Markdown (visualisable avec Obsidian). Ce n'est **pas** un projet où on prend des notes — c'est le kit lui-même.

Langue de travail : **français** (code, commentaires, messages, procédures). Accents complets, pas d'ASCII volontaire.

## Architecture

```
core/procedures/              ← spec procédurale canonique, agnostique LLM
adapters/                     ← traductions vers chaque plateforme
  mistral-vibe/
    instructions-block.md     ← bloc injecté dans ~/.vibe/instructions.md
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core et installe dans ~/.vibe/
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter — `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique — pas qu'il faut la forker.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` — c'est la source de vérité.
2. Éditer `adapters/mistral-vibe/instructions-block.md` si le bloc d'instructions injecté dans `~/.vibe/instructions.md` doit changer (formulation des triggers naturels, description des skills).
3. Lancer `.\deploy.ps1` pour pousser vers `~/.vibe/`.
4. Tester dans une session Mistral Vibe en formulant un trigger naturel (« on reprend le projet X », « on s'arrête », etc.) — Vibe n'expose pas de slash commands, tout passe par le langage naturel + le tool use.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Ajouter un nouvel adapter

Créer `adapters/{plateforme}/` avec la structure propre à cette plateforme, puis étendre `deploy.ps1` pour détecter l'installation de la plateforme et y déployer. **Ne jamais modifier `core/`** pour accommoder une plateforme — `core/` reste neutre.

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `_index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, **immuables** (un par session complète)
- `projets/{nom}/contexte.md` — snapshot mutable du projet
- `projets/{nom}/historique.md` — fil chronologique avec liens vers les archives
- `.obsidian/` — config Obsidian (créée automatiquement à l'ouverture du vault par Obsidian)

**Fichiers Obsidian spéciaux** dans `memory/` : `.excalidraw.md`, `.canvas`, `.base` — ne pas éditer avec des opérations texte brutes, passer par Obsidian.

## Conventions de déploiement

- Le script détecte automatiquement `$HOME/.vibe` — **jamais de chemin en dur** dans les fichiers à distribuer.
- Contrairement aux autres adapters, Mistral Vibe n'a pas de fichier `memory-kit.json` dédié : le chemin du vault est injecté directement dans le bloc d'instructions.
- Le bloc injecté dans `~/.vibe/instructions.md` est délimité par `<!-- MEMORY-KIT:START -->` et `<!-- MEMORY-KIT:END -->` — idempotent, préserve le reste du contenu utilisateur.

## Spécificités Mistral Vibe

Mistral Vibe n'expose pas de slash commands user-level. Tout passe par :

- **Les instructions globales** dans `~/.vibe/instructions.md` (bloc MEMORY-KIT injecté par `deploy.ps1`).
- **Le tool use** : les opérations sur le vault passent par `read_file`, `write_file`, `search_replace`, `bash` selon les besoins de la procédure.
- **Le déclenchement par langage naturel** : « on reprend le projet X » → `mem-recall`, « on s'arrête pour aujourd'hui » → `mem-archive` en mode complet, etc. Les mappings exacts sont documentés dans `adapters/mistral-vibe/instructions-block.md`.
