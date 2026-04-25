# Procédure : Goal (nouveau v0.5)

Objectif : ingérer un objectif (intention future, état désiré, but) dans `50-objectifs/`. Shortcut explicite quand l'utilisateur formule un objectif.

## Déclenchement

L'utilisateur tape `/mem-goal {contenu}` ou exprime l'intention en langage naturel : « ajoute cet objectif », « note ce but », « j'aimerais atteindre X d'ici Y ».

Options reconnues :
- `--scope perso|pro` : force le scope.
- `--horizon court|moyen|long` : force l'horizon temporel. Court = semaines, moyen = mois, long = années.
- `--echeance YYYY-MM-DD` : date cible explicite.
- `--projet {slug}` : rattachement projet (typiquement pour objectifs `pro/projets/`).
- `--no-confirm`, `--dry-run` : passe au router.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Préformatage

Le titre de l'objectif est extrait des premières mots significatifs. Le corps inclut le « pourquoi » (motivation), les jalons éventuels, les indicateurs de succès.

### 2. Invoquer le router avec hint zone forcée

Appeler le router avec :
- `Contenu` : le contenu de l'objectif.
- `Hint zone` : `objectifs`.
- `Hint source` : `manuel` (sauf dérivation par `mem-archive`).
- `Métadonnées` : horizon, échéance, projet si fournis.

{{INCLUDE _router}}

Le router :
- Détermine `horizon` si non forcé (heuristique : échéance < 1 mois = court, < 6 mois = moyen, > = long).
- Détermine la sous-catégorie selon scope et projet (`perso/{vie|sante|famille|finances}` ou `pro/{carriere|projets/{slug}}`).
- Écrit dans `{VAULT}/50-objectifs/...`.
- Frontmatter avec `type: objectif`, `horizon`, `echeance`, `statut: ouvert` (par défaut), `projet`.

### 3. Confirmer

Rapport du router.
