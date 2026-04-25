# Procédure : List (v0.5 brain-centric)

Objectif : afficher l'inventaire du vault (projets, domaines, contenus par zone) avec état synthétique. Renommé depuis `mem-list-projects` en v0.5 car il liste maintenant aussi les domaines et peut filtrer par zone.

## Déclenchement

L'utilisateur tape `/mem-list` ou exprime l'intention en langage naturel : « liste mes projets », « quels projets j'ai en mémoire ? », « montre-moi tous les domaines », « inventaire du vault ».

Options reconnues :
- `--kind projet|domaine|all` : restreint l'inventaire. Défaut : `all` (projets + domaines).
- `--scope perso|pro|all` : filtre par scope. Défaut : `all`.
- `--zone {liste}` : liste les contenus des zones données au lieu de l'inventaire projets/domaines (ex: `--zone principes` = liste des principes).
- `--detail` : affiche en plus les compteurs par zone et le dernier événement.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure — mode inventaire (par défaut)

### 1. Énumérer projets et domaines

Lister les sous-dossiers de :
- `{VAULT}/10-episodes/projets/` → kind=projet
- `{VAULT}/10-episodes/domaines/` → kind=domaine

Pour chaque slug, lire son `contexte.md` pour récupérer :
- `scope` (filtrer si `--scope` actif).
- `phase` (champ frontmatter ou première ligne de la section État).
- `derniere-session` (frontmatter).
- Compteur d'archives dans `archives/`.

### 2. Afficher l'inventaire

Format de base :

```
## Vault SecondBrain — Inventaire

### Projets ({N}) — vocation finie
- **{slug}** ({scope}) — phase : {phase} — {N} archive(s) — dernière : {date}
- ...

### Domaines ({N}) — permanents
- **{slug}** ({scope}) — phase : {phase} — {N} archive(s) — dernière : {date}
- ...
```

Si `--detail` :

```
- **{slug}** ({scope})
  Phase : {phase}
  Archives : {N}
  Principes rattachés : {N}
  Objectifs ouverts : {N}
  Personnes liées : {N}
  Dernière session : {date}
```

## Procédure — mode liste de zone (`--zone X`)

Si `--zone X` est fourni, lister les contenus de la zone au lieu de l'inventaire projets/domaines.

### 1. Lister les fichiers de la zone

Énumérer récursivement les `.md` sous `{VAULT}/{NN-zone}/` et lire leur frontmatter.

### 2. Filtrer par scope si `--scope` actif

### 3. Afficher

Format :

```
## Vault SecondBrain — Zone {zone}

{N} item(s) trouvé(s).

### {sous-dossier 1}
- [{titre}]({chemin}) — {scope}, {date}
- ...

### {sous-dossier 2}
- ...
```

## Sortie minimale

Si le vault est vide ou ne contient ni projets ni domaines :

```
Vault vide. Crée ton premier projet ou domaine via /mem-archive ou /mem.
```
