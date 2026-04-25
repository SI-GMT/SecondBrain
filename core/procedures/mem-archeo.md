# Procédure : Archeo (v0.5 brain-centric)

Objectif : **reconstituer l'historique d'un dépôt Git existant** sous forme d'archives datées, **et d'atomes dérivés** (principes, concepts techniques) extraits de chaque jalon. Permet de démarrer un projet dans le kit mémoire avec un contexte riche reconstruit a posteriori.

En v0.5, `mem-archeo` ne produit plus une archive monolithique par jalon — il segmente via le router, qui peut générer plusieurs atomes répartis dans plusieurs zones (1 archive en `episodes` + N principes en `40-principes` + N concepts en `20-knowledge`).

## Déclenchement

L'utilisateur tape `/mem-archeo [chemin-du-dépôt]` ou exprime l'intention en langage naturel : « fais une rétro Git de ce projet », « reconstitue l'historique », « archéo sur ce repo ».

Arguments :
- `{chemin-du-dépôt}` (optionnel, défaut = CWD) : chemin absolu vers un dépôt Git local.
- `--projet {slug}` : force le projet cible.
- `--niveau {tags|releases|merges|commits}` : force le niveau de granularité.
- `--depuis YYYY-MM-DD` / `--jusqu-a YYYY-MM-DD` : bornes temporelles.
- `--fenetre {jour|semaine|mois}` : taille de regroupement pour niveau `commits`.
- `--dry-run` : liste les jalons qui seraient ingérés, sans écrire.
- `--no-confirm` : passe au router en mode fluide même sur multi-atomes.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Valider le dépôt source

- Vérifier que `{chemin-du-dépôt}` est un dépôt Git (`git -C {chemin} rev-parse --git-dir`).
- Sinon, arrêter avec message clair.

### 2. Résoudre le projet/domaine cible

Par priorité :
1. `--projet {slug}` ou `--domaine {slug}` explicite.
2. Match du basename du dépôt sur les slugs existants dans `{VAULT}/10-episodes/projets/` puis `domaines/`.
3. Demander à l'utilisateur (avec `/mem-list` à l'appui).
4. Si nouveau slug → créer la structure `{VAULT}/10-episodes/projets/{slug}/contexte.md` + `historique.md` + `archives/`.

### 3. Détecter le niveau de granularité

Si `--niveau` non fourni, choisir automatiquement (premier qui retourne >0) :

1. **Tags semver** (`v*.*.*`) → 1 archive par tag.
2. **Releases GitHub** (via `gh release list` si dispo) → 1 archive par release.
3. **Merges sur mainline** (`git log --merges main`) → 1 archive par merge.
4. **Fenêtres de commits** (semaine/mois) → 1 archive par fenêtre.

Afficher le choix à l'utilisateur et demander confirmation avant de poursuivre.

### 4. Pour chaque jalon : préparer le contenu

Pour chaque jalon (tag, release, merge, fenêtre) dans la fenêtre temporelle `--depuis`/`--jusqu-a` :

#### a. Vérifier idempotence

Chercher dans le vault un atome existant avec :
- `source: archeo-git`
- `source_jalon: {tag|sha|range}` égal au jalon courant.

Si trouvé, **skip silencieux** (déjà ingéré) sauf si le jalon a changé (ex: tag déplacé) — dans ce cas, créer une révision avec `previous_atom: [[ancien]]`.

#### b. Extraire les informations du jalon

Selon le niveau :
- **Tag/release** : message du tag, contenu de la release note GitHub (`gh release view`), commit SHA, date, auteur principal, fichiers modifiés (diff stats).
- **Merge** : message de merge, branche source, fichiers, tickets référencés (regex `[A-Z]+-\d+` pour Jira, `#\d+` pour PR).
- **Fenêtre commits** : agrégation des messages de commits dans la fenêtre, fichiers touchés, contributeurs.

Enrichir avec :
- **Fichiers IA racine** au moment du commit : `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `README.md`, `contexte.md`, `historique.md` si présents (lire à `git show {sha}:{fichier}`).
- **Tickets Jira/Linear** : extraire les clés du message + référence.
- **PR liés** : `gh pr view {numero}` si disponible.

#### c. Construire le contenu pour le router

Préparer un Markdown structuré avec délimiteurs Markdown pour faciliter la segmentation par le router :

```
# Archive jalon — {tag|sha|range}

[Section principale — événement daté à archiver en episodes]

## Principe : [titre court] [si dégagé]

[Si le jalon a fait émerger un principe explicite, le formuler ici]

## Concept : [titre court] [si dégagé]

[Si le jalon introduit un concept technique réutilisable, le formuler ici]
```

### 5. Invoquer le router pour ce jalon

Appeler le router avec :
- `Contenu` : Markdown structuré du jalon.
- `Hint zone` : `episodes` (force la section principale).
- `Hint source` : `archeo-git`.
- `Métadonnées` : projet/domaine résolu, **`source_jalon: {tag|sha|range}`**, `commit_sha`, scope.

{{INCLUDE _router}}

Le router :
- Écrit l'archive principale dans `{VAULT}/10-episodes/{kind}/{slug}/archives/`.
- Pour chaque section dérivée (`## Principe :`, `## Concept :`), classe via la cascade.
- Crée les liens bidirectionnels.
- Vérifie l'idempotence via `source_jalon + type + sujet` (cf. R10 du bloc router).

### 6. Boucle sur tous les jalons

Si `--dry-run` : afficher la liste des jalons qui seraient ingérés (avec atomes dérivés prévus) + total estimé. Demander confirmation pour passer en `--apply`.

Sinon : itérer sur tous les jalons. Le router gère la confirmation utilisateur en mode safe (par défaut), ou écriture directe si `--no-confirm`.

### 7. Rapport final

Synthèse globale : N jalons traités, N archives créées, N atomes dérivés (par zone), N skips (idempotence).
