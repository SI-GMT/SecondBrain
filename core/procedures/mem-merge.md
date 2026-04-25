# Procédure : Merge (v0.5 brain-centric)

Objectif : fusionner deux projets OU deux domaines du vault mémoire. Réattribue les archives, principes, objectifs, personnes liés à la source vers la cible. Retire la source de l'index.

Renommé depuis `mem-merge-projects` en v0.5. **Restriction** : on ne peut pas mélanger projet ↔ domaine (la nature est différente : un projet a une fin, un domaine non). Pour transformer un projet en domaine, utiliser `mem-promote-domain`.

## Déclenchement

L'utilisateur tape `/mem-merge {source} {cible}` ou exprime l'intention en langage naturel : « fusionne le projet X dans Y », « regroupe les domaines X et Y sous Y ».

Arguments :
- `{source}` (**obligatoire**) : slug à fusionner (sera supprimé après merge).
- `{cible}` (**obligatoire**) : slug qui absorbe (conservé).
- `--dry-run` : affiche le plan sans appliquer.
- `--no-confirm` : applique sans confirmation.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Identifier kind des deux slugs

Chercher chacun dans `projets/` puis `domaines/`. Vérifier qu'ils ont **le même kind** (les deux projets, ou les deux domaines). Sinon, arrêter avec message clair.

### 2. Énumérer les éléments à transférer

- **Archives** : `{VAULT}/10-episodes/{kind}/{source}/archives/*.md` → cible.
- **`historique.md` source** : à fusionner en fin de l'`historique.md` cible (ordre chronologique préservé).
- **`contexte.md` source** : NE PAS écraser le cible. Annexer les sections « Décisions cumulées » et « Prochaines étapes » de source dans cible avec une note `(fusionné depuis {source} le YYYY-MM-DD)`.
- **Atomes transverses** (40-principes, 50-objectifs, 60-personnes, 20-knowledge) avec tag `projet/{source}` ou `domaine/{source}` : retag vers `projet/{cible}` ou `domaine/{cible}`. Le frontmatter `projet:` / `domaine:` aussi mis à jour.
- **Liens Obsidian** : `[[{source}]]` → `[[{cible}]]`.
- **`99-meta/_index.md`** : retirer source, mettre à jour cible.

### 3. Présenter le plan

Format :

```
## Fusion — {source} → {cible} ({kind})

À transférer :
  - {N} archives → {VAULT}/10-episodes/{kind}/{cible}/archives/
  - {N} entrées historique.md
  - {N} principes, {N} objectifs, {N} personnes, {N} notes connaissance retaggés
  - {N} liens Obsidian réécrits

À supprimer après merge :
  - Dossier {VAULT}/10-episodes/{kind}/{source}/

contexte.md cible : annexion des sections "Décisions cumulées" et "Prochaines étapes"

Continuer ? [o/n]
```

Si `--dry-run` : s'arrêter ici.

### 4. Appliquer (si confirmé ou `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes :

1. **Déplacer les archives** : `mv {source}/archives/*.md {cible}/archives/`. Si conflit de nom (extrêmement rare avec des horodatages différents), renommer en `{nom}-from-{source}.md`.
2. **Renommer les fichiers d'archives** qui contiennent `{source}` dans leur nom : `2026-01-15-...-{source}-...md` → `2026-01-15-...-{cible}-...md`.
3. **Réécrire frontmatters** : remplacer `projet: {source}` → `projet: {cible}` (et `domaine:` idem) dans tous les fichiers transférés et dans tous les atomes transverses.
4. **Réécrire les tags** : `projet/{source}` → `projet/{cible}` (idem domaine).
5. **Réécrire les liens Obsidian** : `[[{source}` → `[[{cible}` dans tout le vault.
6. **Fusionner `historique.md`** : annexer les entrées source en fin de cible (préserver l'ordre chronologique global → resort par date après fusion).
7. **Annexer `contexte.md`** : ajouter à la fin du `contexte.md` cible une section « ## Fusionné depuis {source} le YYYY-MM-DD » avec les sections clés du source.
8. **Supprimer le dossier source** : `rm -rf {VAULT}/10-episodes/{kind}/{source}/` après vérification que toutes les archives ont bien été transférées.
9. **Mettre à jour `99-meta/_index.md`** : retirer entrée source, garder cible.

### 5. Confirmer

Format :

```
Fusion effectuée : {source} → {cible} ({kind})
  Archives transférées : {N}
  Atomes retaggés : {N}
  Liens réécrits : {N}
  Dossier source supprimé.
```
