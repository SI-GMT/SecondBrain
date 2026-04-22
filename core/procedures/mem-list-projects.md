# Procédure : List Projects

Objectif : afficher la liste des projets du vault mémoire avec leur état synthétique (phase actuelle, dernière session, nombre de sessions archivées). Permet à l'utilisateur d'avoir une vue d'ensemble sans parcourir `_index.md` à la main.

## Déclenchement

L'utilisateur tape `/mem-list-projects` ou exprime l'intention en langage naturel : « liste mes projets », « quels projets j'ai en mémoire ? », « montre-moi tous les projets ».

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Lire `_index.md`

Lire `{VAULT}/_index.md`. Dans la section « Projets », extraire chaque ligne au format `- [Label](projets/{slug}/historique.md)`.

- Pour chaque ligne : extraire **Label** (texte entre crochets) et **slug** (nom du dossier dans le chemin).
- Si la section est vide ou `_index.md` est absent, répondre « Aucun projet dans le vault. Commence à travailler et un archive créera l'index. » et s'arrêter.

### 2. Enrichir chaque projet

Pour chaque projet listé, lire `{VAULT}/projets/{slug}/contexte.md` :

- Extraire dans le frontmatter YAML : `phase`, `derniere-session`.
- Si `contexte.md` est absent, marquer ces deux champs comme `—`.

Puis lire `{VAULT}/projets/{slug}/historique.md` :

- Compter le nombre de lignes commençant par `- [` dans le corps (chaque ligne = une session archivée).
- Si `historique.md` est absent, compter `0`.

### 3. Afficher le tableau

Format de sortie :

```
## Projets du vault mémoire

| Slug | Label | Phase | Dernière session | Sessions |
|------|-------|-------|------------------|----------|
| {slug} | {Label} | {phase} | {derniere-session} | {N} |
| ... | ... | ... | ... | ... |

Total : {nombre de projets} projet(s), {somme des sessions} session(s) archivée(s).
```

Trier les lignes par `derniere-session` décroissante (le projet le plus récemment touché en premier). Les projets sans `contexte.md` (et donc sans `derniere-session`) apparaissent en fin de liste.

### 4. Suggérer la suite

Si un projet ressort clairement comme « en cours » (dernière session dans les 7 derniers jours), suggérer : « Tu veux reprendre `{slug}` ? » — qui déclenchera `/mem-recall {slug}`.

Sinon, ne rien suggérer.
