# Doctrine binding : structure mémoire — namespace vs project vs branch

> Doctrine binding (cf. `_when-to-script`, `_archived`, `_linking`, `_mcp-first`, `_frontmatter-archeo`, `_archeo-architecture-v2`). Référencée par `mem-archive.md`, `mem-archeo.md`, `mem-promote-domain.md`, `mem-rename.md`, `mem-merge.md`, `mem-reclass.md`. Source de vérité pour la classification des entités mémorielles.

## Contexte

Le drift `gmt-user` du repo IRIS USER (case study Codex 2026-05-08) a rendu visible un défaut structurel : le slug `gmt-user` était utilisé comme `project` alors qu'il représente un **namespace IRIS** (collection de features hétérogènes : EcoSAV, COMPTA, RSS, arrondis-2digits, etc.). Empiler des archives `archeo-{branch}-branch-first` sous le même slug a mélangé domaine fonctionnel + topologie + features sans distinction sémantique. Codex a flagué le défaut spontanément (« ce projet memoire sert de conteneur transversal »), confirmant que la classification est ambiguë.

Cette doctrine fixe la sémantique pour éliminer le drift.

## Sémantique

**Trois entités distinctes** :

| Entité | Rôle | Localisation vault | Granularité |
|--------|------|---------------------|-------------|
| **Domain** | Scope fonctionnel — un namespace, un ensemble cohérent de features partageant des principes / données / acteurs. | `10-episodes/domains/{slug}/` | Plusieurs projects et atomes transverses. |
| **Topology** | Scope organisationnel — la structure du repo qui héberge le domain (catégories de fichiers, stack, workspaces, branches). | `99-meta/repo-topology/{slug}.md` (+ `{slug}-branches/{branch}.md` pour chaque branche archivée) | Un atome par repo + un atome par branche persistée. |
| **Project / Feature** | Périmètre d'évolution d'une branche, d'une feature, ou d'un projet ponctuel. Un project = une intention qui converge dans le temps. | `10-episodes/projects/{slug}/` | Un par branche ou feature trackée. |

**Règles de classification** :

1. **Un repo = un domain + une topology**, pas un project. Le slug du domain matche typiquement le namespace ou le nom du repo (ex : `gmt-user`, `secondbrain`).

2. **Une branche fonctionnelle = un project**, distinct du domain qui l'héberge. Le project a son propre `context.md`, `history.md`, `archives/`. Son frontmatter porte `domain: {namespace-slug}` pour le lien remontant.

3. **Une feature transverse non-branche** (ex : un sprint, un projet client one-shot) = un project, lié à un domain ou pas selon le contexte.

4. **Un domain n'a pas d'archives `archeo-{branch}-branch-first.md`**. Ces archives sont la propriété du project correspondant à la branche, pas du domain. Le domain peut citer les projects via wikilinks dans son `context.md`.

5. **Pour un repo mono-feature** (un repo = un projet unique, ex : `secondbrain` lui-même), le domain peut être **sous-entendu** : le project porte directement les archives, et `99-meta/repo-topology/{slug}.md` capture la topologie. Pas de domain explicite nécessaire.

## Détection d'un drift namespace-project

Un slug `10-episodes/projects/{slug}/` est candidat **namespace mal classé** si :

- Son dossier `archives/` contient **au moins 2 archives** dont le frontmatter `source` est `archeo-git` ET dont les `branch` sont **distincts**.
- OU son `context.md` mentionne explicitement un terme de namespace (« namespace », « workspace », « conteneur transversal », « collection de projets »).

Quand détecté → la migration `v2_namespace_to_domain` (cf. `mcp-server/src/memory_kit_mcp/migrations/v2_namespace_to_domain.py`) propose de scinder le slug en :

- `10-episodes/domains/{slug}/` — le domain (créé)
- `10-episodes/projects/{branch-slug}/` — un project par branche distincte trouvée dans les archives (créés)

**Le project namespace original n'est pas supprimé par la migration** — l'utilisateur le laisse en place pendant la transition pour traçabilité, et le retire manuellement via `mem_rename` ou suppression de dossier quand satisfait.

## Conventions de slug

- **Domain slug** : reprend le nom du namespace ou du repo. Pas de préfixe.
- **Branch project slug** : 
  - Si la branche a un nom explicite et unique (`ecosav`, `dev-compta`) → le slug est ce nom (sanitized : minuscules, accents fold ASCII, `/` → `-`).
  - Si conflit avec un autre project existant → préfixé par le namespace : `{namespace}-{branch-slug}` (ex : `gmt-user-ecosav`).
  - Le slug ne porte PAS de date ni de timestamp (les archives le font déjà via leur nom de fichier).

- **Topology branch atom slug** : suit la convention `{namespace}-branches/{branch-slug}` sous `99-meta/repo-topology/`. Le filename est `{branch-slug}.md` à l'intérieur du sous-dossier `{namespace}-branches/`.

## Frontmatter requis

Le frontmatter universel (cf. `_frontmatter-archeo.md`) s'applique à tous. Champs spécifiques par type :

**Domain** (`zone: episodes`, `kind: domain`) :

```yaml
zone: episodes
kind: domain
slug: <namespace>
display: <namespace> — domain
scope: work | personal
collective: false
related_projects:
  - <branch-slug-1>
  - <branch-slug-2>
related_topology: 99-meta/repo-topology/<namespace>.md
```

**Project (branche)** (`zone: episodes`, `kind: project`) :

```yaml
zone: episodes
kind: project
slug: <branch-slug>
display: <branch-slug> — project
scope: work | personal
collective: false
domain: <namespace>           # lien remontant vers le domain (peut être absent
                              # si le project est standalone — ex : secondbrain)
branch: <branch-name>         # nom Git réel de la branche, peut différer du slug
repo_path: <abs-path>         # le repo qui héberge la branche
workspace_member: ""
```

**Topology repo** (`zone: meta`, `kind: repo-topology`) :

```yaml
zone: meta
kind: repo-topology
slug: <namespace>
display: <namespace> — repo topology
source: archeo-topology
source_mode: git | raw
content_hash: <sha256>
last_archive: 99-meta/repo-topology/<namespace>-branches/<branch>.md  # optional
```

**Topology branch** (`zone: meta`, `kind: repo-topology`, sous-dossier `{namespace}-branches/`) :

```yaml
zone: meta
kind: repo-topology
slug: <namespace>             # le slug pointe sur le NAMESPACE, pas la branche —
                              # cohérence avec le domain auquel la branche est rattachée
display: <namespace> — branch topology <branch>
branch: <branch-name>
branch_base: <base-branch>
branch_base_sha: <sha>
files_count: <int>
files_bytes: <int>
files_hash: <sha256>
related_archive: 10-episodes/projects/<branch-slug>/archives/<archive-file>.md
```

Le champ `kind` (et non `type`) est canonique. Tout atome avec `type: repo-topology` est un legacy à migrer (la migration v2 le corrige).

## Doctrine corollaire

- **`mem_archive` invoquée sur un slug namespace mal classé** doit avertir et proposer la migration `v2_namespace_to_domain`. La pratique d'empiler des archives sur un namespace est doctrinalement déconseillée à partir de v0.10.x.

- **`mem_archeo` orchestrator** ne crée des archives que sous le slug du **project ciblé** (la branche), pas sous le slug du namespace. Si le slug fourni est candidat namespace selon l'heuristique ci-dessus, l'outil émet un warning et suggère de fournir explicitement le slug de la branche ou de lancer la migration.

- **Wikilinks** entre domain ↔ project ↔ topology : maintenance mécanique via `mem_health_repair` (catégorie `dangling-wikilinks` existante).

- **Migration vault** : la migration `v2_namespace_to_domain` est idempotente, takes-backup, dry-run par défaut, applied via `--apply` (CLI) ou `mem_migrate` (MCP tool). Elle ne supprime jamais le project namespace original — c'est l'utilisateur qui décide quand le retirer.
