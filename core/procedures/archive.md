# Procédure : Archive

Objectif : archiver la session de travail en cours afin de permettre à l'utilisateur de faire `/clear` sans perdre le contexte. L'archive doit contenir tout ce qu'il faut pour reprendre dans une session future.

## Deux modes

### Mode incrémental silencieux (pendant la session)

À tout moment de la session, dès qu'un fait ou une décision important émerge et n'est pas encore présent dans `{VAULT}/projets/{nom}/contexte.md` :

- Mettre à jour **uniquement** `contexte.md` — ajouter la ligne dans la section appropriée (Décisions cumulées, Prochaines étapes, Assets actifs).
- **Ne pas** créer de fichier archive. **Ne pas** annoncer l'action à l'utilisateur sauf s'il le demande.
- Justification : `contexte.md` est un snapshot mutable, conçu pour évoluer en continu ; `archives/` est réservé aux instantanés de fin de session.

### Mode archive complet (fin de session)

Déclenché par un signal explicite :
- L'utilisateur tape `/archive` ou `/clear`.
- L'utilisateur dit en langage naturel « on s'arrête », « je pars », « on termine », « archive ».

Exécuter alors la procédure complète ci-dessous.

## Résolution du chemin du vault

Avant toute écriture, lire le fichier de configuration du kit mémoire ({{CONFIG_FILE}}) et en extraire le champ `vault`. Dans la suite de cette procédure, `{VAULT}` désigne cette valeur.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure (mode complet)

### 1. Collecter le contexte

Synthétiser depuis la conversation en cours :

- **Projet** concerné (demander à l'utilisateur si ambigu)
- **Travail effectué** : livrables produits, fichiers créés ou modifiés
- **Décisions** prises et leur justification
- **État du projet** : phase actuelle, éléments validés, éléments en cours
- **Prochaines étapes** prévues
- **Fichiers modifiés** avec chemins complets
- **Assets générés** : URLs d'images, vidéos, fichiers exportés (noter « Aucun. » si session purement logique)

### 2. Écrire le fichier archive

Chemin : `{VAULT}/archives/YYYY-MM-DD-HHhMM-{projet}-{resume-court}.md`

Format :

```markdown
---
date: YYYY-MM-DD
heure: "HH:MM"
projet: {nom}
phase: {phase actuelle}
tags: [projet/{nom}, type/archive]
---

# Session YYYY-MM-DD HHhMM — {Projet} {Résumé}

## Résumé
[2-3 phrases : objectif de la session + résultat livré]

## Travail effectué
- {action}

## Décisions
- **{Décision}** : {raison}

## État du projet
- Phase actuelle : {phase}
- Validé : {éléments terminés}
- En cours : {éléments en cours}

## Prochaines étapes
1. {étape}

## Fichiers modifiés
- `{chemin}` — {créé|modifié|supprimé}

## Assets (URLs)
{URLs des fichiers générés, ou « Aucun. »}
```

### 3. Réécrire le contexte projet

Écrire `{VAULT}/projets/{nom}/contexte.md` en écrasant intégralement le fichier existant. Ce fichier est la vue courante du projet — mutable, écrasée à chaque archivage complet. Ne pas accumuler les sessions ; c'est le rôle des archives.

Format :

```markdown
---
projet: {nom}
phase: {phase actuelle}
derniere-session: YYYY-MM-DD
tags: [projet/{nom}]
---

# {Projet} — Contexte actif

## État courant
- Phase : {phase actuelle}
- Validé : {éléments}
- En cours : {éléments}

## Décisions cumulées
- {décision} — {raison}

## Prochaines étapes
1. {étape}

## Assets actifs (URLs)
{URLs validées les plus récentes}
```

### 4. Mettre à jour l'historique projet

Ajouter une ligne en fin de `{VAULT}/projets/{nom}/historique.md` :

```
- [YYYY-MM-DD HHhMM — {résumé}](../../archives/YYYY-MM-DD-HHhMM-{projet}-{resume}.md)
```

Si le fichier n'existe pas, le créer avec le squelette :

```markdown
---
projet: {nom}
tags: [projet/{nom}]
---

# {Projet} — Historique des sessions

- [YYYY-MM-DD HHhMM — {résumé}](../../archives/YYYY-MM-DD-HHhMM-{projet}-{resume}.md)
```

### 5. Mettre à jour l'index global

Dans `{VAULT}/_index.md`, ajouter une entrée dans la section **Archives** :

```
- [YYYY-MM-DD HHhMM — {Projet} {résumé}](archives/YYYY-MM-DD-HHhMM-{projet}-{resume}.md)
```

Si c'est la première archive du projet, ajouter aussi dans la section **Projets** :

```
- [{Projet}](projets/{nom}/historique.md)
```

### 6. Confirmer

Afficher à l'utilisateur :

```
Archive créée : {VAULT}/archives/{fichier}.md
Contexte mis à jour : {VAULT}/projets/{nom}/contexte.md
Le /clear est safe — utilise /recall {projet} pour reprendre.
```
