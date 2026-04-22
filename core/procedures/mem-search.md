# Procédure : Search

Objectif : recherche plein-texte dans le vault mémoire. Retourner les occurrences avec contexte, groupées par fichier et triées par pertinence (archives récentes d'abord).

## Déclenchement

L'utilisateur tape `/mem-search {requête}` ou exprime l'intention en langage naturel : « cherche dans la mémoire X », « trouve les archives qui parlent de Y », « où est-ce qu'on avait parlé de Z ? ».

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Récupérer la requête

La requête est l'argument passé à la commande ou l'expression identifiée dans le langage naturel.

- Si vide : répondre « Précise ce que tu cherches : `/mem-search {mot-clé ou phrase}`. » et s'arrêter.
- Recherche insensible à la casse par défaut.
- Support des guillemets pour phrase exacte (ex. `/mem-search "merge freeze"`).

### 2. Périmètre de recherche

Scanner **récursivement** ces emplacements :

- `{VAULT}/_index.md`
- `{VAULT}/archives/*.md`
- `{VAULT}/projets/**/*.md`

**Exclure** :

- Le dossier `.obsidian/` et ses descendants (configuration Obsidian, non pertinent).
- Les fichiers `*.canvas`, `*.excalidraw.md`, `*.base` (contenu non textuel géré par Obsidian).
- Le dossier `.trash/` s'il existe.

### 3. Exécuter la recherche

Utiliser un outil de recherche adapté (Grep côté Claude Code / équivalent côté autre plateforme) :

- Mode : `content` avec 2 lignes de contexte avant/après chaque match.
- Limite : 50 matches au total pour ne pas inonder la sortie. Si la limite est atteinte, le signaler dans le rapport.

### 4. Trier et grouper les résultats

- Grouper les matches par fichier.
- Pour chaque fichier, afficher le nom + nombre de matches.
- Trier les fichiers : archives en premier (les plus récentes d'abord, basé sur l'horodatage du nom de fichier), puis `projets/**/contexte.md`, puis `projets/**/historique.md`, puis `_index.md`.

### 5. Afficher le rapport

Format :

```
## Recherche : "{requête}"

{N} occurrence(s) dans {M} fichier(s).

### {VAULT}/archives/2026-04-21-21h03-secondbrain-v0-1-0-publie.md ({k} match)
> ligne 42 : ... {ligne avec match surligné} ...
> ligne 58 : ... {ligne avec match surligné} ...

### {VAULT}/projets/secondbrain/contexte.md ({k} match)
> ligne 15 : ... {ligne avec match surligné} ...

...
```

Si aucun match :

```
## Recherche : "{requête}"

Aucune occurrence trouvée dans le vault.
```

### 6. Suggérer la suite

Si les résultats portent majoritairement sur un projet (nom apparaît dans plusieurs archives du même projet), suggérer : « Tu veux que je charge le contexte de `{projet}` ? » — qui déclenchera `/mem-recall {projet}`.
