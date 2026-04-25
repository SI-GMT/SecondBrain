## Router sémantique — procédure d'ingestion

Le router est le composant central d'ingestion du vault SecondBrain v0.5. Il est invoqué par tous les skills d'ingestion (`mem`, `mem-archive`, `mem-doc`, `mem-archeo`, `mem-archeo-atlassian`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`) avec un éventuel **hint de zone forcée** transmis par le skill appelant.

### R1. Réception et préformatage

Le router reçoit en entrée :

- **Contenu** : texte Markdown (peut contenir plusieurs atomes hétérogènes).
- **Hint de zone forcée** (optionnel) : valeur parmi `episodes`, `knowledge`, `procedures`, `principes`, `objectifs`, `personnes`, `cognition`. Si présent, **bypass de la cascade d'heuristiques** pour l'ensemble du contenu (mais la segmentation peut quand même produire plusieurs atomes au sein de la zone).
- **Hint de source** (optionnel) : `vecu | doc | archeo-git | archeo-atlassian | manuel`. Renseigné par le skill appelant. Défaut : `manuel`.
- **Métadonnées de contexte** (optionnel) : projet/domaine courant détecté par l'adapter (CWD), branche Git, scope par défaut (`default_scope` lu dans `~/.claude/memory-kit.json`).

Préparation :

1. Normaliser le contenu (LF, UTF-8 sans BOM — les adapters l'ont déjà fait, mais on revérifie).
2. Établir le **scope par défaut** : valeur de `default_scope` du `memory-kit.json` (ou `pro` si absent), surchargée par `--scope perso|pro` éventuel passé par l'utilisateur.
3. Établir la **date / heure courante** au format `YYYY-MM-DD` / `HH:MM`.

### R2. Segmentation en atomes

Un input peut contenir un seul atome (cas le plus fréquent : « ne jamais X » → un principe unique) ou plusieurs (ex: une session de dev qui livre une décision + 2 principes + 1 connaissance).

Heuristiques de segmentation, à appliquer dans l'ordre :

1. **Délimiteurs explicites** : `---` Markdown, ou puces de liste de premier niveau séparées par des lignes vides → chaque section est un atome candidat.
2. **Titres Markdown** (`#`, `##`) : chaque section sous un titre est un atome candidat.
3. **Verbes / structures rhétoriques distinctes** dans un même paragraphe : « décision », « règle », « note », « contact », « TODO » → atomes candidats même sans délimiteur explicite.
4. **Aucune segmentation détectée** : le contenu entier = un seul atome.

Pour chaque atome candidat, conserver :
- Son **texte brut** (préservé tel quel, le LLM ne reformule pas).
- Son **contexte parent** (le reste du contenu, pour donner du contexte au classement).

Limite : si le router détecte plus de **8 atomes** dans un même input, considérer que la segmentation est suspecte → tout regrouper en un seul atome envoyé en `00-inbox/` avec un message à l'utilisateur (« Segmentation > 8 atomes refusée, contenu placé en inbox pour reclassement manuel »).

### R3. Cascade d'heuristiques de classement

Pour chaque atome (et si pas de hint de zone forcée), appliquer la cascade en ordre de priorité — **premier match gagne** :

| Priorité | Indice détecté | Zone cible | Type |
|---|---|---|---|
| 1 | Hint de zone forcée par le skill appelant | Zone forcée | (selon zone) |
| 2 | Événement daté au passé + contexte projet/domaine identifiable (« hier », « aujourd'hui », « le DD/MM », verbes au passé concrets, hint `source: vecu\|archeo-*`) | `10-episodes/{kind}/{slug}/archives/` | `archive` |
| 3 | Verbe impératif ou structure étape-par-étape (« comment faire », « pour X : étape 1, 2, 3 », « playbook ») | `30-procedures/{scope}/{categorie}/` | `procedure` |
| 4 | Règle / contrainte / valeur (« toujours », « jamais », « privilégier », « éviter », « ligne rouge », « ne pas ») | `40-principes/{scope}/{domaine}/` | `principe` |
| 5 | Intention future + horizon temporel (« objectif », « vise », « d'ici X », date-échéance, « ambition ») | `50-objectifs/{scope}/{horizon}/` | `objectif` |
| 6 | Fiche personne (nom propre + rôle/relation, « collègue », « client », « ami ») | `60-personnes/{scope}/{categorie}/` | `personne` |
| 7 | Production non verbale ou référence à schéma (Excalidraw, métaphore explicite, mention `.canvas`/`.excalidraw`) | `70-cognition/{type}/` | `schema\|metaphore\|moodboard\|sketch` |
| 8 | Fait / concept / définition / synthèse stable (description, glossaire, fiche de connaissance) | `20-knowledge/{famille}/{sous-domaine}/` | `concept\|fiche\|synthese\|glossaire\|reference` |
| 9 | Aucun match clair, ambigu | `00-inbox/` | (laissé vide) |

**Détection du scope** par indices lexicaux :

| Indice | Scope déduit |
|---|---|
| « mon équipe », « client », « collègue », « projet de travail », nom de société | `pro` |
| « ma famille », « ma santé », « mon enfant », « mes vacances » | `perso` |
| Aucun indice clair | `default_scope` du `memory-kit.json` (défaut `pro`) |

**Détection du projet/domaine** : si l'atome mentionne explicitement un slug de projet existant (lister via `{VAULT}/10-episodes/projets/` et `{VAULT}/10-episodes/domaines/`), associer. Sinon, utiliser le projet/domaine du **contexte d'invocation** (CWD ou métadonnées passées par l'adapter). Sinon, laisser sans rattachement (sauf pour zone `episodes` qui exige toujours un `kind` + slug).

### R4. Enrichissement du frontmatter

Pour chaque atome classé, construire un frontmatter conforme à la zone cible (cf. `_frontmatter-universel.md` pour les champs universels, et la section 7 du document de cadrage `docs/architecture/brain-architecture-v0.5.md` pour les champs propres à chaque zone).

Champs systématiquement renseignés :
- `date` : date courante.
- `zone` : zone cible.
- `scope` : `perso` ou `pro`.
- `collectif: false` (toujours à l'écriture initiale).
- `modality: left` (par défaut), `right` uniquement si zone = `cognition`.
- `tags` : liste reflétant le frontmatter (`zone/*`, `scope/*`, `kind/*` si episodes, `type/*`, etc. — cf. section 6 du doc de cadrage).

Champs spécifiques à la zone (voir section 7 du doc) :
- **episodes** : `kind`, `projet` ou `domaine`, `heure`, `source`, `derived_atoms` (vide à la création, rempli si atomes dérivés).
- **knowledge** : `type` (`concept|fiche|synthese|glossaire|reference`), `sources: []`.
- **procedures** : `type: procedure`, `etapes`, `duree_estimee`, `outils`.
- **principes** : `force` (`ligne-rouge|heuristique|preference`), `contexte_origine` (lien vers archive fondatrice si dérivé), `projet`.
- **objectifs** : `horizon` (`court|moyen|long`), `echeance`, `statut: ouvert`, `projet`.
- **personnes** : `nom`, `role`, `organisation`, `contact`, `derniere_interaction`, `sensitive: true`.
- **cognition** : `type` (`schema|metaphore|moodboard|sketch`), `projet`.

### R5. Construction du chemin cible

Le chemin du fichier suit la zone et la sous-arborescence :

| Zone | Chemin |
|---|---|
| `inbox` | `{VAULT}/00-inbox/{YYYY-MM-DD}-{slug-sujet}.md` |
| `episodes` (projet) | `{VAULT}/10-episodes/projets/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{sujet-court}.md` |
| `episodes` (domaine) | `{VAULT}/10-episodes/domaines/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{sujet-court}.md` |
| `knowledge` | `{VAULT}/20-knowledge/{famille}/{sous-domaine}/{slug-sujet}.md` |
| `procedures` | `{VAULT}/30-procedures/{scope}/{categorie}/{slug-sujet}.md` |
| `principes` | `{VAULT}/40-principes/{scope}/{domaine}/{slug-sujet}.md` |
| `objectifs` (perso) | `{VAULT}/50-objectifs/perso/{categorie}/{slug-sujet}.md` |
| `objectifs` (pro projet) | `{VAULT}/50-objectifs/pro/projets/{slug-projet}/{slug-sujet}.md` |
| `personnes` | `{VAULT}/60-personnes/{scope}/{categorie}/{slug-nom}.md` |
| `cognition` | `{VAULT}/70-cognition/{type}/{slug-sujet}.md` |

`{slug-sujet}` est dérivé du sujet de l'atome : lowercase, accents retirés, espaces → `-`, max 60 caractères, caractères FS-invalides (`/\:*?"<>|`) supprimés.

Si le dossier parent n'existe pas, le créer avant l'écriture (`New-Item -ItemType Directory -Force` ou équivalent).

### R6. Plan d'ingestion et mode safe conditionnel

**Si segmentation = 1 atome** (cas le plus fréquent) → **mode fluide** : écrire directement, puis afficher le rapport.

**Si segmentation > 1 atome** → **mode safe** : afficher d'abord le **plan d'ingestion** et attendre la confirmation utilisateur :

```
Plan d'ingestion (N atomes détectés) :
  [1] {résumé court de l'atome 1}
      → {chemin cible 1}  (zone: {zone}, source: {source}, scope: {scope})
  [2] {résumé court de l'atome 2}
      → {chemin cible 2}  (zone: {zone}, source: {source}, scope: {scope})
  ...

Continuer ? [o/n/e(dit)]
```

- `o` (oui) → écrire tous les atomes selon le plan.
- `n` (non) → annuler, ne rien écrire.
- `e` (edit) → permettre à l'utilisateur de modifier la classification d'un atome (changer zone, scope, ou rejeter cet atome) avant écriture.

**Flags utilisateur** :
- `--no-confirm` : force le mode fluide même sur multi-atomes (utile en batch / scripts).
- `--dry-run` : force le mode safe sans écriture (inspection seule du plan, retour `n` automatique après affichage).

### R7. Écriture

Pour chaque atome accepté du plan :

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes par atome :

1. **Construire le contenu Markdown final** : frontmatter (R4) + corps de la note (texte brut de l'atome avec mise en forme minimale).
2. **Vérifier les invariants** (cf. `_frontmatter-universel.md` section « Invariants à vérifier à l'écriture ») — si violation, signaler à l'utilisateur et écrire en `00-inbox/` avec tag `invariant-violation` au lieu de la zone cible.
3. **Créer le dossier parent** si absent.
4. **Écrire via rename atomique** (Pattern 1).
5. Si la zone cible est `episodes` : mettre à jour `historique.md` du projet/domaine via **rename atomique + hash check** (Pattern 2). Ajouter une ligne `- [YYYY-MM-DD HHhMM — {sujet}](archives/{nom-archive}.md)`.
6. Si l'atome a un `derived_atoms` (atome parent qui a généré celui-ci) : enrichir l'atome parent en ajoutant `derived_atoms: [..., "[[nouveau-atome]]"]`. Bidirectionnalité.
7. Mettre à jour `99-meta/_index.md` (rename atomique + hash check) : ajouter une entrée dans la section `Archives` (zone episodes uniquement) ou simplement maintenir le compteur global.

### R8. Liens bidirectionnels (atomes dérivés)

Quand un atome A en zone `episodes` génère un atome B en autre zone (ex: une archive de session dégage un nouveau principe), créer un **lien bidirectionnel** :

- Dans A (`10-episodes/...`) : ajouter dans le frontmatter `derived_atoms: ["[[chemin-relatif-vers-B]]"]`.
- Dans B (zone cible) : renseigner `contexte_origine: "[[chemin-relatif-vers-A]]"`.

Obsidian Graph rendra visible la filiation. Cette bidirectionnalité est indispensable pour que `mem-recall {projet}` puisse charger non seulement les archives mais aussi les principes/objectifs/connaissances dérivés du projet.

### R9. Rapport utilisateur

À la fin de l'écriture, afficher un **rapport synthétique** :

```
✓ {N} atome(s) ingéré(s) :
  [1] {sujet} → {chemin}
  [2] {sujet} → {chemin}
  ...

Liens : {N} liens bidirectionnels créés (visible dans Obsidian Graph).
Prochaines étapes suggérées : {ouvrir le vault | reclasser via /mem-reclass | voir l'index}.
```

Si certains atomes ont été refusés (mode safe avec `n` ou `e`), les lister dans le rapport :

```
✗ {M} atome(s) non écrit(s) (refusé par utilisateur) :
  [3] {sujet} — refusé
```

### R10. Idempotence (pour skills `mem-archeo*`)

Quand le router est invoqué par `mem-archeo` ou `mem-archeo-atlassian` (rétro-archivage), il doit éviter de **recréer des atomes déjà ingérés** lors d'un précédent passage.

Mécanisme :
- L'atome porte un identifiant d'origine : `source_jalon` (commit SHA pour archeo-git, page ID pour archeo-atlassian) + `source_atom_type` (event/principle/concept/etc.) + `source_atom_subject` (slug court du sujet).
- Avant l'écriture, le router cherche dans le vault un fichier ayant les mêmes 3 champs. Si trouvé :
  - Si contenu identique → skip silencieux.
  - Si contenu modifié → créer une nouvelle version avec `previous_atom: [[ancien]]` + tag `revision`. Préserve l'immuabilité des archives historiques.

Cette logique ne s'applique **pas** aux skills d'ingestion vécue (`mem-archive`, `mem-note`, etc.) : ces skills produisent toujours du contenu nouveau, pas de risque de doublon.
