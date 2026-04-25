# Procédure : Person (nouveau v0.5)

Objectif : ingérer une fiche personne (collègue, client, ami, famille) dans `60-personnes/`. Shortcut explicite. Toujours `sensitive: true` par défaut (interdit la promotion vers CollectiveBrain).

## Déclenchement

L'utilisateur tape `/mem-person {contenu}` ou exprime l'intention en langage naturel : « ajoute cette personne », « note ce contact », « fiche de {nom} ».

Options reconnues :
- `--scope perso|pro` : force le scope.
- `--categorie collegues|clients|partenaires|famille|amis|connaissances` : force la sous-catégorie.
- `--no-confirm`, `--dry-run` : passe au router.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Préformatage

Extraire du contenu fourni :
- `nom` : prénom + NOM (obligatoire, demander à l'utilisateur si absent).
- `role` : rôle ou relation (« CTO », « collègue », « médecin de famille », « ami d'enfance »).
- `organisation` : société/structure (pour pro).
- `contact` : email, tel si fournis.
- Notes libres : contexte, premières interactions, points notables.

Si `nom` est extractible des premiers mots du contenu (« Jean DUPONT a fait... » → nom = Jean DUPONT), le faire automatiquement. Sinon, demander.

### 2. Invoquer le router avec hint zone forcée

Appeler le router avec :
- `Contenu` : la fiche structurée.
- `Hint zone` : `personnes`.
- `Hint source` : `manuel`.
- `Métadonnées` : nom, role, organisation, contact, catégorie si fournie.

{{INCLUDE _router}}

Le router :
- Détermine la sous-catégorie selon scope et indices (« mon enfant » → famille, « collègue » → collegues, etc.).
- Écrit dans `{VAULT}/60-personnes/{scope}/{categorie}/{slug-nom}.md`.
- Frontmatter avec `type: personne`, `nom`, `role`, `organisation`, `contact`, `derniere_interaction: today`, **`sensitive: true` (toujours)**.

### 3. Confirmer

Rapport du router. Mentionner explicitement que la fiche est `sensitive: true` (donc jamais remontée vers CollectiveBrain).
