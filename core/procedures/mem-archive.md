# Procédure : Archive

Objectif : archiver la session de travail en cours afin de permettre à l'utilisateur de faire `/clear` sans perdre le contexte. L'archive doit contenir tout ce qu'il faut pour reprendre dans une session future.

## Deux modes

### Mode incrémental silencieux (pendant la session)

À tout moment de la session, dès qu'un fait ou une décision important émerge et n'est pas encore présent dans le `contexte.md` cible (cf. « Détection de la branche » ci-dessous) :

- Mettre à jour **uniquement** `contexte.md` — ajouter la ligne dans la section appropriée (Décisions cumulées, Prochaines étapes, Assets actifs).
- **Ne pas** créer de fichier archive. **Ne pas** annoncer l'action à l'utilisateur sauf s'il le demande.
- Justification : `contexte.md` est un snapshot mutable, conçu pour évoluer en continu ; `archives/` est réservé aux instantanés de fin de session.

### Mode archive complet (fin de session)

Déclenché par un signal explicite :
- L'utilisateur tape `/mem-archive` ou `/clear`.
- L'utilisateur dit en langage naturel « on s'arrête », « je pars », « on termine », « archive ».

Exécuter alors la procédure complète ci-dessous.

## Résolution du chemin du vault

Avant toute écriture, lire le fichier de configuration du kit mémoire ({{CONFIG_FILE}}) et en extraire le champ `vault`. Dans la suite de cette procédure, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Détection de la branche courante et routage feature/projet

Pour déterminer si l'archive doit aller au niveau **projet global** ou au niveau **feature**, détecter la branche Git courante du répertoire de travail :

```
git branch --show-current
```

Décision :

| Cas détecté | Routage |
|---|---|
| Pas un repo Git (`.git` absent) ou HEAD détaché | **Projet global** (fallback safe) |
| Branche dans les **mainlines** : `main`, `master`, `recette`, `dev`, `hotfix/*`, `release/*` | **Projet global** |
| Toute autre branche (ex: `feature/foo`, `bugfix/xyz`, `user/john/wip`) | **Feature** |

**Sanitisation du nom de branche** : pour un routage feature, remplacer tous les `/` par `--` dans le nom de branche afin d'obtenir un nom de dossier portable Windows/POSIX.

Exemples :
- `feature/foo-bar` → `feature--foo-bar`
- `user/john/wip` → `user--john--wip`
- `bugfix/iss-123` → `bugfix--iss-123`

Dans la suite, `{branche-san}` désigne le nom sanitisé.

**Définition des cibles** (utilisées dans les étapes ci-dessous) :

| Cible | Cas projet global | Cas feature |
|---|---|---|
| `{cible-contexte}` | `{VAULT}/projets/{nom}/contexte.md` | `{VAULT}/projets/{nom}/features/{branche-san}/contexte.md` |
| `{cible-historique}` | `{VAULT}/projets/{nom}/historique.md` | `{VAULT}/projets/{nom}/features/{branche-san}/historique.md` |
| Nom de fichier archive | `YYYY-MM-DD-HHhMM-{nom}-{resume-court}.md` | `YYYY-MM-DD-HHhMM-{nom}-{branche-san}-{resume-court}.md` |
| Frontmatter archive `tags` | `[projet/{nom}, type/archive]` | `[projet/{nom}, feature/{branche-san}, type/archive]` |
| Frontmatter archive (champ supplémentaire) | — | `feature: {branche-san}` |

Le fichier archive horodaté lui-même reste **toujours** dans `{VAULT}/archives/` (structure FS plate). Le découpage feature/projet est logique, matérialisé par le frontmatter et les chemins de contexte/historique.

## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ils corrompent les accents français et les caractères diacritiques (`�` dans Obsidian).

Selon l'outil d'écriture :
- **Shell POSIX** (bash, sh, git-bash, WSL, macOS, Linux) : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM` ou `Out-File -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : `-Encoding UTF8` injecte un BOM — préférer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`.
- **cmd.exe** : ne pas utiliser pour du Markdown accentué (encodage OEM corrompt) — basculer sur PowerShell ou bash.
- **Python** : `open(path, 'w', encoding='utf-8', newline='\n')`.
- **Outils natifs LLM** (Write, file_write…) : vérifier la doc ; en cas de doute, écrire via shell avec une commande explicite en UTF-8.

## Écritures atomiques et protection contre les accès concurrents

Le vault peut subir des accès concurrents — deux sessions LLM parallèles (ex: Claude Code + Codex), ou une session LLM qui écrit pendant qu'Obsidian édite manuellement le même fichier. Sans protection, last-write-wins corrompt ou fait perdre des entrées.

### Pattern 1 — Rename atomique (pour toutes les écritures)

Chaque fichier écrit ou réécrit suit cette séquence :

1. Écrire le nouveau contenu dans `{fichier}.tmp` (même répertoire que la cible).
2. Rename atomique `{fichier}.tmp` → `{fichier}`. Sur POSIX, `rename()` est atomique et remplace silencieusement. Sur Windows, `Move-Item -Force` (PowerShell) ou équivalent (MoveFileEx avec `MOVEFILE_REPLACE_EXISTING`).
3. Si le rename échoue, supprimer le `.tmp` et remonter l'erreur à l'utilisateur.

Commandes concrètes :

| Shell | Séquence |
|---|---|
| bash / POSIX | `printf '%s' "$contenu" > "$cible.tmp" && mv -f "$cible.tmp" "$cible"` |
| PowerShell 7+ | `Set-Content -Path "$cible.tmp" -Value $contenu -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$cible.tmp" -Destination $cible -Force` |
| Python | `Path(f"{cible}.tmp").write_text(contenu, encoding='utf-8', newline=''); Path(f"{cible}.tmp").replace(cible)` (`replace` est atomique cross-platform) |

### Pattern 2 — Hash check read-before-write (pour les fichiers partagés)

Les fichiers suivants peuvent être modifiés par plusieurs procédures ou par Obsidian en parallèle — ils exigent un hash check avant toute réécriture :

- `{VAULT}/_index.md`
- `{VAULT}/projets/{nom}/historique.md` (et `{VAULT}/projets/{nom}/features/{branche-san}/historique.md`)
- `{VAULT}/projets/{nom}/contexte.md` (et `{VAULT}/projets/{nom}/features/{branche-san}/contexte.md`)

Procédure pour chaque écriture de ces fichiers :

1. **Début d'opération** : lire le fichier, calculer son SHA-256, mémoriser (`hash_initial`).
2. **Juste avant l'écriture** : relire le fichier cible, recalculer son SHA-256 (`hash_avant`).
3. Si `hash_avant != hash_initial` → le fichier a été modifié entre-temps par un autre acteur. **Ne pas écraser**. Relire le contenu actuel, merger les modifs qu'on voulait apporter, puis reprendre à l'étape 2 (boucle jusqu'à 3 tentatives).
4. Si `hash_avant == hash_initial` → procéder au rename atomique (pattern 1).
5. Si après 3 tentatives le hash continue de diverger → stopper, afficher un avertissement à l'utilisateur : « Fichier `{cible}` modifié par un acteur externe pendant l'archivage. Vérifie manuellement, relance `/mem-archive` ensuite. »

Le fichier **archive horodaté** (`{VAULT}/archives/YYYY-MM-DD-HHhMM-...md`) est exempté du hash check : c'est un fichier **nouveau** à chaque session, aucun conflit possible. Mais il doit quand même utiliser le rename atomique (pattern 1).

### Limite connue

Ces patterns réduisent fortement la fenêtre de race mais ne l'éliminent pas complètement. Une race reste théoriquement possible entre le calcul de `hash_avant` et le rename. Pour une protection stricte, le MCP memory-kit (Phase 3) utilisera un verrou applicatif via `asyncio.Lock`.

## Procédure (mode complet)

### 1. Collecter le contexte

Synthétiser depuis la conversation en cours :

- **Projet** concerné (demander à l'utilisateur si ambigu)
- **Travail effectué** : livrables produits, fichiers créés ou modifiés
- **Décisions** prises et leur justification
- **État du projet** : phase actuelle, éléments validés, éléments en cours
- **Prochaines étapes** prévues
- **Fichiers modifiés** avec chemins complets
- **Assets générés** : URLs d'images, vidéos, fichiers exportés (noter « Aucun. » si session purement logique)

Détecter également la branche courante (voir section « Détection de la branche ») pour déterminer `{cible-contexte}`, `{cible-historique}` et le nom de fichier archive.

### 2. Écrire le fichier archive

Chemin : `{VAULT}/archives/YYYY-MM-DD-HHhMM-{nom}-{resume-court}.md` (cas projet global) OU `{VAULT}/archives/YYYY-MM-DD-HHhMM-{nom}-{branche-san}-{resume-court}.md` (cas feature).

Écriture via **rename atomique** (pattern 1 ci-dessus). Pas de hash check nécessaire (fichier nouveau).

Format (exemple cas feature — pour cas projet global, retirer la ligne `feature:` et le tag `feature/...`) :

```markdown
---
date: YYYY-MM-DD
heure: "HH:MM"
projet: {nom}
phase: {phase actuelle}
feature: {branche-san}
tags: [projet/{nom}, feature/{branche-san}, type/archive]
---

# Session YYYY-MM-DD HHhMM — {Projet} {Résumé}

## Résumé
[2-3 phrases : objectif de la session + résultat livré]

## Travail effectué
- {action}

## Décisions
- **{Décision}** : {raison}

## État du projet
- Phase actuelle : {phase}
- Branche : {branche-courante} (cas feature uniquement)
- Validé : {éléments terminés}
- En cours : {éléments en cours}

## Prochaines étapes
1. {étape}

## Fichiers modifiés
- `{chemin}` — {créé|modifié|supprimé}

## Assets (URLs)
{URLs des fichiers générés, ou « Aucun. »}
```

### 3. Réécrire le contexte cible

Écrire `{cible-contexte}` en écrasant intégralement le fichier existant. Ce fichier est la vue courante du projet (ou de la feature) — mutable, écrasée à chaque archivage complet. Ne pas accumuler les sessions ; c'est le rôle des archives.

**Écriture obligatoirement via rename atomique + hash check** (patterns 1 et 2 ci-dessus).

Si le dossier parent n'existe pas (cas feature première archive : `{VAULT}/projets/{nom}/features/{branche-san}/`), le créer avant.

Format (cas feature — pour cas projet global, retirer la ligne `feature:` et adapter le titre) :

```markdown
---
projet: {nom}
feature: {branche-san}
phase: {phase actuelle}
derniere-session: YYYY-MM-DD
tags: [projet/{nom}, feature/{branche-san}]
---

# {Projet} / {branche-courante} — Contexte actif

## État courant
- Phase : {phase actuelle}
- Branche : {branche-courante}
- Validé : {éléments}
- En cours : {éléments}

## Décisions cumulées
- {décision} — {raison}

## Prochaines étapes
1. {étape}

## Assets actifs (URLs)
{URLs validées les plus récentes}
```

### 4. Mettre à jour l'historique cible

Ajouter une ligne en fin de `{cible-historique}` :

```
- [YYYY-MM-DD HHhMM — {résumé}](../../archives/YYYY-MM-DD-HHhMM-{nom}-{resume}.md)
```

Pour une archive feature (cibles dans `features/{branche-san}/`), le lien relatif doit remonter d'un niveau supplémentaire :

```
- [YYYY-MM-DD HHhMM — {résumé}](../../../archives/YYYY-MM-DD-HHhMM-{nom}-{branche-san}-{resume}.md)
```

**Écriture via rename atomique + hash check** (patterns 1 et 2).

Si le fichier n'existe pas, le créer avec le squelette approprié :

Cas projet global :
```markdown
---
projet: {nom}
tags: [projet/{nom}]
---

# {Projet} — Historique des sessions

- [YYYY-MM-DD HHhMM — {résumé}](../../archives/YYYY-MM-DD-HHhMM-{nom}-{resume}.md)
```

Cas feature :
```markdown
---
projet: {nom}
feature: {branche-san}
tags: [projet/{nom}, feature/{branche-san}]
---

# {Projet} / {branche-courante} — Historique des sessions

- [YYYY-MM-DD HHhMM — {résumé}](../../../archives/YYYY-MM-DD-HHhMM-{nom}-{branche-san}-{resume}.md)
```

### 5. Référencer la feature dans le contexte projet (cas feature uniquement)

Quand on archive une feature pour la **première fois** (le dossier `{VAULT}/projets/{nom}/features/{branche-san}/` n'existait pas avant), ajouter une mention dans le `contexte.md` du projet global à la section « Features actives » (la créer si elle n'existe pas, juste avant la section « Assets actifs ») :

```markdown
## Features actives

- [{branche-courante}](features/{branche-san}/historique.md) — dernier archivage : YYYY-MM-DD
```

Si la section existe déjà mais ne contient pas cette feature, y ajouter la ligne. Si la feature est déjà listée, mettre à jour la date.

**Écriture via rename atomique + hash check** (patterns 1 et 2).

### 6. Mettre à jour l'index global

Dans `{VAULT}/_index.md`, ajouter une entrée dans la section **Archives** (ordre chronologique ascendant) :

Cas projet global :
```
- [YYYY-MM-DD HHhMM — {Projet} — {résumé}](archives/YYYY-MM-DD-HHhMM-{nom}-{resume}.md)
```

Cas feature :
```
- [YYYY-MM-DD HHhMM — {Projet} / {branche-courante} — {résumé}](archives/YYYY-MM-DD-HHhMM-{nom}-{branche-san}-{resume}.md)
```

Si c'est la première archive du projet (dossier `projets/{nom}/` créé à l'instant), ajouter aussi dans la section **Projets** :

```
- [{Projet}](projets/{nom}/historique.md)
```

Les features ne sont **pas** listées en section « Projets » de `_index.md` — elles s'accèdent par navigation depuis le `contexte.md` du projet parent.

**Écriture via rename atomique + hash check** (patterns 1 et 2).

### 7. Confirmer

Afficher à l'utilisateur (format adapté au cas) :

Cas projet global :
```
Archive créée : {VAULT}/archives/{fichier}.md
Contexte mis à jour : {VAULT}/projets/{nom}/contexte.md
Le /clear est safe — utilise /mem-recall {nom} pour reprendre.
```

Cas feature :
```
Archive créée : {VAULT}/archives/{fichier}.md  (feature: {branche-courante})
Contexte feature mis à jour : {VAULT}/projets/{nom}/features/{branche-san}/contexte.md
Contexte projet enrichi : {VAULT}/projets/{nom}/contexte.md  (section Features actives)
Le /clear est safe — utilise /mem-recall {nom} pour reprendre le projet global, ou relance la même branche pour retrouver le contexte feature.
```
