# Procédure : Principle (nouveau v0.5)

Objectif : ingérer rapidement un principe (heuristique, ligne rouge, valeur, règle d'action) dans `40-principes/`. Shortcut explicite quand l'utilisateur formule explicitement une règle.

## Déclenchement

L'utilisateur tape `/mem-principle {contenu}` ou exprime l'intention en langage naturel : « note ce principe », « ajoute cette règle », « ligne rouge », « toujours / jamais ».

Options reconnues :
- `--scope perso|pro` : force le scope.
- `--force ligne-rouge|heuristique|preference` : force le niveau de contrainte. Sinon le router infère depuis le ton (« ne jamais » = ligne-rouge, « préférer » = heuristique, « j'aime » = preference).
- `--domaine X` : force la sous-catégorie (dev, communication, vie, sante, etc.).
- `--projet {slug}` : force le rattachement projet origine. Sinon, projet courant si détecté.
- `--no-confirm`, `--dry-run` : passe au router.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Préformatage

Le titre du principe est extrait des premières mots significatifs (« ne jamais X » → titre « no-x »). Le corps est le contenu complet, qui peut inclure le **contexte d'origine** (incident, lecture, expérience qui a fait émerger le principe).

### 2. Invoquer le router avec hint zone forcée

Appeler le router avec :
- `Contenu` : le contenu du principe.
- `Hint zone` : `principes`.
- `Hint source` : `manuel` (sauf si extrait par `mem-archive` qui passera `vecu`).
- `Métadonnées` : force, domaine, projet origine si fournis.

{{INCLUDE _router}}

Le router :
- Détermine `force` (ligne-rouge / heuristique / preference) si non forcé.
- Détermine la sous-catégorie domaine.
- Écrit dans `{VAULT}/40-principes/{scope}/{domaine}/{slug-titre}.md`.
- Construit le frontmatter avec `type: principe`, `force`, `contexte_origine` (si dérivé d'une archive), `projet`, `tags`.
- Si invoqué depuis une archive parent (cas `mem-archive` qui extrait des principes), pose le lien bidirectionnel `derived_atoms` ↔ `contexte_origine`.

### 3. Confirmer

Rapport du router.
