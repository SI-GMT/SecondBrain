# Procédure : Reclass (nouveau v0.5)

Objectif : changer le scope ou la zone d'un contenu existant. Met à jour le frontmatter + les tags + déplace le fichier physiquement + réécrit les références croisées (`_index`, `historique`, liens Obsidian).

Skill confirmé en v0.5 par décision D3.4 : un contenu peut basculer perso ↔ pro, ou changer de zone (ex: une note de connaissance qui devient un principe), via opération explicite.

## Déclenchement

L'utilisateur tape `/mem-reclass {chemin} [options]` ou exprime l'intention en langage naturel : « reclasse cette note », « passe ce principe en heuristique », « bascule cette note en perso ».

Arguments :
- `{chemin}` (**obligatoire**) : chemin absolu ou relatif d'un fichier dans le vault.
- `--zone X` : nouvelle zone cible (parmi les 9). Optionnel si seul `--scope` change.
- `--scope perso|pro` : nouveau scope. Optionnel si seul `--zone` change.
- `--type X` : nouveau type (selon zone cible).
- `--projet {slug}` ou `--domaine {slug}` : nouveau rattachement.
- `--dry-run` : affiche le plan de reclassement sans appliquer.
- `--no-confirm` : applique sans demander confirmation (mode batch).

Au moins un de `--zone`, `--scope`, `--type`, `--projet`, `--domaine` est requis.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Valider le fichier source

- Vérifier que `{chemin}` existe et est dans le vault.
- Lire son frontmatter (état avant).
- Vérifier que les changements demandés sont valides (cf. invariants section 7.3 du doc de cadrage) :
  - Si `--scope perso` mais le fichier a `collectif: true` → le forcer à `false` (avec avertissement).
  - Si `--zone episodes` sans `kind` ni `projet`/`domaine` → demander à l'utilisateur.
  - Si `--zone X` non valide → arrêter avec liste des zones acceptées.

### 2. Calculer le nouveau frontmatter et le nouveau chemin

Construire le frontmatter cible :
- Conserver tous les champs sauf ceux explicitement changés.
- Adapter `tags` pour refléter les changements (`zone/*`, `scope/*`, `type/*`, etc.).

Calculer le nouveau chemin :
- Si `--zone` change : nouveau chemin selon mapping section R5 du bloc router.
- Si `--scope` change pour une zone qui a `{scope}/` dans son chemin (procédures, principes, objectifs, personnes) : nouveau chemin avec scope mis à jour.
- Si `--projet`/`--domaine` change pour zone `episodes` : nouveau dossier projet/domaine.

### 3. Présenter le plan

Format :

```
## Reclassement — {chemin source}

Avant :
  zone   : {ancien}
  scope  : {ancien}
  type   : {ancien}
  ...

Après :
  zone   : {nouveau}
  scope  : {nouveau}
  type   : {nouveau}
  ...

Nouveau chemin : {nouveau-chemin}

Liens à réécrire :
  - {N} liens [[...]] dans d'autres fichiers du vault
  - Entrées dans 99-meta/_index.md
  - Entrées dans historique.md (si zone source ou cible = episodes)

Continuer ? [o/n]
```

Si `--dry-run` : s'arrêter ici.

### 4. Appliquer (si confirmé ou `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes :

1. **Écrire le fichier dans la nouvelle position** avec le nouveau frontmatter (rename atomique).
2. **Réécrire les liens Obsidian** : grep `[[ancien-nom]]` ou `[[chemin/ancien]]` dans tout le vault, remplacer par `[[nouveau-nom]]`. Patterns 1+2 sur chaque fichier modifié.
3. **Mettre à jour `99-meta/_index.md`** : retirer l'ancienne entrée, ajouter la nouvelle si applicable. Pattern 2.
4. **Si zone source = episodes** : retirer la ligne dans `historique.md` du projet/domaine source. Pattern 2.
5. **Si zone cible = episodes** : ajouter la ligne dans `historique.md` du projet/domaine cible. Pattern 2.
6. **Supprimer le fichier source** (après vérification que la copie destination existe).

### 5. Confirmer

Format :

```
Reclassement effectué :
  Source : {ancien-chemin} (supprimé)
  Cible  : {nouveau-chemin}

Liens réécrits : {N} fichiers mis à jour
Index mis à jour
```
