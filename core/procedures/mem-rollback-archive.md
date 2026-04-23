# Procédure : Rollback Archive

Objectif : annuler la dernière archive d'un projet (ou de l'ensemble du vault) en cas de fausse manip ou d'archivage prématuré. Supprime le fichier archive, retire la ligne correspondante de `historique.md` et de `_index.md`.

**Limite connue** : le `contexte.md` du projet est **écrasé** à chaque archive complet. Le rollback ne restaure **pas automatiquement** l'ancien `contexte.md` — l'archive supprimée contenait elle-même le snapshot du moment. L'utilisateur est averti et peut relancer `/mem-recall {projet}` pour régénérer un contexte à partir de l'avant-dernière archive (ou des suivantes qui subsistent).

## Déclenchement

L'utilisateur tape `/mem-rollback-archive [projet]` ou exprime l'intention en langage naturel : « annule la dernière archive », « oublie la dernière session », « rollback l'archive de X ».

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ils corrompent les accents et les caractères diacritiques (`�` dans Obsidian).

Selon l'outil d'écriture :
- **Shell POSIX** (bash, sh, git-bash, WSL, macOS, Linux) : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM` ou `Out-File -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : `-Encoding UTF8` injecte un BOM — préférer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`.
- **cmd.exe** : ne pas utiliser pour du Markdown accentué — basculer sur PowerShell ou bash.
- **Python** : `open(path, 'w', encoding='utf-8', newline='\n')`.
- **Outils natifs LLM** (Write, file_write…) : vérifier la doc ; en cas de doute, écrire via shell avec une commande explicite en UTF-8.

## Écritures atomiques et protection contre les accès concurrents

Le vault peut subir des accès concurrents — deux sessions LLM parallèles, ou une session qui écrit pendant qu'Obsidian édite manuellement. Toutes les écritures de cette procédure doivent appliquer les patterns suivants.

### Pattern 1 — Rename atomique (pour toutes les écritures)

Chaque fichier écrit ou réécrit suit cette séquence :

1. Écrire le nouveau contenu dans `{fichier}.tmp` (même répertoire que la cible).
2. Rename atomique `{fichier}.tmp` → `{fichier}`. POSIX : `rename()` natif. Windows : `Move-Item -Force` ou `MoveFileEx` avec `REPLACE_EXISTING`.
3. Si le rename échoue, supprimer le `.tmp` et remonter l'erreur.

Commandes concrètes :

| Shell | Séquence |
|---|---|
| bash / POSIX | `printf '%s' "$contenu" > "$cible.tmp" && mv -f "$cible.tmp" "$cible"` |
| PowerShell 7+ | `Set-Content -Path "$cible.tmp" -Value $contenu -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$cible.tmp" -Destination $cible -Force` |
| Python | `Path(f"{cible}.tmp").write_text(contenu, encoding='utf-8', newline=''); Path(f"{cible}.tmp").replace(cible)` |

Pour la **suppression du fichier archive** cible du rollback, utiliser directement `rm` / `Remove-Item` / `Path.unlink()` — opération déjà atomique.

### Pattern 2 — Hash check read-before-write (pour les fichiers partagés)

Les fichiers partagés modifiables par plusieurs procédures (`_index.md`, `historique.md`) exigent un hash check avant toute réécriture :

1. Au début de l'opération : lire le fichier cible, calculer son SHA-256, mémoriser (`hash_initial`).
2. Juste avant l'écriture : relire le fichier cible, recalculer le SHA-256 (`hash_avant`).
3. Si `hash_avant != hash_initial` → le fichier a changé entre-temps. Ne pas écraser. Re-lire, merger les modifs souhaitées avec le contenu actuel, reprendre à l'étape 2 (max 3 tentatives).
4. Si `hash_avant == hash_initial` → procéder au rename atomique (pattern 1).
5. Après 3 tentatives échouées → stopper, avertir l'utilisateur : « Fichier `{cible}` modifié par un acteur externe pendant l'opération. Vérifie manuellement, relance la commande ensuite. »

### Limite connue

Ces patterns réduisent fortement la fenêtre de race mais ne l'éliminent pas complètement. Pour une protection stricte, le MCP memory-kit (Phase 3) utilisera un verrou applicatif via `asyncio.Lock`.

## Procédure

### 1. Identifier l'archive cible

Deux cas :

**Cas A — un projet est spécifié** (`/mem-rollback-archive iris-etl`) :

- Lire `{VAULT}/projets/{projet}/historique.md`.
- Prendre la dernière ligne d'archive du fichier (ligne la plus en bas, qui est aussi la plus récente selon le format d'écriture défini dans `mem-archive.md`).
- Extraire le chemin d'archive référencé dans le lien.

**Cas B — aucun projet spécifié** :

- Lister tous les fichiers de `{VAULT}/archives/*.md`, trier par nom (l'horodatage en préfixe est ISO donc un tri alphabétique décroissant donne le plus récent).
- Prendre le plus récent.
- Lire son frontmatter pour identifier le projet concerné (`projet: {slug}`).

Si aucune archive n'existe, répondre « Aucune archive à annuler. » et s'arrêter.

### 2. Afficher ce qui va être supprimé

**Avant toute suppression**, afficher clairement :

```
Archive à annuler : {chemin complet}
Projet : {slug}
Date : {date extraite du frontmatter}
Résumé : {titre H1 ou section Résumé, première ligne}
```

**Exécuter ensuite directement sans demander confirmation supplémentaire** — l'utilisateur a invoqué la commande en connaissance de cause.

### 3. Supprimer le fichier archive

Exécuter :

```powershell
Remove-Item -Path "{chemin absolu de l'archive}" -Force
```

### 4. Retirer la ligne de `historique.md`

Lire `{VAULT}/projets/{projet}/historique.md`. Supprimer la ligne qui contient le lien vers l'archive supprimée (comparaison par nom de fichier de l'archive). Réécrire le fichier.

Si après suppression l'historique ne contient plus aucune ligne d'archive, laisser le fichier avec juste son frontmatter et son titre H1 — ne pas le supprimer.

### 5. Retirer la ligne de `_index.md`

Lire `{VAULT}/_index.md`. Dans la section « Archives », supprimer la ligne qui contient le lien vers l'archive supprimée. Réécrire le fichier.

**Ne pas** toucher à la section « Projets » (le projet reste dans l'index même si son historique devient vide).

### 6. Avertir sur `contexte.md`

Afficher :

```
Archive annulée : {chemin}

Fichiers modifiés :
- {VAULT}/archives/{nom}.md (supprimé)
- {VAULT}/projets/{projet}/historique.md (ligne retirée)
- {VAULT}/_index.md (ligne retirée)

⚠ Attention : {VAULT}/projets/{projet}/contexte.md n'a PAS été restauré à son état d'avant.
L'archive que tu viens de supprimer contenait elle-même le snapshot de ce moment — il est perdu
sauf si tu as une copie git ou Obsidian. Pour régénérer un contexte à partir de l'avant-dernière
archive, lance : /mem-recall {projet}
```
