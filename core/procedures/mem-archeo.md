# Procédure : Archeo

Objectif : **reconstituer l'historique d'un dépôt Git existant** sous forme de plusieurs archives datées dans le vault mémoire, une par jalon signifiant (tag de release, merge sur mainline, commit important). Permet de démarrer un projet dans le kit mémoire avec un contexte riche reconstruit *a posteriori*, plutôt qu'à partir d'une page blanche.

Complémentaire de `/mem-archive` (capture une session vécue) et `/mem-doc` (ingère un document local). `/mem-archeo` couvre le cas du dépôt qu'on reprend ou qu'on vient de découvrir, et dont l'historique Git contient des informations précieuses non encore matérialisées en archives.

## Déclenchement

L'utilisateur tape `/mem-archeo [chemin-du-dépôt]` (chemin par défaut : répertoire de travail courant) ou exprime l'intention en langage naturel : « fais une rétro Git de ce projet », « reconstitue l'historique de ce dépôt », « archéo sur ce repo », « analyse les tags de version et archive-les ».

Arguments possibles :
- `{chemin-du-dépôt}` (optionnel, défaut = CWD) : chemin absolu ou relatif vers un dépôt Git local.
- `--projet {nom}` : force le projet cible. Sinon, résolu automatiquement (voir étape 2).
- `--niveau {tags|releases|merges|commits}` : force un niveau de granularité. Sinon, détection auto (voir étape 3).
- `--depuis YYYY-MM-DD` : ne considère que les jalons postérieurs à cette date.
- `--jusqu-a YYYY-MM-DD` : ne considère que les jalons antérieurs à cette date.
- `--fenetre {jour|semaine|mois}` : uniquement pour niveau `commits`, taille de la fenêtre de regroupement. Défaut : `semaine`.
- `--dry-run` : liste les archives qui seraient créées, sans les écrire. **Recommandé pour la première passe sur un gros dépôt.**

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ils corrompent les accents français et les caractères diacritiques (`�` ou `Ã©` dans Obsidian).

Selon l'outil d'écriture :
- **Shell POSIX** (bash, sh, git-bash, WSL, macOS, Linux) : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : préférer `[System.IO.File]::WriteAllText(...)` avec `UTF8Encoding($false)`.
- **cmd.exe** : à éviter pour du Markdown accentué (OEM corrompt).
- **Python** (méthode la plus fiable sur Windows) : `Path(path).write_text(contenu, encoding='utf-8', newline='')`.

## Écritures atomiques et protection contre les accès concurrents

Mêmes patterns que `mem-archive` :

### Pattern 1 — Rename atomique (toutes les écritures)

1. Écrire dans `{fichier}.tmp`.
2. Rename atomique `{fichier}.tmp` → `{fichier}`.
3. En cas d'échec, supprimer le `.tmp` et remonter l'erreur.

### Pattern 2 — Hash check read-before-write (fichiers partagés)

Pour `_index.md`, `historique.md` : capture SHA-256 au début, re-hash juste avant écriture, merger + retry (max 3) si divergence, sinon avertir. Les archives horodatées reconstituées sont **nouvelles** et exemptées du hash check.

## Procédure

### 1. Valider le dépôt source

- Vérifier que `{chemin-du-dépôt}` est un dépôt Git (présence de `.git/` ou retour non-vide de `git -C {chemin} rev-parse --git-dir`).
- Si le chemin est absent ou non-Git → erreur explicite et arrêt.
- Récupérer :
  - Le nom du dépôt (dernier segment du chemin absolu).
  - La branche courante : `git -C {chemin} branch --show-current`.
  - L'URL distante si elle existe : `git -C {chemin} remote get-url origin` (utile pour `gh` si GitHub).
  - La date du premier commit : `git -C {chemin} log --reverse --format=%aI | head -1`.
  - La date du dernier commit : `git -C {chemin} log -1 --format=%aI`.

### 2. Résoudre le projet cible

Par priorité descendante :

1. **`--projet {nom}` explicite** → utiliser directement.
2. **Nom du dépôt** : vérifier s'il match (insensible à la casse) un slug déjà présent dans `{VAULT}/_index.md` section « Projets ». Si oui → utiliser ce projet. Sinon → utiliser le nom du dépôt comme nouveau slug (après sanitisation : lowercase, espaces/underscores → `-`).
3. **CWD courant** : seulement si le chemin-du-dépôt == CWD et que l'étape 2 n'a pas trouvé de match — segmenter le CWD et chercher un match dans les projets existants.
4. **Fallback `inbox`** : si tout échoue (cas rare — normalement le nom du dépôt fait toujours un slug). Avertir.

Si le projet résolu n'existe pas encore dans le vault, créer sa structure (`{VAULT}/projets/{nom}/contexte.md` + `historique.md` squelettes, ajout dans la section Projets de `_index.md` à l'étape 9).

### 3. Détecter le niveau de granularité

Si `--niveau` fourni → utiliser directement. Sinon, appliquer la hiérarchie descendante suivante et **s'arrêter au premier niveau qui produit au moins 1 jalon** :

1. **Tags Git** : `git -C {chemin} tag --sort=-v:refname` (triés par version). Si au moins 1 tag → niveau `tags`.
2. **Releases GitHub/GitLab** : si `gh` disponible et que `git remote get-url origin` pointe vers GitHub/GitLab, tenter `gh release list --limit 50`. Si des releases existent *sans* tag correspondant — cas rare — niveau `releases`.
3. **Merges sur mainlines** : `git -C {chemin} log --merges --first-parent {mainline}` pour chaque mainline connue (`main`, `master`, `recette`, `dev`). Collecter tous les commits de merge. Si au moins 1 merge → niveau `merges`.
4. **Commits sur mainlines regroupés par fenêtre temporelle** : `git -C {chemin} log --first-parent {mainline}`. Regrouper par fenêtre (par défaut `semaine`). 1 archive par fenêtre non-vide.

Retourner à l'utilisateur le niveau retenu + nombre de jalons détectés AVANT de commencer à écrire, pour qu'il confirme ou passe en `--dry-run`.

### 4. Confirmation interactive (sauf `--dry-run`)

Afficher à l'utilisateur :

```
Dépôt : {chemin} ({nom-dépôt})
Projet cible : {nom} ({"déjà présent" si existant, "nouveau" sinon})
Niveau retenu : {tags|releases|merges|commits}
Jalons détectés : {N}
Fenêtre : {date-premier} → {date-dernier}

Archives à créer (aperçu, max 10 premiers) :
  - YYYY-MM-DD — {type-jalon} — {description-courte}
  - ...

{N} archives seront créées dans {VAULT}/archives/. Confirmer ? (o/n)
```

Si `--dry-run` : ne pas écrire, juste afficher la liste complète et terminer.

Si l'utilisateur refuse : arrêter sans rien modifier.

### 5. Détecter les archives déjà existantes (idempotence)

Avant d'écrire chaque archive, vérifier dans `{VAULT}/archives/` s'il existe déjà un fichier pour ce jalon. Critères de détection :

- Lire les archives existantes avec frontmatter `source: archeo-git` ET `projet: {nom}`.
- Pour chaque archive trouvée, extraire le champ d'identifiant du jalon :
  - Niveau `tags` : frontmatter `git_tag`.
  - Niveau `releases` : frontmatter `git_release`.
  - Niveau `merges` : frontmatter `git_commit_sha` (le SHA du commit de merge).
  - Niveau `commits` : frontmatter `git_window_start` + `git_window_end`.
- Si l'identifiant du jalon existe déjà → **skip** ce jalon (ne pas dupliquer), informer l'utilisateur.
- Si un jalon correspond à une archive `source: vecu` dont la date couvre le même moment → **skip également**, jamais d'écrasement d'archive vécue par une archive reconstruite. Informer.

### 6. Pour chaque jalon à créer, extraire les données

Selon le niveau :

**Niveau `tags`** :
- Nom du tag : `v0.1.0`.
- Date du tag : `git -C {chemin} log -1 --format=%aI {tag}`.
- Auteur : `git log -1 --format="%an <%ae>" {tag}`.
- Message du tag (pour tags annotés) : `git tag -l -n99 {tag}`.
- SHA du commit : `git rev-list -n 1 {tag}`.
- Diff stat depuis le tag précédent : `git diff --stat {tag-précédent}..{tag}`.
- Liste des commits entre les deux tags : `git log --oneline {tag-précédent}..{tag}`.
- Si `gh` disponible : `gh release view {tag}` pour récupérer les release notes utilisateur.

**Niveau `releases`** (sans tag correspondant) : similaire à `tags` mais via `gh release view {tag-ou-id}`.

**Niveau `merges`** :
- SHA du merge : identifiant du jalon.
- Date, auteur, message du merge.
- Parents du merge : `git log -1 --format=%P {sha}` (2 parents, le premier = mainline avant le merge, le second = branche mergée).
- Nom de la branche mergée (si déductible du message ou de `git name-rev --name-only --refs="refs/remotes/*" {parent2}`).
- Diff stat : `git diff --stat {parent1}..{sha}`.
- Commits de la branche : `git log --oneline {parent1}..{parent2}`.
- Si `gh` et un numéro de PR est référencé dans le message (pattern `#\d+`) : `gh pr view {numéro}` pour récupérer description + commentaires.

**Niveau `commits` (regroupés par fenêtre)** :
- Date de début + date de fin de la fenêtre.
- Liste des commits de la fenêtre sur la mainline : `git log --first-parent --since={début} --until={fin} --format="%h %aI %s"`.
- Diff stat cumulatif de la fenêtre.
- Auteurs uniques.

**Enrichissement commun à tous les niveaux** :
- **Fichiers IA racine** : à la date du jalon (ou du dernier commit de la fenêtre), extraire via `git show {sha}:CLAUDE.md`, `git show {sha}:AGENTS.md`, `git show {sha}:GEMINI.md`, `git show {sha}:MISTRAL.md`. S'ils existent, en capturer un snippet (10-30 premières lignes).
- **README** à ce moment : `git show {sha}:README.md` (premier paragraphe).
- **Tickets référencés** : regex `[A-Z][A-Z0-9_]+-\d+` (pattern Jira/Linear) sur tous les messages de commit de la fenêtre / du jalon. Collecter les clés uniques.
- **PRs référencées** : regex `#\d+` sur les messages.

### 7. Écrire le fichier archive pour chaque jalon

Chemin : `{VAULT}/archives/YYYY-MM-DD-HHhMM-{nom}-archeo-{identifiant-jalon-san}.md`

Où `{identifiant-jalon-san}` est :
- Niveau `tags` : `tag-v0-1-0` (sanitisé : `.` → `-`).
- Niveau `releases` : `release-{slug-release}`.
- Niveau `merges` : `merge-{SHA-8-premiers-caractères}`.
- Niveau `commits` : `commits-{YYYY-MM-DD}-{YYYY-MM-DD}` (début-fin de fenêtre).

Pour éviter les collisions horaires entre plusieurs archives créées dans la même minute, utiliser `HHhMM` du premier commit du jalon (ou de la date du tag pour les tags) plutôt que l'heure courante.

Écriture via **rename atomique** (pattern 1). Pas de hash check (fichier nouveau).

Format de l'archive :

```markdown
---
date: YYYY-MM-DD
heure: "HH:MM"
projet: {nom}
source: archeo-git
git_repo: {chemin-absolu}
git_remote: {url-distante-ou-"local-only"}
git_niveau: {tags|releases|merges|commits}
git_tag: {tag-si-niveau-tags}
git_release: {release-si-niveau-releases}
git_commit_sha: {sha-complet-si-niveau-merges}
git_window_start: {YYYY-MM-DD-si-niveau-commits}
git_window_end: {YYYY-MM-DD-si-niveau-commits}
tags: [projet/{nom}, type/archive, source/archeo-git]
---

# Archeo YYYY-MM-DD — {Projet} — {Titre jalon}

## Résumé

[2-3 phrases reconstituant ce qui s'est passé à ce jalon, à partir des messages de commit et des release notes si disponibles.]

## Métadonnées du jalon

- **Type** : {tag | release | merge | fenêtre commits}
- **Identifiant** : {tag/release/SHA/période}
- **Date** : YYYY-MM-DD (ISO: YYYY-MM-DDTHH:MM:SSZ)
- **Auteur(s)** : {liste}
- **Branche** : {mainline concernée, ex: main}
- **Diff stat** : {X fichiers changés, +N insertions, -M suppressions}

## Synthèse reconstituée

### Changements principaux
[À partir des messages de commit, extraire les "feat:" / "fix:" / "refactor:" / "docs:" et les résumer par catégorie.]

### Décisions et contraintes visibles
[Extraits pertinents des messages qui révèlent une décision d'architecture ou un choix contraignant. Si release notes disponibles, les prioriser.]

### Tickets référencés
- {JIRA-123, LIN-42, ...} (si détectés)

### Pull Requests
- #42 — {titre si récupéré via gh} (si détectés)

### Fichiers IA racine au moment du jalon
- **CLAUDE.md** : {extrait — 5-10 lignes max, ou "absent"}
- **AGENTS.md** : {extrait ou "absent"}
- **GEMINI.md** : {extrait ou "absent"}
- **MISTRAL.md** : {extrait ou "absent"}

### README (premier paragraphe au moment du jalon)
> {extrait}

## Contenu brut (Git)

> [!note]- Log des commits du jalon (déplier)
> ```text
> {git log --oneline de la plage}
> ```

> [!note]- Diff stat (déplier)
> ```text
> {git diff --stat}
> ```

> [!note]- Release notes / message du tag (si disponible, déplier)
> ```text
> {contenu}
> ```
```

### 8. Mettre à jour l'historique projet

Pour chaque archive créée, ajouter une ligne dans `{VAULT}/projets/{nom}/historique.md` (ordre chronologique ascendant) :

```
- [YYYY-MM-DD — Archeo : {Titre-jalon}](../../archives/YYYY-MM-DD-HHhMM-{nom}-archeo-{identifiant}.md)
```

**Écriture via rename atomique + hash check** (patterns 1 et 2). Batch les ajouts : un seul read-before-write pour toutes les lignes à ajouter d'un coup, pas N écritures successives.

Si le fichier n'existe pas (projet nouvellement créé), créer d'abord le squelette standard.

### 9. Mettre à jour l'index global

Pour chaque archive créée, ajouter une entrée dans la section **Archives** de `{VAULT}/_index.md` (ordre chronologique ascendant) :

```
- [YYYY-MM-DD — {Projet} — Archeo : {Titre-jalon}](archives/YYYY-MM-DD-HHhMM-{nom}-archeo-{identifiant}.md)
```

Si c'est la première archive du projet (créé à cette archéologie), ajouter aussi dans la section **Projets** :

```
- [{Projet}](projets/{nom}/historique.md)
```

**Écriture via rename atomique + hash check** (patterns 1 et 2). Batch identique à l'étape 8.

### 10. Enrichir le contexte projet (optionnel mais utile)

Si le projet est **nouvellement créé** à cette archéologie (aucun `contexte.md` préexistant), pré-remplir `{VAULT}/projets/{nom}/contexte.md` avec une synthèse de l'archéologie :

- Phase : « reconstituée via archéo le YYYY-MM-DD — pas de session vécue encore ».
- Décisions cumulées : agrégées depuis les messages de commit des jalons les plus significatifs.
- État validé / en cours : déduit du dernier jalon (si dernière release avec tag, la version est "stable" ; sinon "en cours").
- Assets actifs : URL du dépôt distant, chemin local.

Si le projet **existait déjà** avec un `contexte.md`, **ne pas l'écraser**. Afficher à l'utilisateur : « Le contexte actuel a été conservé. Les nouvelles archives archéo enrichissent l'historique mais pas le snapshot mutable. Utilise `/mem-recall {nom}` + édition manuelle si tu veux y intégrer des éléments. »

### 11. Confirmer

Afficher à l'utilisateur :

```
Archéologie terminée pour le projet {nom}.

Dépôt analysé : {chemin}
Niveau retenu : {tags|releases|merges|commits}
Archives créées : {N} (sur {M} jalons détectés — {M-N} skippées car déjà présentes)
Plage couverte : {date-première-archive} → {date-dernière-archive}

Vérifier dans Obsidian : {VAULT}/projets/{nom}/historique.md

Prochaine étape suggérée : {ouvrir dans Obsidian | /mem-recall {nom} pour charger le contexte reconstitué | relancer avec --niveau plus fin si les jalons actuels sont trop grossiers}
```
