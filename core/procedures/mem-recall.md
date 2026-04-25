# Procédure : Recall (v0.5 brain-centric)

Objectif : retrouver le contexte de travail depuis le vault après un `/clear` ou au début d'une nouvelle session. Permettre à l'utilisateur de reprendre en 30 secondes sans re-briefing manuel. En v0.5, le rappel charge non seulement les archives de session mais aussi les **principes actifs**, **objectifs ouverts** et **personnes-clés** rattachés au projet/domaine — pour donner un contexte complet, pas juste épisodique.

## Déclenchement

### Automatique (sans que l'utilisateur tape `/mem-recall`)

Déclencher la procédure complète dès que l'utilisateur exprime, en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était sur X », « on reprend ? », « on s'y remet ».
- Un besoin de consulter la mémoire : « tu te rappelles de… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi… ».

Si le signal est ambigu (le projet ou domaine visé n'est pas clair), demander : « Tu veux que je charge le contexte de {nom} ? » avant d'exécuter.

### Explicite

L'utilisateur invoque `/mem-recall` avec ou sans argument. L'argument éventuel est le nom du projet ou domaine à charger.

Options reconnues :
- `--scope perso|pro|all` : filtre les éléments rattachés selon le scope. Défaut : `all`.
- `--zone {liste}` : limite le chargement à certaines zones (par défaut : toutes les zones rattachées au projet/domaine).

## Résolution du chemin du vault

Avant toute lecture, lire le fichier de configuration du kit mémoire ({{CONFIG_FILE}}) et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur. Lire aussi `default_scope` du même fichier pour connaître la valeur par défaut du scope.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Identifier le projet ou domaine

Dans cet ordre :

1. **Argument fourni** : utiliser la valeur donnée par l'utilisateur. Le router cherche d'abord dans `{VAULT}/10-episodes/projets/{slug}/`, puis dans `{VAULT}/10-episodes/domaines/{slug}/`.
2. **Auto-détection** : prendre le basename du `cwd`. Si ce nom correspond à un slug existant dans `projets/` ou `domaines/`, l'utiliser.
3. **Fallback interactif** : lire `{VAULT}/99-meta/_index.md`, afficher la liste des projets ET domaines, et demander à l'utilisateur lequel charger.
4. **Vault vide ou aucun projet/domaine** : répondre « Aucun projet/domaine trouvé. Mémoire initialisée — {VAULT}/99-meta/_index.md est prêt. Décris ce sur quoi tu travailles et on commence. » puis s'arrêter.

Dans la suite, `{kind}` désigne `projets` ou `domaines`, et `{slug}` le slug identifié.

### 2. Charger le contexte courant (voie rapide)

**Si `{VAULT}/10-episodes/{kind}/{slug}/contexte.md` existe** : le lire en priorité. C'est l'état courant synthétisé (snapshot mutable). Voie rapide.

**Sinon** : lire la dernière archive listée dans `historique.md`. Extraire : état du projet, décisions, prochaines étapes, assets.

### 3. Charger l'historique

Lire `{VAULT}/10-episodes/{kind}/{slug}/historique.md` pour voir le fil chronologique des sessions.

### 4. Charger les éléments rattachés (nouveau v0.5)

Le projet/domaine se projette **transversalement** dans plusieurs zones via les tags `projet/{slug}` ou `domaine/{slug}`. Charger :

| Zone | Filtre | Pourquoi |
|---|---|---|
| `40-principes/` | tag `projet/{slug}` ou `domaine/{slug}`, **filtré par scope** si `--scope` | Principes actifs nés dans ce projet ou s'y appliquant — le LLM doit les respecter pendant la session. |
| `50-objectifs/` | tag `projet/{slug}` + `statut: ouvert\|en-cours` | Objectifs actifs — pour orienter les prochaines étapes. |
| `60-personnes/` | mentionnés dans les 3 dernières archives ou liés via tag projet | Personnes-clés du projet — utile pour conserver le contexte relationnel. |

Implémentation : grep sur `{VAULT}/40-principes/`, `{VAULT}/50-objectifs/`, `{VAULT}/60-personnes/` pour les tags pertinents. Limiter à 5 items par zone si trop nombreux (afficher « +N autres » en fin).

### 5. Présenter le briefing

Format de réponse :

```
## Reprise — {Projet ou Domaine} ({kind})

**Dernière session** : {date} — {résumé}
**Phase actuelle** : {phase}
**Scope** : {perso|pro}

### État
- Validé : …
- En cours : …

### Décisions clés
- …

### Principes actifs ({N})
- {force} — {titre court} → [[lien]]
- …

### Objectifs ouverts ({N})
- [{horizon}] {titre} (échéance: {date}) → [[lien]]
- …

### Personnes-clés
- {nom} ({rôle}) — dernière interaction {date} → [[lien]]

### Prochaines étapes
1. …
2. …

### Assets disponibles
- {URLs ou « Aucun »}
```

Adapter le briefing au scope demandé : si `--scope perso`, masquer les éléments `pro` et inversement.

### 6. Proposer la suite

Demander : « On reprend à l'étape {X} ? »

Si l'utilisateur confirme, lire les fichiers projet nécessaires et démarrer le travail.
