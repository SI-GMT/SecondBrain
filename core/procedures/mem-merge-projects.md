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
