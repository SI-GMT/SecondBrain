# AGENTS.md

This file provides guidance to Codex/GPT agents when working with code in this repository.

## Nature du dépôt

**SecondBrain — dépôt de développement.** Ce dossier contient le code source d'un kit qui donne aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) une mémoire persistante entre les sessions via un vault Markdown (visualisable avec Obsidian). Ce n'est **pas** un projet où on prend des notes ; c'est le kit lui-même.

Langue de travail : **français** (code, commentaires, messages, procédures). Accents complets, pas d'ASCII volontaire.

## Architecture

```text
core/procedures/              ← spec procédurale canonique, agnostique LLM
adapters/                     ← traductions vers chaque plateforme
  codex/
    prompts/*.template.md     ← prompts user-level assemblés au déploiement
    skills/*/SKILL.md.template← skills assemblés au déploiement
memory/                       ← vault Obsidian local (non versionné avec le kit)
deploy.ps1                    ← assemble adapters + core et installe dans ~/.codex/
```

## Règle d'or : single source of truth

Toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. **Ne jamais dupliquer la procédure** dans un adapter ; `deploy.ps1` la compose à la volée en substituant `{{PROCEDURE}}` par le contenu du fichier core correspondant.

Si une procédure doit diverger entre plateformes, c'est le signe qu'il manque un paramètre ou une généralisation dans la spec canonique, pas qu'il faut la forker.

## Workflow de développement

1. Éditer la procédure dans `core/procedures/mem-{nom}.md` : c'est la source de vérité.
2. Éditer le template Codex dans `adapters/codex/skills/mem-{nom}/SKILL.md.template` si le champ `description` doit changer.
3. Éditer le prompt user-level dans `adapters/codex/prompts/mem-{nom}.template.md` si l'invocation explicite ou le cadrage du prompt doit changer.
4. Lancer `.\deploy.ps1` pour pousser vers `~/.codex/`.
5. Tester dans Codex avec `/mem-{nom}` ou via le déclenchement naturel quand le skill le prévoit.

Commandes disponibles : `mem-archive`, `mem-recall` (cycle session) + `mem-list-projects`, `mem-search`, `mem-rename-project`, `mem-merge-projects`, `mem-digest`, `mem-rollback-archive` (gestion du vault).

## Ajouter ou faire évoluer l'adapter Codex

L'adapter Codex repose sur deux surfaces :

- `prompts/` pour les commandes explicites côté utilisateur.
- `skills/` pour le déclenchement contextuel et la procédure détaillée.

Si un comportement manque côté Codex, corriger d'abord `core/`, puis adapter le template `prompts/` ou `skills/` concerné. **Ne pas contourner `core/` avec une logique locale spécifique à Codex** sauf contrainte produit clairement identifiée.

## Le vault `memory/`

`memory/` est le vault Obsidian **local** à ce poste (non versionné avec le kit, voir `.gitignore`). Structure :

- `index.md` — catalogue des projets et archives
- `archives/` — fichiers horodatés, une archive par session complète
- `projets/{nom}/context.md` — snapshot mutable du projet
- `projets/{nom}/history.md` — fil chronologique avec liens vers les archives
- `.obsidian/` — config Obsidian (créée automatiquement à l'ouverture du vault par Obsidian)

**Fichiers Obsidian spéciaux** dans `memory/` : `.excalidraw.md`, `.canvas`, `.base` ; ne pas éditer avec des opérations texte brutes, passer par Obsidian.

## Conventions de déploiement Codex

- Le script déploie les prompts dans `~/.codex/prompts/` et les skills dans `~/.codex/skills/{nom}/SKILL.md`.
- Le chemin du vault est écrit dans `~/.codex/memory-kit.json` à l'installation, puis lu par les prompts et skills à l'exécution.
- Ne jamais coder un chemin local en dur dans les fichiers distribués ; utiliser `{{CONFIG_FILE}}` dans la procédure canonique quand nécessaire.
- Contrairement à Claude Code ou Mistral Vibe, l'adapter Codex ne repose pas ici sur une injection de bloc dans un fichier global d'instructions utilisateur ; le comportement est porté par les prompts et les skills distribués.

## Attentes pour les agents GPT/Codex dans ce dépôt

- Préserver l'architecture `core/` + `adapters/`.
- Éviter toute duplication procédurale entre plateformes.
- Lorsqu'une demande concerne Codex, vérifier d'abord si elle doit vivre dans `core/procedures/`, `adapters/codex/prompts/` ou `adapters/codex/skills/`.
- Si une modification doit être distribuée sans toucher `deploy.ps1`, rester dans une surface déjà prise en charge par le script ou dans ce dépôt racine quand l'objectif est la documentation de travail du repo.
