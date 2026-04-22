# Procédure : Rollback Archive

Objectif : annuler la dernière archive d'un projet (ou de l'ensemble du vault) en cas de fausse manip ou d'archivage prématuré. Supprime le fichier archive, retire la ligne correspondante de `historique.md` et de `_index.md`.

**Limite connue** : le `contexte.md` du projet est **écrasé** à chaque archive complet. Le rollback ne restaure **pas automatiquement** l'ancien `contexte.md` — l'archive supprimée contenait elle-même le snapshot du moment. L'utilisateur est averti et peut relancer `/mem-recall {projet}` pour régénérer un contexte à partir de l'avant-dernière archive (ou des suivantes qui subsistent).

## Déclenchement

L'utilisateur tape `/mem-rollback-archive [projet]` ou exprime l'intention en langage naturel : « annule la dernière archive », « oublie la dernière session », « rollback l'archive de X ».

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Identifier l'archive cible

Deux cas :

**Cas A — un projet est spécifié** (`/mem-rollback-archive iris-etl`) :

- Lire `{VAULT}/projets/{projet}/historique.md`.
- Prendre la dernière ligne d'archive du fichier (ligne la plus en bas, qui est aussi la plus récente selon le format d'écriture défini dans `mem-archive.md`).
- Extraire le chemin d'archive référencé dans le lien.

**Cas B — aucun projet spécifié** :

- Lister tous les fichiers de `{VAULT}/archives/*.md`, trier par nom (l'horodatage en préfixe est ISO donc un tri alphabétique décroissant donne le plus récent).
- Prendre le plus récent.
- Lire son frontmatter pour identifier le projet concerné (`projet: {slug}`).

Si aucune archive n'existe, répondre « Aucune archive à annuler. » et s'arrêter.

### 2. Afficher ce qui va être supprimé

**Avant toute suppression**, afficher clairement :

```
Archive à annuler : {chemin complet}
Projet : {slug}
Date : {date extraite du frontmatter}
Résumé : {titre H1 ou section Résumé, première ligne}
```

**Exécuter ensuite directement sans demander confirmation supplémentaire** — l'utilisateur a invoqué la commande en connaissance de cause.

### 3. Supprimer le fichier archive

Exécuter :

```powershell
Remove-Item -Path "{chemin absolu de l'archive}" -Force
```

### 4. Retirer la ligne de `historique.md`

Lire `{VAULT}/projets/{projet}/historique.md`. Supprimer la ligne qui contient le lien vers l'archive supprimée (comparaison par nom de fichier de l'archive). Réécrire le fichier.

Si après suppression l'historique ne contient plus aucune ligne d'archive, laisser le fichier avec juste son frontmatter et son titre H1 — ne pas le supprimer.

### 5. Retirer la ligne de `_index.md`

Lire `{VAULT}/_index.md`. Dans la section « Archives », supprimer la ligne qui contient le lien vers l'archive supprimée. Réécrire le fichier.

**Ne pas** toucher à la section « Projets » (le projet reste dans l'index même si son historique devient vide).

### 6. Avertir sur `contexte.md`

Afficher :

```
Archive annulée : {chemin}

Fichiers modifiés :
- {VAULT}/archives/{nom}.md (supprimé)
- {VAULT}/projets/{projet}/historique.md (ligne retirée)
- {VAULT}/_index.md (ligne retirée)

⚠ Attention : {VAULT}/projets/{projet}/contexte.md n'a PAS été restauré à son état d'avant.
L'archive que tu viens de supprimer contenait elle-même le snapshot de ce moment — il est perdu
sauf si tu as une copie git ou Obsidian. Pour régénérer un contexte à partir de l'avant-dernière
archive, lance : /mem-recall {projet}
```
