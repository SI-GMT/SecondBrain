# Procédure : Digest (v0.5 brain-centric)

Objectif : synthèse des N dernières archives d'un projet OU domaine, ou agrégation par zone (objectifs, principes, etc.). Utile pour voir les arcs majeurs sans relire chaque archive. **Lecture seule** — n'écrit rien dans le vault.

## Déclenchement

L'utilisateur tape `/mem-digest {slug} [N]` ou exprime l'intention en langage naturel : « résume-moi les N dernières sessions de X », « fais un digest de X », « donne-moi le fil rouge de X », « état des lieux des objectifs ouverts ».

Options reconnues :
- `{slug}` : slug du projet ou domaine. Obligatoire si pas de `--zone`.
- `{N}` : nombre d'archives à synthétiser. Défaut `5`.
- `--zone X` : digest sur une zone entière au lieu d'un projet. Ex : `--zone objectifs --scope pro` = état des lieux des objectifs pro.
- `--scope perso|pro|all` : filtre par scope.
- `--depuis YYYY-MM-DD` : ne considère que les archives postérieures.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure — mode projet/domaine (par défaut)

### 1. Récupérer les arguments

- `{slug}` : slug du projet ou domaine. Obligatoire. Si absent, demander à l'utilisateur via `/mem-list`.
- `{N}` : défaut 5.

### 2. Identifier kind (projet ou domaine)

Chercher d'abord dans `{VAULT}/10-episodes/projets/{slug}/`, puis dans `{VAULT}/10-episodes/domaines/{slug}/`. Si introuvable, répondre « Slug `{slug}` introuvable. Utilise `/mem-list` pour voir les disponibles. » et s'arrêter.

### 3. Charger l'historique

Lire `{VAULT}/10-episodes/{kind}/{slug}/historique.md`. Extraire les N dernières lignes d'archive (trier par date décroissante).

### 4. Lire les archives sélectionnées

Pour chaque archive : lire le contenu et extraire **Résumé**, **Décisions**, **Prochaines étapes**. Ignorer **Travail effectué** et **Fichiers modifiés** (trop bas niveau pour un digest).

### 5. Charger les atomes dérivés (nouveau v0.5)

Pour chaque archive sélectionnée, suivre le champ `derived_atoms` du frontmatter. Lister les principes, objectifs, connaissances dérivés des archives — ils enrichissent la synthèse.

### 6. Synthétiser

Produire une synthèse structurée :

- **Arcs majeurs** : grandes transitions (nouvelle phase, pivot, livraison) à travers les résumés successifs.
- **Décisions structurantes** : décisions ayant eu des conséquences sur plusieurs sessions.
- **Atomes dérivés** : nouveaux principes / objectifs / concepts dégagés sur la période.
- **Dérive des prochaines étapes** : ce qui a été fait vs ce qui a été abandonné/décalé.
- **État final** : synthèse de où on en est maintenant.

### 7. Afficher le rapport

Format :

```
## Digest — {slug} ({kind}) — {N} dernières sessions

Période : {date début} → {date fin}

### Arcs majeurs
- ...

### Décisions structurantes
- ...

### Atomes dérivés ({N})
- [{type}] {titre} → [[lien]]

### Évolution des prochaines étapes
- Annoncées : ...
- Faites : ...
- Décalées / abandonnées : ...

### État final
{snapshot synthétique}
```

## Procédure — mode zone (`--zone X`)

### 1. Lister les fichiers de la zone

Énumérer récursivement `{VAULT}/{NN-zone}/`. Filtrer par scope si applicable.

### 2. Synthétiser

Selon la zone :
- **principes** : grouper par `force` (ligne-rouge / heuristique / preference) puis par catégorie. Compter par groupe. Lister les principes les plus récents.
- **objectifs** : grouper par `statut` (ouvert / en-cours / atteint / abandonne). Compter par groupe. Pour les ouverts/en-cours, trier par échéance.
- **personnes** : grouper par catégorie (collègues / clients / famille / amis). Lister les personnes avec interaction récente (< 30 jours).
- **knowledge** : grouper par famille (metier / tech / vie / methodes). Compter par groupe.
- **procedures** : grouper par catégorie. Lister les plus récentes.
- **autres** : liste plate, triée par date décroissante.

### 3. Afficher

Format adapté à la zone, toujours commencer par un compteur global et les groupements.
