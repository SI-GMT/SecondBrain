# Procédure : Digest

Objectif : synthèse des N dernières archives d'un projet. Utile quand un projet traîne sur beaucoup de sessions et qu'on veut voir les arcs majeurs sans relire chaque archive individuellement. **Lecture seule** — n'écrit rien dans le vault.

## Déclenchement

L'utilisateur tape `/mem-digest {projet} [N]` ou exprime l'intention en langage naturel : « résume-moi les N dernières sessions de X », « fais un digest de X », « donne-moi le fil rouge de X ».

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Récupérer les arguments

- `{projet}` : slug du projet. Obligatoire.
  - Si absent, lire `{VAULT}/_index.md` et demander à l'utilisateur : « Sur quel projet veux-tu un digest ? » + liste.
- `{N}` : nombre d'archives à synthétiser. Optionnel, défaut `5`.
  - Si `N > nombre total d'archives`, prendre toutes les archives disponibles et le mentionner dans le rapport.

### 2. Charger l'historique

Lire `{VAULT}/projets/{projet}/historique.md`.

- Si absent : répondre « Projet `{projet}` introuvable ou sans historique. Utilise `/mem-list-projects` pour voir les projets disponibles. » et s'arrêter.
- Extraire les lignes d'archive et les trier par date décroissante (plus récent d'abord).
- Sélectionner les N premières.

### 3. Lire les archives sélectionnées

Pour chaque archive sélectionnée : lire son contenu et extraire les sections **Résumé**, **Décisions** et **Prochaines étapes**. Ignorer le détail de **Travail effectué** et **Fichiers modifiés** (trop bas niveau pour un digest).

### 4. Synthétiser

Produire une synthèse structurée qui met en évidence :

- **Arcs majeurs** : les grandes transitions (nouvelle phase, pivot, livraison) identifiables à travers les résumés successifs.
- **Décisions structurantes** : les décisions qui ont eu des conséquences sur plusieurs sessions suivantes (pas chaque petite décision).
- **Dérive des prochaines étapes** : ce qui était annoncé comme prochaine étape et qui a effectivement été fait vs. ce qui a été abandonné ou décalé.
- **État final** : synthèse de où on en est maintenant (s'inspire du `contexte.md` mais avec le recul des N dernières sessions).

### 5. Afficher le rapport

Format :

```
## Digest — {Projet} ({N} dernières sessions)

**Période couverte** : {date plus ancienne} → {date plus récente}

### Arcs majeurs
1. {Arc 1 avec dates approximatives}
2. ...

### Décisions structurantes
- **{décision}** ({date}) — {raison synthétique et conséquence}
- ...

### Dérive des prochaines étapes
- Annoncé « X » le {date}, réalisé le {date}.
- Annoncé « Y », reporté / abandonné (apparaît dans {n} sessions successives sans action).
- ...

### État actuel
{3-5 phrases synthétiques sur la situation actuelle}

---
Archives lues : {liste des chemins, à titre de traçabilité}
```

### 6. Suggérer la suite

Si la dérive révèle des prochaines étapes abandonnées, demander : « Tu veux qu'on reprenne `{étape abandonnée}` ou qu'on l'enlève du `contexte.md` ? »
