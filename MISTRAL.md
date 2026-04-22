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
    instructions-block.md     ← bloc injecté dans ~/.vibe/AGENTS.md
    skills/*/SKILL.md.template ← skills user-invocables (auto-découverts)
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core et installe dans ~/.vibe/
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter — `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique — pas qu'il faut la forker.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` — c'est la source de vérité.
2. Éditer le frontmatter (`description`, `user-invocable`) dans `adapters/mistral-vibe/skills/mem-{nom}/SKILL.md.template` si le champ de trigger automatique doit changer.
3. Éditer `adapters/mistral-vibe/instructions-block.md` si le bloc injecté dans `~/.vibe/AGENTS.md` doit changer (règle d'or, cheat sheet bash, liste des skills, anti-drift).
4. Lancer `.\deploy.ps1` pour pousser vers `~/.vibe/`.
5. Tester dans une nouvelle session Vibe — soit par trigger naturel (« reprends », « on s'arrête »), soit par invocation explicite `/mem-{nom}`.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `_index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, **immuables** (un par session complète)
- `projets/{nom}/contexte.md` — snapshot mutable du projet
- `projets/{nom}/historique.md` — fil chronologique avec liens vers les archives
- `.obsidian/` — config Obsidian (créée automatiquement à l'ouverture du vault par Obsidian)

**Fichiers Obsidian spéciaux** dans `memory/` : `.excalidraw.md`, `.canvas`, `.base` — ne pas éditer avec des opérations texte brutes, passer par Obsidian.

## Conventions de déploiement

- `deploy.ps1` détecte automatiquement `$HOME/.vibe` — **jamais de chemin en dur** dans les fichiers à distribuer.
- Contrairement aux autres adapters, Mistral Vibe n'a pas de fichier `memory-kit.json` runtime. Le chemin du vault est substitué directement dans le bloc `instructions-block.md` au moment du déploiement (remplacement de `{{VAULT_PATH}}` par le chemin absolu).
- Le bloc injecté dans `~/.vibe/AGENTS.md` est délimité par `<!-- MEMORY-KIT:START -->` et `<!-- MEMORY-KIT:END -->` — idempotent, préserve le reste du contenu utilisateur.
- Les skills sont assemblés dans `~/.vibe/skills/mem-{nom}/SKILL.md` (template + `{{PROCEDURE}}` substituée).

## Spécificités Mistral Vibe

- Vibe charge `~/.vibe/AGENTS.md` comme user-level instructions à chaque session (confirmé par `vibe/core/system_prompt.py`). C'est le vrai point d'injection des règles permanentes — **pas** `~/.vibe/instructions.md` (fichier sans rôle côté Vibe malgré son nom).
- Vibe auto-découvre les skills dans `~/.vibe/skills/{nom}/SKILL.md` — même format qu'Anthropic et Codex (frontmatter YAML + corps de procédure). Le champ `user-invocable: true` expose le skill au déclenchement utilisateur (langage naturel + commande).
- Pour toute opération sur le vault, **privilégier l'outil `bash` avec chemin absolu** plutôt que `read_file`/`write_file` — les tools de fichiers de Vibe peuvent être sandboxés sur le cwd et refuser un chemin absolu externe. `bash` contourne cette limite.
