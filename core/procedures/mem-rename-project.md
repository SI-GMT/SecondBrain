# Procédure : Rename Project

Objectif : renommer un projet dans le vault mémoire de manière **complète** — plus aucune référence à l'ancien nom (slug OU label) ne doit subsister, sauf volonté explicite de l'utilisateur de conserver une trace historique.

**Portée du renommage** (tout est mis à jour) :

- **Slug** (utilisé dans les chemins, frontmatters, tags, noms de fichiers d'archives).
- **Label affiché** (utilisé dans les titres H1 et les labels de liens `_index.md`). Si l'utilisateur ne fournit pas de nouveau label, en dériver un depuis le slug (`iris-sync` → « Iris Sync », séparateurs `-`/`_` → espace, capitalisation des mots).
- **Noms de fichiers des archives** : oui, renommés (remplacement du slug dans le nom, horodatage préservé).
- **Contenu narratif des archives** : balayé pour remplacer les mentions littérales de l'ancien slug ou de l'ancien label.

## Déclenchement

L'utilisateur tape `/mem-rename-project {ancien-slug} {nouveau-slug}` ou exprime l'intention en langage naturel : « renomme le projet X en Y », « change le slug de X ».

L'utilisateur peut aussi préciser un nouveau label explicitement : `/mem-rename-project {ancien-slug} {nouveau-slug} --label "Nouveau Label"`. À défaut, dériver le label du nouveau slug.

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

Deux arguments requis : `{ancien-slug}` et `{nouveau-slug}`.

- Non-vides, composés uniquement de `[a-z0-9_-]`.
- Différents (sinon répondre « Les deux slugs sont identiques, rien à faire. »).

### 2. Vérifier l'existence des dossiers

- `{VAULT}/projets/{ancien-slug}/` doit exister, sinon arrêter avec message d'erreur.
- `{VAULT}/projets/{nouveau-slug}/` ne doit PAS exister, sinon proposer `/mem-merge-projects`.

### 3. Déterminer l'ancien label

Lire `{VAULT}/_index.md` section « Projets ». Trouver la ligne pointant vers `projets/{ancien-slug}/historique.md` et extraire le texte entre crochets — c'est l'**ancien label**.

### 4. Déterminer le nouveau label

Si l'utilisateur a fourni `--label "..."`, l'utiliser. Sinon, dériver du `{nouveau-slug}` :

- Remplacer `-` et `_` par des espaces.
- Capitaliser la première lettre de chaque mot (sauf mots courts : `de`, `du`, `le`, `la`, `à`, `et`).

Exemples : `iris-sync` → `Iris Sync` ; `app-mobile-rh` → `App Mobile Rh`.

### 5. Renommer le dossier projet

```powershell
Rename-Item -Path "{VAULT}/projets/{ancien-slug}" -NewName "{nouveau-slug}"
```

### 6. Mettre à jour `contexte.md`

Dans `{VAULT}/projets/{nouveau-slug}/contexte.md` :

- Frontmatter : `projet: {ancien-slug}` → `{nouveau-slug}`, `tags: [projet/{ancien-slug}]` → `[projet/{nouveau-slug}]`.
- H1 : remplacer toute occurrence de l'ancien label par le nouveau label.
- Corps : balayer et remplacer les mentions littérales du `{ancien-slug}` et de l'ancien label (`{ancien-label}`) par leur nouvelle version.

### 7. Mettre à jour `historique.md`

Dans `{VAULT}/projets/{nouveau-slug}/historique.md` :

- Frontmatter : idem (slug + tags).
- H1 : « {ancien-label} — Historique des sessions » → « {nouveau-label} — Historique des sessions ».
- **Les liens vers les archives seront corrigés à l'étape 9** (après renommage des fichiers).

### 8. Traiter chaque archive référencée

Pour chaque archive listée dans `historique.md` (lire et résoudre les chemins `../../archives/...`) :

- Lire le fichier.
- Frontmatter : `projet:` et `tags:` → nouveau slug.
- H1 : remplacer l'ancien label par le nouveau label.
- Corps : balayer et remplacer les mentions littérales de `{ancien-slug}` et `{ancien-label}` par leur équivalent. **Ne pas toucher** aux faits historiques pertinents (dates, données métier) — seuls les références au nom du projet sont impactées.
- Sauvegarder.

### 9. Renommer les fichiers archives

Pour chaque archive référencée : si son nom de fichier contient `{ancien-slug}`, le renommer en remplaçant cette portion par `{nouveau-slug}` (préserver le préfixe horodaté + le suffixe résumé).

```powershell
Rename-Item -Path "{VAULT}/archives/{nom-fichier-ancien}.md" -NewName "{nom-fichier-nouveau}.md"
```

Puis mettre à jour les liens dans `historique.md` (section corps) : remplacer `../../archives/{ancien-nom}.md` par `../../archives/{nouveau-nom}.md`.

### 10. Mettre à jour `_index.md`

Dans `{VAULT}/_index.md` :

- **Section « Projets »** : remplacer `[{ancien-label}](projets/{ancien-slug}/historique.md)` par `[{nouveau-label}](projets/{nouveau-slug}/historique.md)`.
- **Section « Archives »** : pour chaque ligne mentionnant `{ancien-label}` ou pointant vers une archive renommée :
  - Remplacer le label par le nouveau.
  - Remplacer le chemin (nom de fichier) par le nouveau chemin.

### 11. Nettoyer `.obsidian/workspace.json` (optionnel)

Si `{VAULT}/.obsidian/workspace.json` existe et contient des entrées `lastOpenFiles` pointant vers l'ancien slug, les retirer (ce sont des caches de tabs). Si Obsidian est ouvert au moment du rename, il écrasera le fichier à la fermeture — l'action reste correcte mais peut être perdue. Dans ce cas, inviter l'utilisateur à fermer/rouvrir Obsidian après l'opération.

### 12. Vérification finale

Exécuter un `grep` (ou équivalent) sur `{VAULT}/` à l'exception de `.obsidian/` pour s'assurer qu'il ne reste plus aucune occurrence littérale du `{ancien-slug}` ni de l'ancien label. Si des occurrences subsistent, les lister dans le rapport final sous « À traiter manuellement ».

### 13. Rapport final

Afficher à l'utilisateur :

```
Projet renommé : {ancien-slug} → {nouveau-slug}
Label : {ancien-label} → {nouveau-label}

Fichiers modifiés :
- {VAULT}/projets/{nouveau-slug}/ (dossier renommé)
- {VAULT}/projets/{nouveau-slug}/contexte.md (frontmatter + H1 + corps)
- {VAULT}/projets/{nouveau-slug}/historique.md (frontmatter + H1 + liens vers archives)
- {VAULT}/_index.md (section Projets + section Archives)
- {N} archive(s) dans {VAULT}/archives/ (frontmatter + H1 + corps + nom de fichier renommé)
- {VAULT}/.obsidian/workspace.json (entrées stales nettoyées)

Vérification finale : 0 référence résiduelle à « {ancien-slug} » ou « {ancien-label} » dans le vault.
```

Si la vérification finale trouve des occurrences, les lister après le rapport sous :

```
À traiter manuellement (occurrences résiduelles détectées) :
- {chemin}:{ligne} — {extrait}
```
