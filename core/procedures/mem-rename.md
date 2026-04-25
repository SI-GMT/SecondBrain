# Procédure : Rename (v0.5 brain-centric)

Objectif : renommer un projet ou domaine dans le vault. Réécrit le slug **partout** (dossier physique, frontmatter de toutes les archives, tags `projet/{slug}` ou `domaine/{slug}`, liens Obsidian, `_index.md`, `historique.md`).

Renommé depuis `mem-rename-project` en v0.5 car il opère maintenant sur projets ET domaines.

## Déclenchement

L'utilisateur tape `/mem-rename {ancien} {nouveau}` ou exprime l'intention en langage naturel : « renomme le projet X en Y », « change le slug du domaine X ».

Arguments :
- `{ancien}` (**obligatoire**) : slug actuel.
- `{nouveau}` (**obligatoire**) : nouveau slug.
- `--dry-run` : affiche le plan sans appliquer.
- `--no-confirm` : applique sans confirmation.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Identifier kind (projet ou domaine)

Chercher `{ancien}` dans :
- `{VAULT}/10-episodes/projets/{ancien}/` → kind=projet
- `{VAULT}/10-episodes/domaines/{ancien}/` → kind=domaine

Si introuvable : arrêter avec message clair.
Si trouvé dans les deux : arrêter, demander explicitation (extrêmement rare, mais à protéger).

### 2. Vérifier conflit avec le nouveau slug

Vérifier que `{VAULT}/10-episodes/{kind}/{nouveau}/` n'existe pas déjà. Si conflit, arrêter avec message clair.

### 3. Énumérer toutes les références à réécrire

- **Dossier projet/domaine** : `{VAULT}/10-episodes/{kind}/{ancien}/` → `{VAULT}/10-episodes/{kind}/{nouveau}/`
- **Frontmatter `projet:` ou `domaine:`** : tous les fichiers du vault qui ont `projet: {ancien}` ou `domaine: {ancien}`.
- **Tags `projet/{ancien}` ou `domaine/{ancien}`** : tous les fichiers avec ce tag (transverses : peuvent être en `40-principes/`, `50-objectifs/`, etc.).
- **Liens Obsidian** : `[[{ancien}]]`, `[[{ancien}/...]]`, `[[archives/...{ancien}...]]`.
- **`99-meta/_index.md`** : entrée projet/domaine + entrées d'archives.
- **`historique.md`** : titre + liens.
- **`contexte.md`** : champ `slug:` du frontmatter.
- **Sous-dossiers `50-objectifs/pro/projets/{ancien}/`** s'il existe.

### 4. Présenter le plan

Format :

```
## Renommage — {ancien} → {nouveau} ({kind})

Fichiers touchés : {N}
  - Dossier principal : {ancien-chemin} → {nouveau-chemin}
  - Archives : {N} fichiers (frontmatter + tags)
  - Atomes transverses (40-principes, 50-objectifs, ...) : {N} fichiers
  - Liens Obsidian dans le vault : {N} occurrences
  - Index global : 1 entrée
  - Historique : 1 fichier

Continuer ? [o/n]
```

Si `--dry-run` : s'arrêter ici.

### 5. Appliquer (si confirmé ou `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes (ordre important) :

1. **Renommer le dossier** : `mv {VAULT}/10-episodes/{kind}/{ancien}/ {VAULT}/10-episodes/{kind}/{nouveau}/`
2. **Renommer les fichiers d'archives** dans `{nouveau}/archives/` qui contiennent `{ancien}` dans leur nom : `2026-01-15-...-{ancien}-...md` → `2026-01-15-...-{nouveau}-...md`
3. **Réécrire les frontmatters et tags** : pour chaque fichier touché, regex remplace `projet: {ancien}` → `projet: {nouveau}`, `domaine: {ancien}` → `domaine: {nouveau}`, `projet/{ancien}` → `projet/{nouveau}`, `domaine/{ancien}` → `domaine/{nouveau}`. Pattern 1+2 sur chaque écriture.
4. **Réécrire les liens Obsidian** dans tout le vault : grep + remplace `[[{ancien}` → `[[{nouveau}` (préfixe, attention aux faux positifs sur les noms d'archives).
5. **Mettre à jour `99-meta/_index.md`** : entrée projet/domaine + entrées d'archives.
6. **Mettre à jour `50-objectifs/pro/projets/`** si concerné.

### 6. Confirmer

Format :

```
Renommage effectué : {ancien} → {nouveau} ({kind})
{N} fichiers modifiés
{N} liens réécrits

Vérifie le résultat dans Obsidian (Graph + arborescence).
```
