# Procédure : Doc

Objectif : ingérer **un document local** (PDF, Markdown, texte, image, etc.) dans le vault mémoire en tant qu'archive single-shot, avec synthèse structurée et copie préservée du fichier source.

Complémentaire de `/mem-archive` (qui capture une session vécue) et `/mem-archeo` (qui reconstruit des archives depuis l'historique Git). `/mem-doc` couvre le cas du document qui traîne sur le disque : SFD reçu par mail, spec Word sur NAS, présentation kickoff, PDF scanné, export Confluence local, notes exportées, etc.

## Déclenchement

L'utilisateur tape `/mem-doc {chemin}` ou exprime l'intention en langage naturel : « ingère ce document », « archive ce fichier », « enregistre ce PDF dans ma mémoire », « absorbe ce document dans le projet X ».

Arguments possibles :
- `{chemin}` (**obligatoire**) : chemin absolu ou relatif du fichier à ingérer.
- `--projet {nom}` (optionnel) : force le projet cible. Sinon, résolu automatiquement (voir étape 2).
- `--titre "{texte}"` (optionnel) : titre court pour l'archive. Sinon, dérivé du nom de fichier.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ils corrompent les accents français et les caractères diacritiques (`�` ou `Ã©` dans Obsidian).

Selon l'outil d'écriture :
- **Shell POSIX** (bash, sh, git-bash, WSL, macOS, Linux) : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM` ou `Out-File -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : `-Encoding UTF8` injecte un BOM — préférer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`.
- **cmd.exe** : ne pas utiliser pour du Markdown accentué (OEM corrompt) — basculer sur PowerShell ou bash.
- **Python** (méthode la plus fiable sur Windows) : `open(path, 'w', encoding='utf-8', newline='\n')` ou `Path(path).write_text(contenu, encoding='utf-8', newline='')`.

Cette procédure **copie** un fichier source (binaire ou texte) — la copie doit être **byte-for-byte identique** à l'original, pas de ré-encodage (voir étape 5).

## Écritures atomiques et protection contre les accès concurrents

Le vault peut subir des accès concurrents. Toutes les écritures de cette procédure doivent appliquer les patterns suivants.

### Pattern 1 — Rename atomique (pour toutes les écritures)

1. Écrire le nouveau contenu dans `{fichier}.tmp`.
2. Rename atomique `{fichier}.tmp` → `{fichier}`.
3. Si le rename échoue, supprimer le `.tmp` et remonter l'erreur.

| Shell | Séquence |
|---|---|
| bash / POSIX | `printf '%s' "$contenu" > "$cible.tmp" && mv -f "$cible.tmp" "$cible"` |
| PowerShell 7+ | `Set-Content -Path "$cible.tmp" -Value $contenu -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$cible.tmp" -Destination $cible -Force` |
| Python | `Path(f"{cible}.tmp").write_text(contenu, encoding='utf-8', newline=''); Path(f"{cible}.tmp").replace(cible)` |

Pour la **copie binaire** du fichier source (étape 5), utiliser directement `cp` / `Copy-Item` / `shutil.copy2` — opérations déjà atomiques côté FS.

### Pattern 2 — Hash check read-before-write (pour les fichiers partagés)

Pour `_index.md`, `historique.md`, `contexte.md` (cible) :

1. Capture SHA-256 au début (`hash_initial`).
2. Re-hash juste avant écriture (`hash_avant`).
3. Si divergence → merger les modifs, retry (max 3).
4. Sinon → rename atomique (pattern 1).
5. Après 3 échecs → avertir l'utilisateur.

## Procédure

### 1. Valider le chemin source

- Vérifier que `{chemin}` existe et est un **fichier** (pas un dossier — v1 est strict 1 fichier).
- Calculer la taille du fichier en octets.
- **Si taille > 50 Mo** : avertir l'utilisateur et demander confirmation avant de continuer (« Ce fichier fait {taille} Mo, la copie sera stockée dans `{VAULT}/archives/_sources/`. Continuer ? »). Si refus, arrêter.
- Déterminer le type via extension :
  - `.md`, `.txt` → texte Markdown / plat, lecture directe.
  - `.pdf` → PDF, extraction via les capacités natives du LLM (outil de lecture de PDF si disponible).
  - `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` → image, description via les capacités vision du LLM.
  - `.docx`, `.pptx`, `.xlsx`, `.odt`, `.html`, `.htm` → formats v2 (pandoc requis) — si l'outil n'est pas disponible dans l'environnement, informer l'utilisateur que le format sera supporté en v2 et arrêter.
  - Autre extension → tenter lecture texte brute, si échec de décodage UTF-8, arrêter avec message explicite.

### 2. Résoudre le projet cible

Par priorité descendante :

1. **Argument explicite `--projet {nom}`** → utiliser directement.
2. **Match dans le chemin source** : séparer `{chemin}` sur `/` et `\`, prendre chaque segment, comparer (insensible à la casse) avec les noms de projets listés dans `{VAULT}/_index.md` section « Projets ». Si un segment matche un slug de projet → utiliser ce projet. Exemple : `C:\_PROJETS\MULTIPLATEFORME\GMT-Knowledges\spec.pdf` → segment `GMT-Knowledges` match slug `gmt-knowledges` → projet `gmt-knowledges`.
3. **Match dans le CWD** : appliquer la même logique que (2) sur les segments du `pwd` courant.
4. **Fallback `inbox`** : si aucun match → projet cible = `inbox`. Avertir l'utilisateur : « Projet cible non détecté, archive placée dans `inbox`. Utilise `/mem-rename-project inbox {nom}` pour reclasser, ou déplace manuellement l'archive ensuite. »

Si le projet résolu (autre que `inbox`) n'existe pas encore dans le vault — créer sa structure : `{VAULT}/projets/{nom}/contexte.md` + `{VAULT}/projets/{nom}/historique.md` avec squelettes minimaux. Le projet sera ajouté à la section Projets de `_index.md` en étape 7.

### 3. Calculer le hash SHA-256 du source

- Lire le fichier en mode binaire, calculer le SHA-256.
- Noter les 8 premiers caractères hexa (`{hash8}`) — utilisés dans le nom de la copie.
- Noter le hash complet (`{hash_full}`) — utilisé dans le frontmatter.

### 4. Détecter une re-ingestion

- Lister les archives existantes dans `{VAULT}/archives/` qui ont un frontmatter `source: doc`.
- Pour chaque, lire `source_hash` du frontmatter.
- **Si `{hash_full}` existe déjà** → le document a déjà été ingéré. Informer l'utilisateur : « Ce fichier (hash `{hash8}…`) a déjà été ingéré le {date} dans l'archive `{nom-archive}`. Re-ingérer créera un doublon. Continuer ? ». Sur refus, arrêter ; sur confirmation, continuer (chaque ingestion reste datée).

### 5. Copier le fichier source

Chemin destination : `{VAULT}/archives/_sources/{YYYY-MM}/{hash8}-{nom-original-sans-ext}.{ext}`

Où :
- `{YYYY-MM}` : mois courant (ex: `2026-04`), groupement pour éviter le dossier à plat.
- `{hash8}` : 8 premiers caractères hexa du SHA-256.
- `{nom-original-sans-ext}` : nom de fichier original nettoyé (retirer caractères FS-invalides `\/:*?"<>|`, remplacer espaces par `_`).
- `{ext}` : extension originale (conservée).

Exemple : `spec-technique v2.1.pdf` avec hash `a3f4b9c2...` → `{VAULT}/archives/_sources/2026-04/a3f4b9c2-spec-technique_v2.1.pdf`.

Actions :
1. Créer `{VAULT}/archives/_sources/{YYYY-MM}/` si absent (créer les parents).
2. Au **premier usage du dossier `_sources/`** : créer `{VAULT}/archives/_sources/.gitignore` avec :
   ```
   # Ignore tous les binaires copiés (évite d'enfler un repo Git partagé).
   # Si un vault est versionné et que tu veux garder les sources, supprime ce .gitignore.
   *.pdf
   *.png
   *.jpg
   *.jpeg
   *.gif
   *.webp
   *.docx
   *.doc
   *.pptx
   *.ppt
   *.xlsx
   *.xls
   *.odt
   *.zip
   *.tar
   *.gz
   ```
3. **Copie byte-for-byte** : `cp` (bash), `Copy-Item` (pwsh), `shutil.copy2` (Python). Jamais de `cat` / `Get-Content > Set-Content` sur un binaire — ça corromprait.

### 6. Écrire le fichier archive

Chemin : `{VAULT}/archives/YYYY-MM-DD-HHhMM-{nom}-doc-{titre-court-san}.md`

Où `{titre-court-san}` est dérivé de `--titre` ou du nom de fichier original (sanitisé : lowercase, espaces → `-`, caractères spéciaux retirés, max 40 caractères).

Écriture via **rename atomique** (pattern 1). Pas de hash check (fichier nouveau).

Format de l'archive :

```markdown
---
date: YYYY-MM-DD
heure: "HH:MM"
projet: {nom}
source: doc
source_path: "{chemin-original-absolu}"
source_type: {pdf|md|txt|image|docx|...}
source_hash: "{hash_full}"
source_copy: "_sources/{YYYY-MM}/{hash8}-{nom}.{ext}"
source_size_bytes: {taille}
tags: [projet/{nom}, type/archive, source/doc]
---

# Doc YYYY-MM-DD — {Projet} — {Titre du document}

## Résumé

[2-3 phrases : objet du document + raison probable de son ingestion + valeur pour le projet]

## Métadonnées source

- **Fichier** : `{nom-original}.{ext}` ({taille humaine, ex: 2.3 Mo})
- **Chemin original** : `{chemin-absolu}`
- **Type** : {description, ex: PDF — spécification fonctionnelle détaillée}
- **Hash SHA-256** : `{hash_full}`
- **Copie vault** : `[{hash8}-{nom}.{ext}](../archives/_sources/{YYYY-MM}/{hash8}-{nom}.{ext})`
- **Ingéré le** : YYYY-MM-DD HHhMM

## Synthèse structurée

### Objet
[Ce que le document décrit / couvre / spécifie.]

### Décisions et contraintes extraites
- [Décision ou contrainte 1]
- [Décision ou contrainte 2]

### Actions / TODOs extraits
- [ ] [Action 1]
- [ ] [Action 2]

### Glossaire (termes métier définis)
- **{terme}** : {définition}

### Questions ouvertes
- [Question 1]
- [Question 2]

### Liens / références mentionnés
- {URL ou mention}

## Contenu brut

> [!note]- Contenu intégral du document (déplier)
> {contenu extrait du document, sans reformulation. Pour un PDF, le texte extrait. Pour une image, une description exhaustive. Pour un docx, le Markdown généré par pandoc. Pour un fichier texte, le contenu brut. Si très volumineux (> 5000 mots), tronquer avec une indication explicite « [contenu tronqué — voir source copie] ».}
```

### 7. Mettre à jour l'historique projet

Ajouter une ligne en fin de `{VAULT}/projets/{nom}/historique.md` (cas projet global — pour le cas `inbox`, même comportement) :

```
- [YYYY-MM-DD HHhMM — Doc : {Titre}](../../archives/YYYY-MM-DD-HHhMM-{nom}-doc-{titre-court-san}.md)
```

Écriture via **rename atomique + hash check** (patterns 1 et 2).

Si le fichier n'existe pas (projet nouvellement créé), créer le squelette standard (cf. `mem-archive.md` étape 4).

### 8. Mettre à jour l'index global

Dans `{VAULT}/_index.md`, ajouter une entrée dans la section **Archives** (ordre chronologique ascendant) :

```
- [YYYY-MM-DD HHhMM — {Projet} — Doc : {Titre}](archives/YYYY-MM-DD-HHhMM-{nom}-doc-{titre-court-san}.md)
```

Si c'est la première archive du projet (créé à cette ingestion), ajouter aussi dans la section **Projets** :

```
- [{Projet}](projets/{nom}/historique.md)
```

**Écriture via rename atomique + hash check** (patterns 1 et 2).

### 9. Confirmer

Afficher à l'utilisateur :

```
Document ingéré dans le projet {nom}.

Archive : {VAULT}/archives/{fichier-archive}.md
Source copiée : {VAULT}/archives/_sources/{YYYY-MM}/{hash8}-{nom}.{ext}
Hash SHA-256 : {hash_full}

Synthèse : [1 phrase de résumé]
Prochaine étape suggérée : {ouvrir dans Obsidian | consulter l'archive | ingérer d'autres documents du même dossier}
```

Si le projet cible est `inbox`, rappeler :
```
Reclasser ensuite avec /mem-rename-project inbox {nom-cible} si tu veux attribuer ce document à un projet existant.
```
