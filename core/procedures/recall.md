# Procédure : Recall

Objectif : retrouver le contexte de travail depuis le vault après un `/clear` ou au début d'une nouvelle session. Permettre à l'utilisateur de reprendre en 30 secondes sans re-briefing manuel.

## Déclenchement

### Automatique (sans que l'utilisateur tape `/recall`)

Déclencher la procédure complète dès que l'utilisateur exprime, en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était sur X », « on reprend ? », « on s'y remet ».
- Un besoin de consulter la mémoire : « tu te rappelles de… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi… ».

Si le signal est ambigu (le projet visé n'est pas clair, par exemple), demander : « Tu veux que je charge le contexte de {projet} ? » avant d'exécuter.

### Explicite

L'utilisateur invoque la commande `/recall` avec ou sans argument. L'argument éventuel — s'il est présent dans le message utilisateur — est le nom du projet à charger.

## Résolution du chemin du vault

Avant toute lecture, lire le fichier de configuration du kit mémoire ({{CONFIG_FILE}}) et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Identifier le projet

Dans cet ordre :

1. **Argument fourni** : utiliser la valeur donnée par l'utilisateur comme nom de projet.
2. **Auto-détection** : prendre le nom du dossier de travail courant (basename de `$PWD` / `cwd`). Si ce nom correspond à un projet listé dans `{VAULT}/_index.md` (section Projets), l'utiliser.
3. **Fallback interactif** : lire `{VAULT}/_index.md`, afficher la liste des projets et demander à l'utilisateur lequel charger.
4. **Vault vide** : si `{VAULT}/_index.md` est absent ou ne contient aucun projet, répondre « Aucune session trouvée. Mémoire initialisée — {VAULT}/_index.md est prêt. Décris ce sur quoi tu travailles et on commence. » puis s'arrêter.

### 2. Charger l'historique

Lire `{VAULT}/projets/{nom}/historique.md` pour voir le fil chronologique des sessions.

Si le fichier n'existe pas, répondre « Aucune session trouvée pour {projet}. » et s'arrêter.

### 3. Charger le contexte (voie rapide)

**Si `{VAULT}/projets/{nom}/contexte.md` existe** : le lire en priorité. C'est l'état courant synthétisé (~25 lignes). Voie rapide, 2× moins de tokens.

**Sinon** : lire la dernière archive listée dans `historique.md`. Extraire : état du projet, décisions, prochaines étapes, assets.

### 4. Présenter le briefing

Format de réponse :

```
## Reprise — {Projet}

**Dernière session** : {date} — {résumé}
**Phase actuelle** : {phase}

### État
- Validé : …
- En cours : …

### Décisions clés
- …

### Prochaines étapes
1. …
2. …

### Assets disponibles
- {URLs ou « Aucun »}
```

### 5. Proposer la suite

Demander : « On reprend à l'étape {X} ? »

Si l'utilisateur confirme, lire les fichiers projet nécessaires et démarrer le travail.
