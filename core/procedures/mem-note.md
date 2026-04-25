# Procédure : Note (nouveau v0.5)

Objectif : ingérer rapidement une note de connaissance dans `20-knowledge/`. Shortcut explicite quand l'utilisateur sait que ce qu'il capte est un fait, un concept, une fiche, ou une synthèse stable.

## Déclenchement

L'utilisateur tape `/mem-note {contenu}` ou exprime l'intention en langage naturel : « note ce concept », « ajoute cette fiche », « enregistre cette définition ».

Options reconnues :
- `--scope perso|pro` : force le scope.
- `--famille metier|tech|vie|methodes` : force la famille de connaissance. Sinon, le router décide.
- `--type concept|fiche|glossaire|synthese|reference` : force le type.
- `--no-confirm`, `--dry-run` : passe au router.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Préformatage

Préparer le contenu Markdown de la note. Si l'utilisateur a fourni un titre clair, l'utiliser. Sinon, dériver un titre court depuis les premières lignes.

### 2. Invoquer le router avec hint zone forcée

Appeler le router avec :
- `Contenu` : le contenu de la note.
- `Hint zone` : `knowledge` (force la zone, bypass cascade).
- `Hint source` : `manuel`.
- `Métadonnées` : famille forcée si fournie, type forcé si fourni.

{{INCLUDE _router}}

Le router :
- Détermine la sous-famille (`metier`, `tech`, `vie`, `methodes`) si non forcée, basée sur les indices lexicaux.
- Écrit dans `{VAULT}/20-knowledge/{famille}/{sous-domaine}/{slug-titre}.md`.
- Construit le frontmatter avec `type`, `tags`, etc.
- Si l'invocation se fait depuis un projet/domaine courant, le tag `projet/{slug}` ou `domaine/{slug}` est ajouté pour rattachement transverse.

### 3. Confirmer

Le router produit son rapport. Pas d'action supplémentaire.
