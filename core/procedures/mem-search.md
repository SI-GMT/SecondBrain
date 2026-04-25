# Procédure : Search (v0.5 brain-centric)

Objectif : recherche plein-texte dans le vault mémoire avec filtres multidimensionnels (zone, scope, kind, modality, projet, domaine, type, source). Retourner les occurrences avec contexte, groupées par fichier et triées par pertinence.

## Déclenchement

L'utilisateur tape `/mem-search {requête}` ou exprime l'intention en langage naturel : « cherche dans la mémoire X », « trouve les notes qui parlent de Y », « où est-ce qu'on avait parlé de Z ? ».

Options reconnues :
- `--zone {liste}` : limite aux zones données (ex: `--zone principes`, `--zone episodes,knowledge`).
- `--scope perso|pro|all` : filtre par scope. Défaut : `all`.
- `--kind projet|domaine` : filtre les épisodes par sous-logique.
- `--modality left|right` : filtre par modalité hémisphérique.
- `--projet {slug}` : filtre par projet rattaché.
- `--domaine {slug}` : filtre par domaine rattaché.
- `--type {valeur}` : filtre par type de note (ex: `--type principe`).
- `--source {valeur}` : filtre par source (`vecu|doc|archeo-git|archeo-atlassian|manuel`).
- `--limit N` : nombre max de matches (défaut 50).

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Récupérer la requête et les filtres

La requête est l'argument principal (premier token non-option). Si vide : répondre « Précise ce que tu cherches : `/mem-search {mot-clé ou phrase}`. » et s'arrêter.

- Recherche insensible à la casse par défaut.
- Support des guillemets pour phrase exacte.
- Les options `--xxx` sont parsées et utilisées comme filtres en R3.

### 2. Périmètre de recherche par défaut

Scanner **récursivement** les 9 zones racines :

```
{VAULT}/00-inbox/
{VAULT}/10-episodes/projets/
{VAULT}/10-episodes/domaines/
{VAULT}/20-knowledge/
{VAULT}/30-procedures/
{VAULT}/40-principes/
{VAULT}/50-objectifs/
{VAULT}/60-personnes/
{VAULT}/70-cognition/
{VAULT}/99-meta/
```

Si `--zone X` est fourni, restreindre aux zones listées.

**Exclure systématiquement** :

- `.obsidian/` et descendants.
- Fichiers `*.canvas`, `*.excalidraw.md`, `*.base` (contenu non textuel).
- `.trash/` si présent.

### 3. Exécuter la recherche

Utiliser un outil de recherche adapté (Grep, ripgrep ou équivalent) :

- Mode : `content` avec 2 lignes de contexte avant/après chaque match.
- Limite : `--limit` (défaut 50). Si atteinte, le signaler.

### 4. Filtrer par frontmatter

Pour chaque fichier matchant, lire son frontmatter et appliquer les filtres :

- `--scope` : ne garder que les fichiers avec `scope: {valeur}` (ou `all` = tous).
- `--kind` : ne garder que les fichiers avec `kind: {valeur}`.
- `--modality` : ne garder que les fichiers avec `modality: {valeur}`.
- `--projet` : ne garder que les fichiers avec `projet: {slug}` ou tag `projet/{slug}`.
- `--domaine` : ne garder que les fichiers avec `domaine: {slug}` ou tag `domaine/{slug}`.
- `--type` : ne garder que les fichiers avec `type: {valeur}`.
- `--source` : ne garder que les fichiers avec `source: {valeur}`.

### 5. Trier et grouper

- Grouper les matches par fichier.
- Trier les fichiers : zones `episodes` en premier (archives récentes en haut), puis autres zones par ordre alphabétique. Dans une même zone, archives horodatées triées par date décroissante.

### 6. Afficher le rapport

Format :

```
## Recherche : "{requête}" ({N filtres actifs})

{N} occurrence(s) dans {M} fichier(s).

### [{zone}] {chemin relatif au vault} ({k} matches)
> ligne 42 : ... {ligne avec match} ...
> ligne 58 : ... {ligne avec match} ...

### [{zone}] {chemin} ({k} matches)
> ...

...
```

Si aucun match :

```
## Recherche : "{requête}"

Aucune occurrence trouvée dans le vault (filtres actifs : {liste}).
```

### 7. Suggérer la suite

Si les résultats portent majoritairement sur un projet/domaine (slug récurrent dans les résultats), suggérer : « Tu veux que je charge le contexte de `{slug}` ? » — qui déclenchera `/mem-recall {slug}`.
