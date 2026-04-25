# Procédure : Archive (v0.5 brain-centric)

Objectif : archiver la session de travail en cours afin de permettre à l'utilisateur de faire `/clear` sans perdre le contexte. L'archive doit contenir tout ce qu'il faut pour reprendre dans une session future.

En v0.5, `mem-archive` délègue au **router sémantique** avec hint de zone forcée `episodes` + source `vecu`. Le router peut segmenter en plusieurs atomes (typiquement : 1 archive principale + N atomes dérivés en `40-principes`, `50-objectifs`, `20-knowledge` selon ce que la session a produit).

## Deux modes

### Mode incrémental silencieux (pendant la session)

À tout moment, dès qu'un fait ou une décision important émerge et n'est pas encore présent dans le `contexte.md` cible :

- Mettre à jour **uniquement** `contexte.md` du projet/domaine courant — ajouter la ligne dans la section appropriée (Décisions cumulées, Prochaines étapes, Assets actifs).
- **Ne pas** créer de fichier archive. **Ne pas** annoncer l'action à l'utilisateur sauf s'il le demande.
- Justification : `contexte.md` est un snapshot mutable, conçu pour évoluer en continu ; les `archives/` sont réservées aux instantanés de fin de session.

### Mode archive complet (fin de session)

Déclenché par signal explicite :
- L'utilisateur tape `/mem-archive` ou `/clear`.
- L'utilisateur dit en langage naturel « on s'arrête », « je pars », « on termine », « archive ».

Exécuter alors la procédure complète ci-dessous.

## Résolution du chemin du vault

Avant toute écriture, lire le fichier de configuration du kit mémoire ({{CONFIG_FILE}}) et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur. Lire aussi `default_scope` pour la valeur par défaut du scope.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Détection du projet/domaine cible

Pour déterminer où archiver, identifier le projet OU domaine :

1. Si l'utilisateur a fourni `--projet {slug}` ou `--domaine {slug}` → utiliser.
2. Sinon, basename du `cwd` → matcher contre `{VAULT}/10-episodes/projets/` puis `{VAULT}/10-episodes/domaines/`.
3. Si pas de match, demander à l'utilisateur : « Sur quel projet/domaine archiver cette session ? » + liste via `/mem-list`.
4. Si réponse = nouveau slug, le créer (créer `{VAULT}/10-episodes/projets/{slug}/` avec `contexte.md` + `historique.md` squelettes).

Détecter aussi la branche Git courante :
- Mainlines (`main`, `master`, `recette`, `dev`, `hotfix/*`, `release/*`) → archive au niveau projet global.
- Autres branches → archive en feature : `{VAULT}/10-episodes/projets/{slug}/features/{branche-san}/archives/`. Sanitisation `/` → `--`.

## Procédure (mode complet)

### 1. Collecter le contexte de session

Synthétiser depuis la conversation en cours :

- Projet/domaine concerné (résolu ci-dessus).
- Travail effectué (livrables, fichiers créés/modifiés).
- Décisions prises et leur justification.
- État actuel : phase, validé, en cours.
- Prochaines étapes prévues.
- Fichiers modifiés avec chemins complets.
- Assets générés (URLs ou « Aucun »).
- **Atomes dérivés à extraire** : si la session a fait émerger des principes, objectifs, ou connaissances stables, les identifier pour que le router puisse les ranger dans leurs zones dédiées.

### 2. Construire le contenu pour le router

Préparer un Markdown structuré qui contient :

- Une **section principale** (titre `# Session ...`) qui sera l'archive de session vécue (zone episodes).
- Des **sections dérivées** (titres `## Principe : ...`, `## Objectif : ...`, `## Concept : ...`) optionnelles, une par atome dérivé identifié.

Cette structure permet au router de segmenter facilement en plusieurs atomes via délimiteurs Markdown.

### 3. Invoquer le router

Appeler le router sémantique avec :
- `Contenu` : le Markdown structuré.
- `Hint zone` : `episodes` (force la section principale en zone episodes).
- `Hint source` : `vecu`.
- `Métadonnées` : projet/domaine résolu, branche, scope.

{{INCLUDE _router}}

Le router :
- Écrit l'archive principale dans `{VAULT}/10-episodes/{kind}/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{sujet}.md`.
- Pour chaque atome dérivé, classe via la cascade d'heuristiques (les sections `## Principe :` vont en `40-principes`, etc.).
- Crée les liens bidirectionnels `derived_atoms` ↔ `contexte_origine`.

### 4. Réécrire le contexte cible

Après l'écriture du router, **toujours** réécrire intégralement `{VAULT}/10-episodes/{kind}/{slug}/contexte.md` pour refléter le snapshot courant.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Format de `contexte.md` :

```markdown
---
zone: episodes
kind: {projet|domaine}
slug: {slug}
scope: {perso|pro}
collectif: false
phase: {phase actuelle}
derniere-session: YYYY-MM-DD
tags: [zone/episodes, kind/*, {projet|domaine}/{slug}, scope/*]
---

# {Slug} — Contexte actif

## État courant
- Phase : {phase}
- Validé : {éléments terminés}
- En cours : {éléments en cours}

## Décisions cumulées
- {décision} — {raison}

## Prochaines étapes
1. {étape}

## Assets actifs (URLs)
{URLs validées}
```

### 5. Mettre à jour l'historique

Le router a déjà ajouté la ligne d'archive dans `historique.md` (cf. R7.5 du bloc router). Pas d'action supplémentaire ici.

### 6. Mettre à jour l'index global

Le router a déjà ajouté l'entrée dans `{VAULT}/99-meta/_index.md`. Pas d'action supplémentaire ici.

### 7. Confirmer

Afficher à l'utilisateur :

```
Archive créée : {chemin de l'archive principale}
{N} atome(s) dérivé(s) créé(s) dans : {liste des zones touchées}
Contexte mis à jour : {chemin contexte.md}

Le /clear est safe — utilise /mem-recall {slug} pour reprendre.
```
