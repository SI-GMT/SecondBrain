# Procédure : Merge Projects

Objectif : fusionner deux projets du vault mémoire. Utile quand des sessions ont été logguées sous deux slugs différents par erreur, ou quand deux initiatives convergent.

**Portée de la fusion** :

- Les archives du projet `{source}` sont retaggées (frontmatter `projet:` et `tags:`) au nom de `{cible}`. Elles restent dans `{VAULT}/archives/` avec leur nom de fichier d'origine (horodatage stable, récit immuable).
- L'historique de `{source}` est concaténé à celui de `{cible}` — les liens d'archive pointent toujours vers les bons fichiers.
- Le dossier `{VAULT}/projets/{source}/` est supprimé après fusion.
- La ligne `{source}` est retirée de la section « Projets » de `_index.md`.
- **Le `contexte.md` de `{cible}` n'est PAS modifié automatiquement** — la fusion sémantique des deux états courants est une décision éditoriale qui revient à l'utilisateur.

## Déclenchement

L'utilisateur tape `/mem-merge-projects {source} {cible}` ou exprime l'intention en langage naturel : « fusionne le projet X dans Y », « regroupe X et Y sous Y ».

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

Pour une **suppression de fichier ou dossier** (étape finale de la fusion), utiliser directement `rm` / `Remove-Item` / `Path.unlink()` — opérations déjà atomiques.

### Pattern 2 — Hash check read-before-write (pour les fichiers partagés)

Les fichiers partagés modifiables par plusieurs procédures (`_index.md`, `historique.md` de la cible, frontmatters d'archives) exigent un hash check avant toute réécriture :

1. Au début de l'opération : lire le fichier cible, calculer son SHA-256, mémoriser (`hash_initial`).
2. Juste avant l'écriture : relire le fichier cible, recalculer le SHA-256 (`hash_avant`).
3. Si `hash_avant != hash_initial` → le fichier a changé entre-temps. Ne pas écraser. Re-lire, merger les modifs souhaitées avec le contenu actuel, reprendre à l'étape 2 (max 3 tentatives).
4. Si `hash_avant == hash_initial` → procéder au rename atomique (pattern 1).
5. Après 3 tentatives échouées → stopper, avertir l'utilisateur : « Fichier `{cible}` modifié par un acteur externe pendant l'opération. Vérifie manuellement, relance la commande ensuite. »

### Limite connue

Ces patterns réduisent fortement la fenêtre de race mais ne l'éliminent pas complètement. Pour une protection stricte, le MCP memory-kit (Phase 3) utilisera un verrou applicatif via `asyncio.Lock`.

## Procédure

### 1. Valider les arguments

Deux slugs requis : `{source}` (sera supprimé) et `{cible}` (conservé, enrichi).

- Si un des deux manque, rejeter avec : « Syntaxe : `/mem-merge-projects {source} {cible}`. Le projet source disparaîtra ; le projet cible récupère ses archives. »
- Si `{source} == {cible}`, rejeter : « Les deux slugs sont identiques, rien à fusionner. »
- Si `{VAULT}/projets/{source}/` n'existe pas, rejeter : « Projet source `{source}` introuvable. »
- Si `{VAULT}/projets/{cible}/` n'existe pas, rejeter : « Projet cible `{cible}` introuvable. Utilise `/mem-rename-project {source} {cible}` si tu veux juste renommer. »

### 2. Extraire les archives de la source

Lire `{VAULT}/projets/{source}/historique.md`. Extraire toutes les lignes d'archive (`- [... — ...](../../archives/{nom-fichier}.md)`) et les chemins résolus.

Si `historique.md` est absent ou vide, la fusion concerne uniquement le retrait du dossier source — continuer quand même vers l'étape 3 mais noter dans le rapport final « Aucune archive côté source ».

### 3. Retagger les archives de la source

Pour chaque archive de la source :

- Lire le fichier.
- Dans le frontmatter YAML : remplacer `projet: {source}` par `projet: {cible}` et les tags `projet/{source}` par `projet/{cible}`.
- **Ne pas toucher** au corps narratif (récit immuable).

### 4. Concaténer l'historique

Lire `{VAULT}/projets/{cible}/historique.md`. Récupérer ses lignes d'archive existantes.

Lire les lignes d'archive de la source (extraites à l'étape 2).

Fusionner les deux listes en **triant par horodatage décroissant** (plus récent en haut — cohérent avec le format ISO dans les noms de fichiers). Réécrire `{VAULT}/projets/{cible}/historique.md` avec :

- Le frontmatter de la cible (inchangé).
- Le titre H1 (inchangé).
- La liste fusionnée et triée.

### 5. Supprimer le dossier source

Exécuter :

```powershell
Remove-Item -Path "{VAULT}/projets/{source}" -Recurse -Force
```

### 6. Mettre à jour `_index.md`

Lire `{VAULT}/_index.md`. Dans la section « Projets », supprimer la ligne qui contient `](projets/{source}/historique.md)`. Laisser la section « Archives » intacte (les liens pointent toujours vers les fichiers existants, juste retaggés).

### 7. Rapport final

Afficher :

```
Projets fusionnés : {source} → {cible}

Fichiers modifiés :
- {N} archive(s) retaggée(s) dans {VAULT}/archives/
- {VAULT}/projets/{cible}/historique.md (entrées fusionnées et triées)
- {VAULT}/_index.md (entrée {source} retirée)

Fichier supprimé :
- {VAULT}/projets/{source}/ (dossier entier)

⚠ À faire manuellement :
- Relire {VAULT}/projets/{cible}/contexte.md et fusionner les décisions / prochaines étapes
  qui étaient dans l'ancien contexte de {source}. La fusion sémantique n'est pas automatisable
  — elle demande ton jugement éditorial.
```
