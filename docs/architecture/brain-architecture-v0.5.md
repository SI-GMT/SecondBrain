---
titre: Brain Architecture v0.5 — refonte brain-centric du vault SecondBrain
statut: validé
version: 1.0
valide_le: 2026-04-25
auteur: bdubois + Claude (Opus 4.7)
date: 2026-04-24
---

# Brain Architecture v0.5 — refonte brain-centric du vault SecondBrain

> Document de cadrage de la refonte du vault SecondBrain, du passage d'une organisation **project-centric** à une organisation **brain-centric** structurée par fonctions mémorielles. Décisions structurantes à prendre **avant** toute implémentation v0.5.0 et avant Phase 3 MCP.

## Table des matières

1. [Contexte et motivation](#1-contexte-et-motivation)
2. [Modèle théorique](#2-modèle-théorique)
3. [Scope personnel / professionnel / collectif](#3-scope-personnel--professionnel--collectif)
4. [Taxonomie : les 9 zones racines](#4-taxonomie--les-9-zones-racines)
5. [Le router sémantique — pattern central d'ingestion](#5-le-router-sémantique--pattern-central-dingestion)
6. [Tags transverses](#6-tags-transverses)
7. [Structure fichier type (frontmatter canonique par zone)](#7-structure-fichier-type-frontmatter-canonique-par-zone)
8. [Impact sur les 11 skills mem-*](#8-impact-sur-les-11-skills-mem)
9. [Plan de migration des archives existantes](#9-plan-de-migration-des-archives-existantes)
10. [Plan de livraison (phasage v0.5.0)](#10-plan-de-livraison-phasage-v050)
11. [Questions ouvertes / décisions différées](#11-questions-ouvertes--décisions-différées)

---

## 1. Contexte et motivation

### 1.1 Le vault v0.1–v0.4 était project-centric

SecondBrain a été conçu en avril 2026 comme un **log de sessions de travail** destiné à donner aux CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) une mémoire persistante. L'axe d'organisation primaire du vault est le **projet** : chaque unité de travail significative génère un dossier `projets/{slug}/` contenant un `context.md` mutable et un `history.md` chronologique, alimenté par des archives horodatées déposées dans un dossier plat `archives/` à la racine du vault.

Ce modèle a tenu sur les premières versions (v0.1 à v0.4) parce que l'usage était dominé par un cas unique : « archiver ce que j'ai fait aujourd'hui sur le projet X ». Les features v0.4.0 (`mem-doc`, `mem-archeo`, `mem-archeo-atlassian`) ont commencé à fissurer ce modèle en introduisant des contenus qui ne sont pas des sessions vécues, mais qui ont été rangés dans la même structure faute d'alternative.

### 1.2 Les limites observées en avril 2026

Trois limites structurelles rendent le modèle project-centric insuffisant :

**(a) Le dossier `archives/` plat sature.** Avec une cinquantaine d'archives après trois semaines d'usage effectif, la lisibilité se dégrade rapidement. Un vault en usage continu sur un an produirait plusieurs centaines d'archives dans un même dossier, illisibles même à la recherche plein texte. L'arborescence d'Obsidian devient un mur.

**(b) Le moule projet est trop étroit.** Une mémoire humaine ne contient pas que des sessions : elle contient des connaissances (faits, concepts), des règles (« ne jamais X »), des objectifs (intentions futures), des relations (personnes), du savoir-faire (procédures, playbooks), et des productions non verbales (schémas, métaphores). Tous ces contenus finissent aujourd'hui soit forcés dans un pseudo-projet, soit relégués au projet `inbox` qui devient fourre-tout. La typologie fonctionnelle de la mémoire n'est pas représentée.

**(c) Aucun axe cognitif.** Les skills `mem-*` ne distinguent pas ce qui est vécu (épisodique), appris (sémantique), ou su-faire (procédural). Conséquence : le `/mem-recall` charge toujours le même type de contenu (les dernières archives du projet), même quand la bonne réponse serait de charger un principe stable, un objectif actif, ou une procédure connue.

### 1.3 Pourquoi maintenant, avant Phase 3 MCP

Le planning initial prévoyait la Phase 3 (serveur MCP `memory-kit`) comme priorité après v0.4.0. Cette phase a été **reportée**, pour une raison simple : implémenter un serveur MCP sur une architecture vouée à être démantelée revient à créer de la dette immédiate. Les outils MCP exposeraient des concepts (`mem_archive`, `mem_recall`, `projets`) qui seront redéfinis à la v0.5.0. Tout le travail de scaffolding, de tests, de documentation du MCP serait à refaire.

**Le refactor brain-centric est donc pré-requis à Phase 3 MCP.** La release v0.4.0 est également annulée : on passe directement à v0.5.0 une fois la refonte livrée.

### 1.4 Objectif de cette refonte

Inverser le rapport primaire entre **projet** et **fonction mémorielle** :

- Avant (v0.1–v0.4) : le projet est l'axe racine, les fonctions mémorielles (épisode, connaissance, règle, objectif...) sont implicites et confondues dans une même forme.
- Après (v0.5.0) : les **fonctions mémorielles sont l'axe racine**, structurées en 9 zones explicites. Le projet devient un **tag transverse** qui se projette verticalement dans plusieurs zones.

Bénéfices attendus :

- **Lisibilité structurelle** : chaque zone a un rôle clair, un type de contenu, un frontmatter canonique.
- **Routing intelligent** : un nouveau composant — le **router sémantique** (cf. section 5) — décide où va chaque atome de contenu selon sa nature.
- **Extensibilité** : les contenus non-sessions (notes, principes, objectifs, personnes) ont enfin un espace natif.
- **Alignement avec les modèles cognitifs** : s'appuie sur des cadres théoriques établis (Squire, Tulving, McGilchrist), facilite la conversation et la documentation.
- **Préparation à CollectiveBrain** : le scope `pro` + flag `collective` devient la clé de voûte de la future synchronisation entreprise.

---

## 2. Modèle théorique

La taxonomie des 9 zones n'est pas arbitraire : elle dérive d'une combinaison de modèles cognitifs établis, adaptés à un vault Markdown. Cette section précise les cadres de référence et ce qu'on en emprunte.

### 2.1 Taxonomie de la mémoire humaine (Squire, Tulving)

Le modèle standard en neuropsychologie distingue deux grandes catégories de mémoire à long terme (Squire, 1992) :

- **Mémoire déclarative** (consciente, verbalisable) :
  - **Épisodique** (Tulving, 1972) — événements personnellement vécus, datés, situés dans un contexte. « Le 24 avril 2026, j'ai décidé de pivoter SecondBrain vers une architecture brain-centric. »
  - **Sémantique** — faits, concepts, connaissances générales décontextualisées. « Le protocole MCP utilise JSON-RPC sur stdio ou HTTP. »
- **Mémoire non déclarative** (implicite, difficilement verbalisable) :
  - **Procédurale** — savoir-faire, habitudes motrices ou cognitives. « Comment faire une release SecondBrain : chore: polish, tag annoté, push, gh release create. »

Cette taxonomie donne les trois premières fonctions mémorielles du vault : **10-episodes**, **20-knowledge**, **30-procedures**.

### 2.2 Dimension volitive (au-delà de Squire)

Le modèle de Squire ne couvre pas les contenus **prospectifs** (tournés vers l'avenir) ni **normatifs** (règles d'action). Ces contenus relèvent de fonctions exécutives (lobe frontal) et sont centraux dans l'activité humaine consciente. On les rajoute :

- **Principes** — règles d'action stables, heuristiques de décision, lignes rouges. Comment je choisis, comment je tranche. Exemples : « ne jamais force-push sur main », « la famille passe avant le travail ».
- **Objectifs** — intentions futures, états désirés, roadmaps. Vers quoi je vais. Exemples : « maîtriser MCP et IRIS », « atteindre 10 000 pas par jour ».

**Décision 2026-04-24** : principes et objectifs sont **deux zones distinctes** (40-principles, 50-goals), parce que *comment je choisis* ≠ *vers quoi je vais*. Les fusionner (dans une zone « volitive ») masquerait cette différence fonctionnelle.

### 2.3 Dimension sociale et relationnelle

La mémoire humaine contient aussi une **carte des personnes** : qui est qui, quel rôle, quelle relation, quelle histoire. Cette fonction n'est pas dans Squire non plus, mais elle est constante dans l'usage vault (on parle de ses collègues, clients, amis, famille).

Zone dédiée : **60-people**.

### 2.4 Cerveau gauche / droit (McGilchrist)

Iain McGilchrist (*The Master and His Emissary*, 2009) popularise une relecture moderne de la dichotomie hémisphérique cérébrale, dépassant le cliché « cerveau gauche = logique, cerveau droit = créatif ». Son apport central : les deux hémisphères traitent le même contenu **selon deux modalités distinctes** :

- **Gauche** — analytique, séquentiel, verbal, décontextualisé, focalisé sur la partie.
- **Droite** — holistique, spatial, non-verbal, contextualisé, focalisé sur le tout.

**Choix d'implémentation** : pas un dossier racine, mais un **tag transverse `modality: left|right`** sur chaque note. Raisons :

- La même information (ex: une architecture logicielle) peut être stockée sous deux modalités (texte structuré `left` + schéma Excalidraw `right`).
- Un dossier séparé couperait artificiellement des contenus qui se complètent.
- Un tag permet à Obsidian Graph de basculer entre une vue « analytique » et une vue « intuitive » sans déplacer les fichiers.

Exception : **70-cognition** est une zone dédiée au cerveau droit pur (schémas, métaphores, moodboards, Excalidraw). Les LLM étant structurellement `left`, cette zone est peu alimentée par les skills et très alimentée par l'humain via Obsidian.

### 2.5 Modèles mentionnés mais non retenus comme axes primaires

- **PARA** (Tiago Forte) — Projects / Areas / Resources / Archives. Proche conceptuellement de notre distinction `projets` / `domaines` / `knowledge` / `archives historiques`, mais PARA est orienté productivité (getting things done), pas fonction mémorielle. On emprunte la distinction **Projects vs Areas** (qui se retrouve dans **projets vs domaines**, cf. section 4.2), mais on ne structure pas le vault entier sur PARA.

- **Zettelkasten** (Luhmann) — notes atomiques interconnectées par liens. C'est un **modèle d'interconnexion**, pas un modèle de classement. On l'adopte au niveau micro : chaque atome de mémoire est une note indépendante, reliée à d'autres via `[[...]]` Obsidian. Le router sémantique (section 5) produit naturellement des Zettel atomiques — c'est convergent.

- **GTD** (Getting Things Done, David Allen) — méthode de traitement des tâches. Hors scope direct (le vault n'est pas un gestionnaire de tâches), mais **capture brute → traitement** se retrouve dans `00-inbox/` → router → zones classées. Le pattern est présent sans être nommé.

- **Psychothérapies / modèles du soi** (IFS, analyse transactionnelle, etc.) — délibérément **non retenus**. Un vault d'assistant cognitif n'est pas un journal thérapeutique et ne doit pas prétendre modéliser la psyché. On reste dans le fonctionnel informatique.

### 2.6 Synthèse — les 9 zones et leur ancrage théorique

| Zone | Ancrage théorique |
|---|---|
| `00-inbox` | GTD (capture brute avant traitement) |
| `10-episodes` | Squire/Tulving — mémoire épisodique |
| `20-knowledge` | Squire — mémoire sémantique |
| `30-procedures` | Squire — mémoire procédurale |
| `40-principles` | Fonctions exécutives volitives — normes d'action |
| `50-goals` | Fonctions exécutives prospectives — intentions |
| `60-people` | Cognition sociale — carte relationnelle |
| `70-cognition` | McGilchrist — hémisphère droit, modalité non verbale |
| `99-meta` | Méta-cognition opérationnelle du vault |

Et un tag transverse : `modality: left|right` (McGilchrist).

---

## 3. Scope personnel / professionnel / collectif

### 3.1 Principe directeur

Un vault SecondBrain individuel porte **deux scopes** :

- **`perso`** — contenu privé, rattaché à la personne (famille, santé, loisirs, projets perso, notes intimes, heuristiques de vie).
- **`pro`** — contenu professionnel, rattaché au rôle de l'individu dans une organisation (projets de travail, compétences métier, procédures d'entreprise, connaissances de domaine pro).

Le **collectif** n'est pas un scope du vault individuel. C'est un **état de promotion** de certains contenus `pro` vers un vault collectif externe (**CollectiveBrain**, projet séparé, hébergé sur GMT Knowledges). Cette promotion est :

- **explicite** : l'utilisateur marque le contenu avec un flag dans le frontmatter ;
- **asymétrique** : le vault individuel peut pousser vers le collectif, mais jamais l'inverse n'est automatique (le collectif n'écrase pas l'individuel) ;
- **différée** : aucun skill SecondBrain ne lit ni ne traite le flag collectif en v0.5.0 — la mécanique de remontée est **Phase 3+** via le plugin CollectiveBrain ;
- **isolée** : la frontière entre les deux vaults est nette. Le vault individuel reste souverain et local.

### 3.2 Matérialisation en frontmatter

Tout fichier du vault (hors `00-inbox/` qui est par définition non qualifié) porte deux champs de frontmatter :

```yaml
scope: personal          # ou pro — obligatoire, valeur par défaut = pro
collective: false      # ou true — optionnel, n'a de sens que si scope: work
                      # défaut = false — non lu par SecondBrain en v0.5
```

**Règle d'invariant** : si `scope: personal`, alors `collective: false` (toujours). Le plugin CollectiveBrain ignorera tout fichier `perso` quel que soit le flag.

### 3.3 Scope applicable par zone

Toutes les zones ne portent pas les deux scopes avec la même distribution. Voici la matrice anticipée (à confirmer en section 4) :

| Zone | `perso` | `pro` | Commentaire |
|---|---|---|---|
| `00-inbox` | n/a | n/a | scope non qualifié, à classer |
| `10-episodes/projects/*` | oui | oui | un projet est soit perso soit pro, jamais les deux |
| `10-episodes/vie` | oui | rare | événements de vie, typiquement perso |
| `20-knowledge/business` | rare | oui | connaissance professionnelle |
| `20-knowledge/tech` | rare | oui | connaissance technique (typiquement pro, sauf loisir tech) |
| `20-knowledge/life` | oui | rare | connaissance perso (santé, parentalité, langues...) |
| `30-procedures` | oui | oui | chaque procédure a son scope |
| `40-principles` | oui | oui | principes perso (lignes rouges de vie) vs principes pro (règles métier) |
| `50-goals` | oui | oui | objectifs de vie perso vs roadmaps pro |
| `60-people` | oui | oui | famille / amis (perso) vs collègues / clients (pro) |
| `70-cognition` | oui | oui | sketches perso ou pro selon le contexte |
| `99-meta` | n/a | n/a | méta du vault, neutre |

### 3.4 Trois use cases cibles

**Use case A — utilisateur perso pur.** Une personne qui utilise SecondBrain pour gérer sa vie personnelle uniquement (projets perso, journal, lectures, objectifs de vie). Quasi-totalité du vault en `scope: personal`. Le flag `collective` n'est jamais activé. CollectiveBrain n'est pas installé. C'est le cas le plus simple.

**Use case B — utilisateur pro en entreprise.** Une personne qui utilise SecondBrain comme mémoire professionnelle dans le cadre de son travail (projets d'équipe, procédures internes, compétences métier, contacts pros, connaissances techniques). Majorité du vault en `scope: work`. Le scope `perso` est **réduit à la facette professionnelle de la personne** : préférences de travail, style de collaboration, éléments de contexte individuel utiles dans le contexte pro (« je travaille mieux le matin », « j'ai une expertise Y rarement mobilisée », « mon engagement sur le projet X se termine en juin »). Flag `collective: true` activé sur les contenus à remonter vers le vault collectif de l'entreprise.

**Use case C — hybride.** Une personne qui utilise un **seul vault SecondBrain** pour sa vie perso et pro. Les deux scopes coexistent, cloisonnés par frontmatter. Les skills filtreront selon le scope au moment de la recherche / rappel / archivage (paramètre `--scope perso|pro|all`). CollectiveBrain ne voit que les contenus `pro` flaggués `collective: true`.

### 3.5 Filtrage par les skills

Les skills `mem-*` exposeront un paramètre `--scope` (valeurs : `perso`, `pro`, `all` ; défaut : `all`). Exemple :

- `/mem-recall --scope pro mon-projet` → charge le contexte en ignorant les contenus `perso`.
- `/mem-search --scope perso objectifs` → cherche uniquement dans le scope perso.
- `/mem-archive` (au moment d'écrire) — doit demander ou inférer le scope du contenu archivé ; valeur par défaut contrôlable via `~/.claude/memory-kit.json` (`default_scope: work` pour un poste d'entreprise, `perso` pour un poste perso).

Un champ `default_scope` dans `memory-kit.json` règle le comportement par défaut sans friction pour l'utilisateur. **Décision : le vault est mono-instance par poste** — un seul vault, un seul `default_scope`. Pas de multi-vault sur un même poste (évite la gestion d'emplacements multiples et clarifie le modèle). Un utilisateur qui aurait besoin de deux vaults (ex: séparation stricte perso/pro) peut utiliser deux comptes/utilisateurs OS ou deux `CLAUDE_CONFIG_DIR`.

Exemple `memory-kit.json` :

```json
{
  "vault": "C:\\_BDC\\GMT\\memory",
  "default_scope": "pro"
}
```

### 3.6 Relation avec CollectiveBrain (hors scope v0.5.0, documenté ici pour alignement)

Quand CollectiveBrain sera développé (après Phase 3 MCP), le plugin Obsidian fera :

1. **Lecture seule** du vault individuel, jamais d'écriture.
2. **Filtre strict** : uniquement les fichiers avec `scope: work` **ET** `collective: true`.
3. **Remontée** vers le vault collectif (hébergé sur GMT Knowledges) avec préservation de l'origine (`origine: {utilisateur}`) et anonymisation optionnelle selon politique entreprise.
4. **Pas de descente automatique** : le collectif ne réécrit jamais l'individuel. Si un contenu collectif est utile à un individu, il est importé comme **lecture** séparée, pas comme mutation de son vault.

Cette asymétrie garantit la souveraineté du vault individuel.

### 3.7 Décisions actées (2026-04-24)

- **D3.1** Pas de scope `inbox` / `brouillon` supplémentaire. Le dossier `00-inbox/` suffit à représenter le contenu non qualifié. Tout contenu hors `00-inbox/` porte obligatoirement `scope: personal` ou `scope: work`.
- **D3.2** Le flag `collective` reste un booléen simple en v0.5.0 (`true` / `false`). L'affinage (granularité `equipe|entreprise|public`) sera traité dans CollectiveBrain quand les cas réels seront connus — hors scope SecondBrain.
- **D3.3** `context.md` et `history.md` d'un projet héritent du scope du projet. Le scope est déclaré **une seule fois** dans `context.md` (frontmatter du projet) et s'applique à tous les fichiers du dossier projet. Un projet est soit `perso`, soit `pro`, jamais les deux.
- **D3.4** Un contenu peut changer de scope au cours de sa vie via le skill **`mem-reclass`** (implémentation immédiate en v0.5.0). Le skill met à jour frontmatter + tags + déplace le fichier si nécessaire (ex: un projet reclassé perso → pro déplace son dossier d'une zone hôte à l'autre). Opération considérée rare mais supportée.

---

## 4. Taxonomie : les 9 zones racines

Chaque zone est décrite via une grille unifiée : **rôle**, **contenu type**, **exemples**, **scope applicable**, **structure interne**, **frontmatter canonique**, **tags attendus**, **skills concernés**.

### 4.1 `00-inbox/` — captation brute

- **Rôle** : point d'entrée zéro-friction pour tout ce qui n'a pas encore de classement. Espace tampon.
- **Contenu type** : notes jetées en vitesse, documents ingérés sans projet détecté, copies de liens, pensées brutes, fragments à traiter.
- **Exemples** : « idée de feature captée en réunion », « PDF reçu sans contexte clair », « bout d'archi dessiné sur un post-it ».
- **Scope applicable** : **non qualifié** (le scope sera fixé au moment du reclassement).
- **Structure interne** : plat, pas de sous-dossiers. Si l'inbox gonfle, c'est un signal qu'il faut classer, pas créer des sous-dossiers dans l'inbox.
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD
  zone: inbox
  tags: [zone/inbox]
  ---
  ```
- **Tags attendus** : `zone/inbox` et rien d'autre d'obligatoire.
- **Skills concernés** :
  - `mem-doc` (par défaut si aucun projet détecté) écrit ici.
  - `mem-reclass` déplace l'item vers sa zone cible et attribue scope + tags.
  - `mem-search` scanne l'inbox comme n'importe quelle zone.
  - **Aucun archive de session ne doit finir en inbox** — `mem-archive` route toujours vers `10-episodes/projects/{slug}/archives/`.

### 4.2 `10-episodes/` — mémoire épisodique

- **Rôle** : événements datés, vécus. « Qu'est-ce qui s'est passé, quand, dans quel contexte ? »
- **Contenu type** : archives de sessions de travail, incidents, décisions datées, points de réunion, événements de vie rattachés à un domaine permanent.
- **Exemples** : archive `2026-04-24-15h30-secondbrain-pivot-brain-centric.md` (projet), `2026-04-20-panne-iris-prod.md` (projet), `2026-03-15-consult-cardio.md` (domaine santé).
- **Scope applicable** : `perso` et `pro`. Le scope est déclaré au niveau du **projet ou du domaine** (dans `context.md`) et hérité par toutes les archives du dossier (D3.3).
- **Structure interne — deux sous-logiques symétriques** (décision 2026-04-24, option C retenue) :
  ```
  10-episodes/
    projets/                # vocation FINIE — projets avec début, déroulé, fin
      {slug}/
        context.md         # scope: personal|pro — snapshot mutable
        history.md       # fil chronologique avec liens
        archives/           # horodatées, immuables
          YYYY-MM-DD-HHhMM-{slug}-{sujet}.md
    domaines/               # PERMANENTS — pas de fin prévue
      {slug}/               # ex: sante, famille, finances, veille-tech, hygiene-mail
        context.md         # snapshot mutable du domaine (état courant)
        history.md       # fil chronologique
        archives/           # horodatées, immuables
  ```
  Un **projet** a une fin probable (même lointaine) : il vise un livrable ou une transformation bornée. Un **domaine** n'a pas de fin : c'est un fil continu d'attention (santé, relation de couple, veille tech). Les deux ont la même structure interne (`context.md` + `history.md` + `archives/`), donc les skills les traitent de manière uniforme — seul le **chemin racine** change (`projects/` vs `domains/`).

- **Règle d'apparition d'un domaine** (anti-dérive) : un domaine n'est créé que si tu as **au moins 3 archives** qui ne rentrent dans aucun projet mais se rattachent au même fil continu. Avant ce seuil, les événements isolés vivent en `00-inbox/`. Règle gravée dans `99-meta/classification-rules.md`.

- **Frontmatter canonique (archive projet OU domaine)** :
  ```yaml
  ---
  date: YYYY-MM-DD
  heure: "HH:MM"
  zone: episodes
  kind: {projet|domaine}            # nouveau — distingue les deux sous-logiques
  projet: {slug}                    # si kind: project
  domaine: {slug}                   # si kind: domain
  scope: {perso|pro}
  collective: false
  source: {vecu|doc|archeo-git|archeo-atlassian}
  modality: left
  tags: [zone/episodes, {projet|domaine}/{slug}, scope/*, source/*, modality/*]
  ---
  ```

- **Frontmatter canonique (context.md d'un projet ou domaine)** :
  ```yaml
  ---
  zone: episodes
  kind: {projet|domaine}
  slug: {slug}
  scope: {perso|pro}
  collective: false
  tags: [zone/episodes, kind/*, {projet|domaine}/{slug}, scope/*]
  ---
  ```

- **Tags attendus** : `zone/episodes`, `kind/{projet|domaine}`, `project/{slug}` OU `domain/{slug}`, `scope/*`, `source/*`, `modality/*`.

- **Skills concernés** :
  - `mem-archive` — écriture principale. Demande ou infère `kind` (projet ou domaine) si ambigu. Par défaut : tente match dans `projects/` puis `domains/`, sinon crée en `00-inbox/`.
  - `mem-recall` — lit `context.md` + dernières entrées d'`history.md`. Marche sur projet **ou** domaine avec la même procédure.
  - `mem-archeo` / `mem-archeo-atlassian` — écrit dans `projets/{slug}/archives/` (les domaines n'ont pas de source Git/Atlassian).
  - `mem-rollback-archive` — suppression de la dernière archive.
  - `mem-rename-project`, `mem-merge-projects` — réorganisation. **Renommés en v0.5.0 en** `mem-rename` et `mem-merge` (opèrent sur projet OU domaine).
  - Nouveau skill potentiel `mem-promote-domain` : promeut un item de `00-inbox/` en nouveau domaine (quand les 3 archives sont atteintes).

### 4.3 `20-knowledge/` — mémoire sémantique

- **Rôle** : faits, concepts, connaissances consolidées, doc de référence. « Qu'est-ce que je sais ? »
- **Contenu type** : notes de domaine, fiches de concepts, glossaires, docs d'architecture de référence, résumés de lectures, synthèses métier.
- **Exemples** : `tech/iris/globals.md`, `metier/imagerie/dicom.md`, `tech/mcp/protocole.md`, `vie/sante/nutrition.md`.
- **Scope applicable** : majoritairement `pro`, mais `perso` possible (`vie/sante`, `vie/parentalite`, `vie/langues`, etc.). Scope au niveau du fichier, pas du dossier.
- **Structure interne** : **libre, aucun schéma imposé** (D section 3 / décision utilisateur 2026-04-24). Proposition d'une **organisation de base** avec grandes familles, à faire évoluer au fil de l'usage :
  ```
  20-knowledge/
    metier/           # domaines professionnels (santé, imagerie, IA, KMS...)
    tech/             # technologies (iris, mcp, obsidian, python, docker...)
    vie/              # connaissance perso (santé, parentalité, langues...)
    methodes/         # connaissance épistémologique : méthodes de pensée, prise de notes,
                      # théorie de la mémoire (Squire/Tulving), Zettelkasten, PARA, GTD...
                      # transposable à n'importe quel vault — à distinguer de 99-meta/
                      # qui est opérationnel et propre à CE vault.
  ```
  L'utilisateur ajoute librement des sous-dossiers selon ses besoins (ex: `tech/iris/globals/`, `metier/imagerie/modalites/`). **Pas de profondeur max imposée**, mais recommandation : au-delà de 4 niveaux, envisager un split ou une tagification.
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD               # date de création, mise à jour tolérée
  zone: knowledge
  scope: {perso|pro}
  collective: false               # true si pro et partageable via CollectiveBrain
  modality: {left|right}
  type: {concept|fiche|glossaire|synthese|reference}
  tags: [zone/knowledge, scope/*, modality/*, type/*, {domaines libres}]
  sources: []                    # URLs ou refs si sourcé
  ---
  ```
- **Tags attendus** : `zone/knowledge`, `scope/*`, `modality/*`, `type/*` + tags libres de domaine.
- **Skills concernés** :
  - `mem-note` (nouveau, à confirmer) — ajoute / édite une note de connaissance.
  - `mem-search` — recherche plein texte.
  - `mem-reclass` — rebascule entre zones ou scopes.
  - `mem-digest` — peut synthétiser un sous-arbre `20-knowledge/*`.

### 4.4 `30-procedures/` — mémoire procédurale

- **Rôle** : savoir-faire, how-to, recettes, playbooks, checklists. « Comment je fais ? »
- **Contenu type** : procédures opérationnelles, checklists d'incidents, recettes de dev, playbooks de release, procédures de vie (recettes de cuisine, protocoles perso).
- **Exemples** : `pro/release-semver.md`, `pro/incident-iris-prod.md`, `perso/recette-cassoulet.md`, `pro/onboarding-nouveau-dev.md`.
- **Scope applicable** : `perso` et `pro`.
- **Structure interne** :
  ```
  30-procedures/
    pro/
      {category}/      # ex: release, incident, dev, admin...
    perso/
      {category}/      # ex: cuisine, sante, admin-perso...
  ```
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD
  zone: procedures
  scope: {perso|pro}
  collective: false
  modality: left              # une procédure est quasiment toujours left
  type: procedure
  tags: [zone/procedures, scope/*, type/procedure, {category}]
  etapes: N                   # optionnel, nombre d'étapes
  duree_estimee: "HHhMM"      # optionnel
  outils: []                  # optionnel, liste d'outils requis
  ---
  ```
- **Tags attendus** : `zone/procedures`, `scope/*`, `type/procedure`, `categorie/*`.
- **Skills concernés** :
  - `mem-note` (ou skill dédié `mem-procedure` si besoin distinct) — écrit une procédure.
  - `mem-search` — retrouver une procédure par mot-clé.
  - `mem-reclass`.
  - **Gardé en tête** : en Phase 3 MCP, une procédure pourrait devenir exécutable si structurée (YAML steps + prompts).

### 4.5 `40-principles/` — heuristiques et lignes rouges

- **Rôle** : règles de choix, heuristiques, lignes rouges, valeurs opérantes. « Selon quoi je tranche ? »
- **Contenu type** : principes d'action (« ne jamais X », « toujours privilégier Y »), heuristiques de décision, critères d'arbitrage, valeurs professionnelles, valeurs personnelles.
- **Exemples** :
  - `pro/dev/no-force-push-sur-main.md`
  - `pro/communication/brief-avant-action-risquee.md`
  - `perso/vie/famille-passe-avant-travail.md`
  - `perso/sante/sommeil-minimum-7h.md`.
- **Scope applicable** : `perso` et `pro`. **Attention** : les principes perso peuvent être très intimes — ils ne doivent jamais fuir vers CollectiveBrain (enforcement par invariant D3 section 3.2).
- **Structure interne** :
  ```
  40-principles/
    pro/
      {domaine}/      # dev, communication, management, ethique...
    perso/
      {domaine}/      # vie, sante, famille, finances...
  ```
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD               # date d'adoption du principe
  zone: principes
  scope: {perso|pro}
  collective: false
  modality: left
  type: principle
  tags: [zone/principes, scope/*, type/principle, {domaine}]
  force: {ligne-rouge|heuristique|preference}
  context_origin: ""           # texte court : incident ou lecture qui a généré ce principe
  ---
  ```
- **Tags attendus** : `zone/principes`, `scope/*`, `type/principle`, `force/*`.
- **Skills concernés** :
  - `mem-principle` (nouveau, à confirmer) — ajoute un principe.
  - `mem-recall` — les principes d'un projet (`scope: work` + tag `project/{slug}`) sont chargés au recall du projet pour nourrir le contexte LLM.
  - `mem-search`.

### 4.6 `50-goals/` — prospective et intentions

- **Rôle** : intentions futures, roadmaps, aspirations, buts. « Vers quoi je vais ? »
- **Contenu type** : objectifs de vie, roadmaps de carrière, objectifs de projet, aspirations, intentions à long, moyen, court terme.
- **Exemples** :
  - `vie/5-ans/autonomie-financiere.md`
  - `pro/carriere/maitriser-mcp-et-iris.md`
  - `projets/secondbrain/roadmap-v1.md`
  - `perso/sante/10000-pas-par-jour.md`.
- **Scope applicable** : `perso` et `pro`.
- **Structure interne** :
  ```
  50-goals/
    perso/
      vie/             # long terme (années)
      sante/
      famille/
      finances/
    pro/
      carriere/        # long terme pro
      projets/
        {slug}/        # objectifs d'un projet donné, scope hérité du projet
  ```
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD                # date d'écriture
  zone: objectifs
  scope: {perso|pro}
  collective: false
  modality: left
  type: goal
  tags: [zone/objectifs, scope/*, type/goal, {horizon}]
  horizon: {court|moyen|long}     # court = semaines, moyen = mois, long = années
  echeance: YYYY-MM-DD            # optionnel, date cible
  statut: {ouvert|en-cours|atteint|abandonne}
  projet: {slug}                  # si rattaché à un projet
  ---
  ```
- **Tags attendus** : `zone/objectifs`, `scope/*`, `type/goal`, `horizon/*`, `statut/*`.
- **Skills concernés** :
  - `mem-goal` (nouveau, à confirmer).
  - `mem-recall` — les objectifs actifs d'un projet sont chargés au recall.
  - `mem-digest` — peut produire un état des lieux des objectifs (atteints, en cours, abandonnés) sur une période.

### 4.7 `60-people/` — carnet relationnel

- **Rôle** : fiches personnes. « Avec qui ? »
- **Contenu type** : collègues, clients, fournisseurs, amis, famille, contacts récurrents. Une fiche par personne.
- **Exemples** :
  - `pro/collegues/marie-tutelo.md`
  - `pro/clients/CHU-toulouse/contacts.md`
  - `perso/famille/frere.md`
  - `perso/amis/marc.md`.
- **Scope applicable** : `perso` (famille, amis) et `pro` (collègues, clients, partenaires). **Les fiches perso ne remontent jamais à CollectiveBrain** (invariant D3.2).
- **Structure interne** :
  ```
  60-people/
    pro/
      collegues/
      clients/
      partenaires/
    perso/
      famille/
      amis/
      connaissances/
  ```
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD                # date de création fiche
  zone: personnes
  scope: {perso|pro}
  collective: false                # invariant : si sensitive: true alors collective: false
  sensitive: true                 # défaut true sur toutes les fiches personnes — interdit
                                  # mécaniquement la promotion vers CollectiveBrain
                                  # (cf. décision Q4.4 2026-04-24)
  modality: left
  type: person
  tags: [zone/personnes, scope/*, type/person, {category}]
  nom: "Prénom NOM"
  role: ""                        # rôle / relation
  organisation: ""                # pour les pros
  contact:
    email: ""
    tel: ""
  last_interaction: YYYY-MM-DD
  ---
  ```
- **Coordonnées dans le vault** (décision Q4.4 2026-04-24) : autorisées pour les deux scopes, car le vault est personnel et local. Contrepartie : flag `sensitive: true` par défaut sur toutes les fiches `60-people/**`, qui **interdit mécaniquement** l'activation de `collective: true` (enforcement dans `mem-reclass` et dans le plugin CollectiveBrain futur). L'utilisateur peut basculer `sensitive: false` s'il le souhaite, mais doit le faire explicitement.
- **Tags attendus** : `zone/personnes`, `scope/*`, `type/person`, `categorie/*`.
- **Skills concernés** :
  - `mem-person` (nouveau, à confirmer).
  - `mem-recall` — les personnes-clés d'un projet peuvent être remontées dans le contexte.
  - `mem-search` — retrouver une personne par nom / rôle / organisation.

### 4.8 `70-cognition/` — cerveau droit pur

- **Rôle** : espace dédié aux productions **non verbales** / intuitives / spatiales. « Qu'est-ce que je ressens, imagine, esquisse ? »
- **Contenu type** : dessins Excalidraw, diagrammes, canvases Obsidian, métaphores, moodboards, analogies, brouillons graphiques, mindmaps, images collectées.
- **Exemples** :
  - `schemas/secondbrain-archi-v0.5.excalidraw.md`
  - `metaphores/vault-comme-maison.md`
  - `moodboards/fonctionnement-equipe-ideale.canvas`
  - `sketches/idees-interfaces.md`.
- **Scope applicable** : `perso` et `pro`.
- **Structure interne** : libre, par **type de production** plutôt que par domaine :
  ```
  70-cognition/
    schemas/          # diagrammes, architecture, flux
    metaphores/       # analogies, comparaisons, récits
    moodboards/       # images, canvases, atmosphères
    sketches/         # brouillons libres
  ```
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD
  zone: cognition
  scope: {perso|pro}
  collective: false
  modality: right                 # toujours right par nature
  type: {schema|metaphore|moodboard|sketch}
  tags: [zone/cognition, scope/*, modality/right, type/*]
  projet: {slug}                  # optionnel
  ---
  ```
- **Note importante** : les fichiers Obsidian spéciaux (`.excalidraw.md`, `.canvas`, `.base`) doivent être édités **depuis Obsidian** et non via `Edit` / `Write` des skills — règle héritée de l'architecture actuelle.
- **Tags attendus** : `zone/cognition`, `modality/right`, `type/*`.
- **Skills concernés** :
  - Peu d'interaction directe avec les skills. `mem-reclass` peut y déplacer un contenu. `mem-search` indexe le texte accompagnant les schémas.
  - L'utilisateur crée et édite via Obsidian ; les skills ne génèrent pas de contenu `right` par défaut (un LLM est structurellement `left`).

### 4.9 `99-meta/` — méta-mémoire du vault

- **Rôle** : doctrine du vault, catalogues, règles de classement. « Comment le vault est-il organisé, selon quelles conventions ? »
- **Note sur l'index** : `index.md` (catalogue maître) vit **à la racine du vault**, pas dans `99-meta/` — c'est le point d'entrée naturel d'Obsidian.
- **Contenu type** : doctrine du vault (copie du présent document), glossaire des tags, règles de classement, conventions d'encodage, journaux de refonte.
- **Exemples** :
  - `99-meta/doctrine.md` (copie archivée de brain-architecture-v0.5)
  - `99-meta/tag-taxonomy.md`
  - `99-meta/classification-rules.md`.
- **Scope applicable** : **non qualifié** (méta, neutre).
- **Structure interne** : plat, très peu de sous-dossiers.
- **Frontmatter canonique** :
  ```yaml
  ---
  date: YYYY-MM-DD
  zone: meta
  type: {index|doctrine|taxonomie|regle}
  tags: [zone/meta, type/*]
  ---
  ```
- **Tags attendus** : `zone/meta`, `type/*`.
- **Skills concernés** :
  - `mem-recall` lit `index.md` (chargement du catalogue projets).
  - Tous les skills lisent les règles de classement si applicables.
  - Le document de cadrage `brain-architecture-v0.5.md` est copié ici au moment de la release v0.5.0 (la spec du kit vit dans le repo, la doctrine opérante vit dans le vault).

---

## 5. Le router sémantique — pattern central d'ingestion

### 5.1 Principe

**Décision 2026-04-24** : l'ingestion de contenu dans le vault n'est pas gérée par N skills indépendants, mais par **un router sémantique unique** qui :

1. **Reçoit** un contenu préformaté (par un adapter, un document, un jalon Git, une page Confluence).
2. **Segmente** ce contenu si nécessaire (un seul input peut contenir plusieurs atomes de mémoire de types différents).
3. **Classe** chaque segment vers la zone appropriée selon des heuristiques claires.
4. **Enrichit** avec scope, tags, frontmatter, relations.
5. **Écrit** dans le vault en respectant les patterns d'atomicité et de concurrence (hash check, rename atomique).
6. **Rapporte** à l'utilisateur où chaque segment a été classé.

Le router est un **composant transverse** stocké dans `core/procedures/_router.md` (préfixe `_` = bloc réutilisable, non déployé seul). Il est invoqué par **tous les skills d'ingestion** : `mem`, `mem-archive`, `mem-doc`, `mem-archeo`, `mem-archeo-atlassian`. Les skills spécialisés peuvent **forcer une zone** lors de l'appel (shortcut de l'utilisateur) ou laisser le router décider.

### 5.2 Surface d'API

```
/mem {contenu}                     # chemin zéro-friction — router décide tout
/mem-archive {note}                # force zone: episodes (session vécue)
/mem-doc {chemin}                  # force source: doc, router décide la zone finale
/mem-archeo {depot}                # force source: archeo-git, router segmente par jalon
/mem-archeo-atlassian {url}        # force source: archeo-atlassian, router segmente par page
/mem-note {contenu}                # force zone: knowledge
/mem-principle {contenu}           # force zone: principes
/mem-goal {contenu}                # force zone: objectifs
/mem-person {contenu}              # force zone: personnes
/mem-reclass {chemin}              # change zone/scope d'un contenu existant
```

Tous les skills spécialisés appellent le router en lui passant un **hint de zone forcée**. L'implémentation est unifiée : **une seule procédure de routing**, plusieurs points d'entrée.

### 5.3 Segmentation

Un contenu soumis au router peut être **un atome unique** (ex: « ne jamais force-push sur main » → principe unique) ou **un agrégat** (ex: session de dev qui a dégagé 1 décision datée + 2 principes + 1 nouvelle connaissance technique). Le router doit :

1. **Détecter la structure** : paragraphes, bullets, blocs, délimités par titres Markdown ou séparateurs explicites (`---`, `#`, puces).
2. **Identifier les atomes** : unités sémantiques cohérentes et autonomes. Un atome = une note finale (fait, principe, objectif, archive, etc.).
3. **Classer chaque atome** séquentiellement via les heuristiques de routing (section 5.4).
4. **Produire un plan** avant toute écriture : liste de `[segment, zone, scope, tags, chemin cible, frontmatter]`.
5. **Valider avec l'utilisateur** si `--dry-run` ou si des atomes sont ambigus (`confidence < seuil`).
6. **Écrire** tous les atomes une fois le plan accepté, atomicité par fichier (pas de rollback global en v0.5.0 — trop coûteux, accepté).

Les atomes peuvent **se référencer entre eux** via les liens Obsidian `[[...]]` (ex: l'archive de session cite les principes nouveaux extraits, qui eux-mêmes pointent vers l'archive comme `context_origin`).

### 5.4 Heuristiques de routing

Cascade de détection, en ordre de priorité (premier match gagne) :

| Priorité | Indice | Zone cible |
|---|---|---|
| 1 | Hint forcé par le skill appelant | Zone forcée, bypass cascade |
| 2 | Événement daté au passé + contexte projet/domaine | `10-episodes/{projets\|domaines}/{slug}/archives/` |
| 3 | Verbe impératif ou structure étape-par-étape | `30-procedures/` |
| 4 | Règle / contrainte / valeur (« toujours », « jamais », « privilégier ») | `40-principles/` |
| 5 | Intention future + horizon temporel (« objectif », « d'ici », échéance) | `50-goals/` |
| 6 | Fiche personne (nom propre + rôle/relation) | `60-people/` |
| 7 | Production non verbale ou référence à schéma (Excalidraw, métaphore) | `70-cognition/` |
| 8 | Fait / concept / définition / synthèse stable | `20-knowledge/` (sous-famille libre selon domaine détecté) |
| 9 | Ambigu ou contenu hétérogène non segmentable | `00-inbox/` + tag `ambigu` |

Le scope (`perso` vs `pro`) est détecté par indices lexicaux (« mon équipe » / « client » → pro ; « ma famille » / « ma santé » → perso) avec fallback sur `default_scope` de `memory-kit.json`.

Le router **loggue** systématiquement son raisonnement dans un rapport utilisateur lisible :

```
Plan d'ingestion (3 atomes détectés) :
  [1] "Le commit fix: no force-push a été motivé par..." 
      → 10-episodes/projects/secondbrain/archives/2026-04-24-... (source: archeo-git)
  [2] "Règle : ne jamais force-pusher sur main"
      → 40-principles/work/dev/no-force-push.md (nouveau principe)
  [3] "Les rulesets GitHub permettent de..."
      → 20-knowledge/tech/github/rulesets.md (nouveau concept)
Continuer ? (o/n)
```

### 5.5 Préformatage par les adapters

Les adapters (Claude Code, Gemini CLI, Codex, Vibe) sont **responsables de préformater** le contenu avant appel au router. Objectifs du préformatage :

- **Normaliser** les fins de ligne (LF), l'encodage (UTF-8 sans BOM).
- **Injecter** le contexte d'invocation : projet courant (CWD), scope par défaut, métadonnées d'origine (session utilisateur, timestamp).
- **Extraire** si possible les atomes évidents (titres Markdown, blocs délimités) pour faciliter la segmentation.
- **Pré-annoter** les indices de scope (« workspace pro » vs « workspace perso » selon le CWD).

Les adapters ne décident **jamais** de la zone finale — c'est la responsabilité du router. Mais ils fournissent tout le contexte utile pour que le router décide bien.

### 5.6 Extension aux skills `mem-archeo*`

**Changement majeur 2026-04-24** : `mem-archeo` et `mem-archeo-atlassian` ne produisent plus une archive monolithique par jalon. Ils délèguent au router, qui peut segmenter un jalon en plusieurs atomes répartis dans plusieurs zones.

Exemple concret (`mem-archeo` sur un commit `fix(security): prevent force-push on main`) :

- Atome 1 : **événement daté** → archive dans `10-episodes/projects/secondbrain/archives/YYYY-MM-DD-...archeo-git.md` (source archeo-git, contenu factuel : hash, auteur, fichiers modifiés, diff stats).
- Atome 2 : **principe extrait** → nouvelle fiche `40-principles/work/dev/no-force-push-sur-main.md` (si le principe n'existe pas déjà, sinon enrichir l'existant avec `context_origin` pointant vers l'archive).
- Atome 3 (optionnel) : **connaissance technique acquise** → nouvelle note `20-knowledge/tech/git/rulesets-protection.md` si le commit introduit un concept réutilisable.

Idem pour `mem-archeo-atlassian` : une page Confluence peut contenir à la fois du factuel (historique d'un incident → `10-episodes`), des principes (règles d'écriture du code produit → `40-principles`), et des connaissances (glossaire métier → `20-knowledge`). Le router segmente et distribue.

**Conséquence sur l'idempotence** : l'idempotence des skills archeo (ne jamais recréer une archive déjà ingérée) doit s'étendre aux atomes dérivés. Si un jalon a déjà généré un principe `P`, une ré-ingestion ne doit pas créer `P2` en doublon — elle doit détecter `P` existant et, soit le laisser intact (si identique), soit l'enrichir (si évolution). Implémenté via les champs d'origine : `derived_from: <archive_id>` dans les atomes dérivés, et recherche par `(source_milestone + type_atome + sujet)` lors de la ré-ingestion.

### 5.7 Conséquences architecturales

- **Une seule procédure core** pour le routing : `core/procedures/_router.md`. Tous les skills d'ingestion la référencent via une directive d'inclusion (à implémenter dans `deploy.ps1` — nouvelle mécanique `{{INCLUDE _router}}` en plus de `{{PROCEDURE}}` et `{{CONFIG_FILE}}`).
- **Les procédures de zone** (`core/procedures/_zone-episodes.md`, `_zone-knowledge.md`, etc.) décrivent **l'écriture spécifique** à chaque zone (structure de dossier, frontmatter canonique, patterns d'atomicité). Le router les invoque après classement.
- **Phase 3 MCP** : le router devient un outil MCP `mem_ingest` qui expose une API typée. Les zones deviennent des sous-outils `mem_zone_episodes`, `mem_zone_knowledge`, etc. Les adapters n'ont plus à gérer ça côté Markdown.

### 5.8 Questions ouvertes sur le router

- **~~Q5.1~~** ✅ **décidé 2026-04-24** : **safe conditionnel**.
  - **1 atome détecté** → mode **fluide** : écriture directe + rapport a posteriori (l'erreur est rare et facile à corriger via `/mem-reclass`).
  - **>1 atome détecté** → mode **safe** par défaut : le router affiche le plan d'ingestion (liste des `[atome, zone cible, chemin]`), attend confirmation `o/n/e(dit)`. `n` annule, `e` permet de reclasser un atome avant écriture.
  - **Flag `--no-confirm`** force le mode fluide même sur multi-atomes (pour scripts et batch).
  - **Flag `--dry-run`** force le mode safe sans écriture (inspection seule du plan).
- **~~Q5.2~~** ✅ **décidé 2026-04-24** : heuristique qualitative (le LLM décide), pas de score numérique. Si le LLM n'est pas confiant, il route vers `00-inbox/` avec tag `ambigu` et mentionne sa raison dans le rapport.
- **~~Q5.3~~** ✅ **décidé 2026-04-24** : les atomes dérivés sont liés **bidirectionnellement** via Obsidian `[[...]]`. L'archive source cite les atomes extraits (« principes dégagés : [[no-force-push-sur-main]] »), et chaque atome extrait pointe vers l'archive (`context_origin: [[2026-04-24-...]]`). Obsidian Graph rendra visible la filiation.

## 6. Tags transverses

Les tags Obsidian ne sont pas de la décoration — ce sont les **indices primaires** pour la recherche, le filtrage et la vue graphique. Le vault v0.5.0 définit des **namespaces de tags** avec des règles strictes. Les tags libres restent autorisés mais recommandés hors des namespaces réservés.

### 6.1 Namespaces réservés

| Namespace | Valeurs | Obligatoire | Rôle |
|---|---|---|---|
| `zone/*` | `inbox`, `episodes`, `knowledge`, `procedures`, `principes`, `objectifs`, `personnes`, `cognition`, `meta` | ✅ | Redondance du champ `zone` du frontmatter — indispensable pour la vue graphique (Obsidian n'indexe que les tags, pas les champs frontmatter arbitraires). |
| `scope/*` | `perso`, `pro` | ✅ hors inbox/meta | Redondance du champ `scope`. Permet filtrage graphique par scope. |
| `kind/*` | `projet`, `domaine` | si zone = episodes | Distingue les deux sous-logiques de la mémoire épisodique (section 4.2). |
| `project/{slug}` | slug du projet | si `kind: project` ou rattachement transverse | Rattachement à un projet. Transverse : un principe peut porter `projet/secondbrain` pour indiquer son rattachement origine. |
| `domain/{slug}` | slug du domaine | si `kind: domain` ou rattachement transverse | Rattachement à un domaine permanent (santé, famille, veille-tech...). |
| `type/*` | `archive`, `note`, `concept`, `synthese`, `glossaire`, `fiche`, `reference`, `procedure`, `principe`, `objectif`, `personne`, `schema`, `metaphore`, `moodboard`, `sketch`, `index`, `doctrine`, `taxonomie`, `regle` | selon zone | Type de note à l'intérieur de sa zone. Voir section 4 pour les types valides par zone. |
| `modality/*` | `left`, `right` | ✅ hors inbox/meta | Dichotomie hémisphérique (section 2.4). `left` par défaut pour les écrits, `right` pour schémas / Excalidraw / moodboards. |
| `source/*` | `vecu`, `doc`, `archeo-git`, `archeo-atlassian`, `manuel` | si zone = episodes ou knowledge | Origine de l'atome. `manuel` par défaut pour une note créée à la main (pas ingérée par un skill). |
| `force/*` | `ligne-rouge`, `heuristique`, `preference` | si zone = principes | Niveau de contrainte du principe. |
| `horizon/*` | `court`, `moyen`, `long` | si zone = objectifs | Horizon temporel. |
| `statut/*` | `ouvert`, `en-cours`, `atteint`, `abandonne` | si zone = objectifs | État de l'objectif. |
| `categorie/*` | libre | optionnel | Sous-catégorie thématique (ex: `categorie/dev`, `categorie/famille`). |
| `ambigu` | (plat, pas de `/`) | flag | Posé par le router quand la confidence n'est pas suffisante pour classer (cf. section 5.4). |

### 6.2 Tags libres

L'utilisateur peut ajouter des tags libres hors des namespaces ci-dessus, pour ses propres axes de navigation (ex: `urgent`, `a-revoir`, `important`, `2026-q2`). **Recommandation** : rester simple, une dizaine de tags libres récurrents maximum, sinon la taxonomie se disperse.

### 6.3 Règles d'écriture

- **Casse** : tout en minuscules, slugifié (espaces → `-`, accents retirés).
- **Hiérarchie** : **un seul niveau de `/` par tag** (`scope/work` OK, `scope/work/entreprise` non — si besoin de granularité, créer un namespace dédié).
- **Pas de pluriel incohérent** : le nom du tag suit le nom de zone (`zone/episodes`, pas `zone/episode`).
- **Cohérence tag ↔ frontmatter** : le tag doit refléter le champ frontmatter correspondant. Un écart = bug, corrigé automatiquement par `mem-reclass` ou par passage du router.

### 6.4 Exemple de taxonomie complète

**Archive de session projet SecondBrain v0.5.0, pro, texte, source vécue** :

```yaml
tags:
  - zone/episodes
  - kind/project
  - projet/secondbrain
  - scope/work
  - modality/left
  - source/lived
  - type/archive
```

**Principe extrait de cette même archive** (atome dérivé, cf. section 5.6) :

```yaml
tags:
  - zone/principes
  - projet/secondbrain       # rattachement origine transverse
  - scope/work
  - modality/left
  - type/principle
  - force/ligne-rouge
  - categorie/dev
```

### 6.5 Rendu dans Obsidian Graph

Les namespaces permettent autant d'axes de coloration indépendants dans le plugin Extended Graph (cf. chantier annexe dans `context.md` SecondBrain). Suggestion de configuration, hors scope de ce document :

- **Couleur de nœud** = `zone/*` (9 couleurs pour les 9 zones)
- **Couleur de bordure / halo** = `scope/*` (2 teintes pour perso/pro)
- **Taille de nœud** = présence de `kind/project` (projets plus visibles que domaines)
- **Arcs transverses** = `project/{slug}` et `domain/{slug}` (met en évidence la filiation entre atomes d'un même fil)
- **Opacité** = `statut/abandonne` atténué pour les objectifs abandonnés

---

## 7. Structure fichier type (frontmatter canonique par zone)

Cette section consolide le frontmatter de chaque zone en un **référentiel unique**. Les détails de contenu sont en section 4.

### 7.1 Champs universels (toutes zones hors inbox/meta)

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | ✅ | Date de création du fichier. Mise à jour tolérée sur `context.md` et notes longues. |
| `zone` | enum | ✅ | `inbox`, `episodes`, `knowledge`, `procedures`, `principes`, `objectifs`, `personnes`, `cognition`, `meta`. |
| `scope` | enum | ✅ | `perso` ou `pro`. |
| `collective` | bool | ✅ (défaut `false`) | Flag de promotion vers CollectiveBrain. Non lu par SecondBrain v0.5.0. |
| `modality` | enum | ✅ | `left` ou `right`. Défaut `left`. `right` pour schémas / Excalidraw. |
| `tags` | liste | ✅ | Cf. section 6. Les tags redondent les champs frontmatter pour la vue graphique Obsidian. |

### 7.2 Champs complémentaires par zone

#### `00-inbox`

```yaml
---
date: YYYY-MM-DD
zone: inbox
tags: [zone/inbox]
---
```

Les champs `scope`, `collective`, `modality` sont **absents** (à fixer au reclassement).

#### `10-episodes` — archive de session (projet OU domaine)

```yaml
---
date: YYYY-MM-DD
heure: "HH:MM"              # format 24h
zone: episodes
kind: project                # ou: domaine
projet: {slug}              # si kind: project
domaine: {slug}             # si kind: domain
scope: {perso|pro}
collective: false
modality: left
source: lived                # ou: doc | archeo-git | archeo-atlassian | manuel
type: archive
tags: [zone/episodes, kind/project, project/{slug}, scope/*, modality/left, source/lived, type/archive]
derived_atoms: []           # optionnel — atomes dérivés par le router (section 5.6)
---
```

#### `10-episodes` — `context.md` d'un projet ou domaine

```yaml
---
zone: episodes
kind: {projet|domaine}
slug: {slug}
scope: {perso|pro}
collective: false
tags: [zone/episodes, kind/*, {projet|domaine}/{slug}, scope/*]
---
```

Pas de `date` (fichier mutable, non daté). Pas de `modality` (hérite `left` par défaut).

#### `20-knowledge` — note de connaissance

```yaml
---
date: YYYY-MM-DD
zone: knowledge
scope: {perso|pro}
collective: false
modality: {left|right}
source: {manuel|doc|archeo-*}
type: {concept|fiche|glossaire|synthese|reference}
sources: []                 # optionnel — URLs ou refs bibliographiques
tags: [zone/knowledge, scope/*, modality/*, type/*, {domaines libres}]
---
```

#### `30-procedures` — procédure / how-to

```yaml
---
date: YYYY-MM-DD
zone: procedures
scope: {perso|pro}
collective: false
modality: left
type: procedure
etapes: N                   # optionnel
duree_estimee: "HHhMM"      # optionnel
outils: []                  # optionnel
tags: [zone/procedures, scope/*, type/procedure, categorie/*]
---
```

#### `40-principles` — principe / heuristique / ligne rouge

```yaml
---
date: YYYY-MM-DD            # date d'adoption du principe
zone: principes
scope: {perso|pro}
collective: false
modality: left
type: principle
force: {ligne-rouge|heuristique|preference}
context_origin: "[[YYYY-MM-DD-...]]"  # lien vers archive fondatrice si applicable (Q4.3)
projet: {slug}              # optionnel, si rattaché à un projet origine
tags: [zone/principes, scope/*, type/principle, force/*, categorie/*]
---
```

#### `50-goals` — objectif / intention

```yaml
---
date: YYYY-MM-DD            # date d'écriture
zone: objectifs
scope: {perso|pro}
collective: false
modality: left
type: goal
horizon: {court|moyen|long}
echeance: YYYY-MM-DD        # optionnel
statut: {ouvert|en-cours|atteint|abandonne}
projet: {slug}              # optionnel, si rattaché à un projet
tags: [zone/objectifs, scope/*, type/goal, horizon/*, statut/*]
---
```

#### `60-people` — fiche personne

```yaml
---
date: YYYY-MM-DD
zone: personnes
scope: {perso|pro}
collective: false            # invariant : si sensitive: true alors collective: false
sensitive: true             # défaut — interdit mécaniquement collective: true (Q4.4)
modality: left
type: person
nom: "Prénom NOM"
role: ""                    # rôle / relation
organisation: ""            # pour les pros
contact:
  email: ""
  tel: ""
last_interaction: YYYY-MM-DD
tags: [zone/personnes, scope/*, type/person, categorie/*]
---
```

#### `70-cognition` — production non verbale

```yaml
---
date: YYYY-MM-DD
zone: cognition
scope: {perso|pro}
collective: false
modality: right             # toujours right par nature
type: {schema|metaphore|moodboard|sketch}
projet: {slug}              # optionnel
tags: [zone/cognition, scope/*, modality/right, type/*]
---
```

#### `99-meta` — méta-mémoire du vault

```yaml
---
date: YYYY-MM-DD
zone: meta
type: {index|doctrine|taxonomie|regle}
tags: [zone/meta, type/*]
---
```

Pas de `scope`, `collective`, `modality` (méta neutre, transverse).

### 7.3 Invariants cross-champs

Le router et `mem-reclass` vérifient ces invariants à l'écriture. Violation = bug bloqué ou corrigé :

1. **Scope perso ⇒ collectif false.** Toujours. `collective: true` sur `scope: personal` = erreur bloquante.
2. **Sensitive true ⇒ collectif false.** Si `sensitive: true` (personnes par défaut), `collective: true` interdit.
3. **Zone episodes ⇒ `kind` présent.** Jamais d'archive sans `kind: project` ou `kind: domain`.
4. **Kind projet ⇒ `projet: {slug}` présent et slug existant dans `10-episodes/projects/`.** Idem pour `kind: domain`.
5. **Tags reflètent frontmatter.** `zone: episodes` ⇒ tag `zone/episodes` obligatoire, et inversement.
6. **Modality absent ⇒ défaut `left`.** Appliqué à l'écriture.
7. **Date obligatoire hors inbox/meta + context.md/history.md.** Les contextes et historiques sont mutables, non datés.

### 7.4 Exemple complet — atomes dérivés d'un `mem-archeo`

Scénario : `/mem-archeo C:\_PROJETS\IRIS\MCP` traite le commit `fix(security): prevent force-push on main`. Le router produit 2 atomes.

**Atome 1 — archive du commit** (`10-episodes/projects/mcp-iris-connector/archives/2026-01-15-14h30-mcp-iris-connector-archeo-tag-v0-3-1.md`) :

```yaml
---
date: 2026-01-15
heure: "14:30"
zone: episodes
kind: project
projet: mcp-iris-connector
scope: work
collective: false
modality: left
source: archeo-git
type: archive
commit_sha: "abc1234"
derived_atoms: ["[[no-force-push-sur-main]]"]
tags: [zone/episodes, kind/project, projet/mcp-iris-connector, scope/work, modality/left, source/archeo-git, type/archive]
---
```

**Atome 2 — principe extrait** (`40-principles/work/dev/no-force-push-sur-main.md`) :

```yaml
---
date: 2026-01-15
zone: principes
scope: work
collective: false
modality: left
type: principle
force: ligne-rouge
context_origin: "[[2026-01-15-14h30-mcp-iris-connector-archeo-tag-v0-3-1]]"
projet: mcp-iris-connector
tags: [zone/principes, projet/mcp-iris-connector, scope/work, modality/left, type/principle, force/ligne-rouge, categorie/dev]
---
```

Les deux atomes sont **liés bidirectionnellement** (décision Q5.3) via `derived_atoms` et `context_origin`, rendant la filiation visible dans Obsidian Graph.

---

## 8. Impact sur les skills mem-*

La v0.5.0 passe de 11 skills à **17 skills + 1 composant core** (le router). Les 11 skills actuels restent (aucune suppression — préservation des habitudes utilisateur), mais leur implémentation est largement refondue pour s'appuyer sur le router et sur la nouvelle arborescence.

### 8.1 Inventaire v0.5.0

| Skill | Statut | Impact | Description v0.5.0 |
|---|---|---|---|
| **`mem` (nouveau)** | 🆕 universal | — | Router sémantique zéro-friction : reçoit un contenu, segmente, classe, écrit. Chemin par défaut pour toute ingestion libre. |
| `mem-archive` | ♻️ refonte | Élevé | Appelle le router avec **hint `zone: episodes`**. Préformate la note de session (date, projet/domaine courant, scope par défaut). Segmente si la note contient plusieurs atomes. |
| `mem-recall` | ♻️ refonte | Élevé | Charge `context.md` + dernières entrées `history.md` d'un projet OU domaine (argument). Charge aussi : **principes actifs** rattachés (`tag: project/{slug}`), **objectifs ouverts** (`statut: ouvert\|en-cours` + projet), **personnes-clés** récemment interagies. |
| `mem-search` | ♻️ refonte | Élevé | Grep plein-texte avec **filtres** : `--zone`, `--scope`, `--kind`, `--modality`, `--projet`, `--domaine`, `--type`, `--source`. Retourne les chemins + extraits. |
| `mem-list-projects` | ♻️ renommé → **`mem-list`** | Moyen | Liste projets ET domaines par défaut. Filtres : `--kind projet\|domaine`, `--scope perso\|pro`. Affiche état synthétique (nb archives, dernière session, objectifs ouverts). |
| `mem-doc` | ♻️ refactor | Moyen | Appelle le router avec **hint `source: doc`**. Résolution projet/domaine cible inchangée. En v0.5.1 : branche sur la batterie de doc-readers Python (feature reportée). |
| `mem-archeo` | ♻️ refonte | Élevé | **Plus d'archive monolithique** : chaque jalon Git produit plusieurs atomes via le router. Idempotence élargie : `source_milestone + type_atome + sujet` évite les doublons aux ré-ingestions. |
| `mem-archeo-atlassian` | ♻️ refonte | Élevé | Idem `mem-archeo` mais source = Confluence/Jira. Claude-only (prérequis MCP Atlassian). |
| `mem-digest` | ♻️ refactor | Moyen | Agrégation des N dernières archives **d'une zone** (pas seulement d'un projet). Ex: `/mem-digest --zone objectifs --scope pro` = état des lieux des objectifs pro. |
| `mem-rename-project` | ♻️ renommé → **`mem-rename`** | Moyen | Opère sur projet OU domaine. Met à jour le slug dans tous les tags `projet/{old}` → `projet/{new}` + les liens Obsidian `[[...]]` qui pointent vers l'ancien slug. |
| `mem-merge-projects` | ♻️ renommé → **`mem-merge`** | Moyen | Fusionne deux projets OU deux domaines (pas de mélange projet ↔ domaine). Réattribue archives, principes, objectifs, personnes, retire source de l'index. |
| `mem-rollback-archive` | ♻️ refactor mineur | Faible | Supprime la dernière archive **et ses atomes dérivés** (chaîne via `derived_atoms`). Demande confirmation si atomes dérivés orphelinisés. |
| **`mem-reclass` (nouveau)** | 🆕 | — | Change scope et/ou zone d'un contenu existant. Met à jour frontmatter + tags + déplace le fichier physiquement, réécrit les références croisées (`_index`, `historique`, liens Obsidian). Enforcement invariants section 7.3. |
| **`mem-note` (nouveau)** | 🆕 | — | Appelle le router avec **hint `zone: knowledge`**. Aide à saisir une note de connaissance rapidement (concept, fiche, synthèse). |
| **`mem-principle` (nouveau)** | 🆕 | — | Appelle le router avec **hint `zone: principes`**. Saisie rapide d'un principe avec demande du champ `force` si absent. |
| **`mem-goal` (nouveau)** | 🆕 | — | Appelle le router avec **hint `zone: objectifs`**. Demande `horizon` et `echeance` si absents. |
| **`mem-person` (nouveau)** | 🆕 | — | Appelle le router avec **hint `zone: personnes`**. Demande `nom`, `role`, `organisation`, `contact`. |
| **`mem-promote-domain` (nouveau)** | 🆕 | — | Promeut un ensemble d'items cohérents de `00-inbox/` vers un nouveau `10-episodes/domains/{slug}/`. Vérifie la règle anti-dérive (≥ 3 items au même fil). |
| **`_router` (composant core)** | 🆕 | — | Pas un skill en soi. Bloc procédural dans `core/procedures/_router.md`, inclus dans toutes les procédures d'ingestion via directive `{{INCLUDE _router}}` (nouvelle mécanique `deploy.ps1`). |

### 8.2 Impact par adapter

Les 4 adapters (Claude Code, Gemini CLI, Codex, Mistral Vibe) doivent être régénérés pour :

1. Prendre les procédures refactorées de `core/procedures/`.
2. Intégrer le nouveau composant `_router.md` via `{{INCLUDE _router}}`.
3. Déclarer les 6 nouveaux skills (`mem`, `mem-reclass`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`, `mem-promote-domain`).
4. Pour Gemini CLI spécifiquement : respecter la contrainte TOML literal strings (`'''`, cf. CLAUDE.md du projet) pour les nouveaux templates.
5. Pour Codex et Vibe : format Markdown brut, pas de contrainte TOML.

**Régénération complète** du répertoire cible (`~/.claude/skills/`, `~/.gemini/extensions/memory-kit/`, `~/.codex/prompts/` + `~/.codex/skills/`, `~/.vibe/skills/`) nécessaire — ne pas tenter de migration incrémentale, trop de changements.

### 8.3 Compatibilité rétroactive

**Aucune.** v0.5.0 est un breaking change assumé. Les vaults v0.4 ne sont pas lus par les skills v0.5. La migration (section 9) est une **opération unique** qui transforme un vault v0.4 en vault v0.5. Après migration, le vault est en mode v0.5 exclusivement.

### 8.4 Nouvelle mécanique `deploy.ps1` — directive `{{INCLUDE}}`

`deploy.ps1` supporte déjà `{{PROCEDURE}}` (injection de la procédure core dans un template adapter) et `{{CONFIG_FILE}}` (référence au fichier de config par plateforme). La v0.5.0 ajoute `{{INCLUDE _nom}}` pour inclure un bloc réutilisable depuis `core/procedures/_*.md`.

Pseudo-code :

```powershell
$procedureContent = Get-Content $procedurePath -Raw

# Résolution {{INCLUDE _xxx}} récursive (support nested, max profondeur 5)
while ($procedureContent -match '\{\{INCLUDE\s+(_\w+)\}\}') {
    $blocName = $matches[1]
    $blocPath = Join-Path $coreSource "$blocName.md"
    if (-not (Test-Path $blocPath)) {
        throw "Bloc {{INCLUDE $blocName}} introuvable : $blocPath"
    }
    $blocContent = Get-Content $blocPath -Raw
    $procedureContent = $procedureContent -replace "\{\{INCLUDE\s+$blocName\}\}", [regex]::Escape($blocContent) -replace '\\', '\\'
    # Protection contre récursion infinie
    if ($depth++ -gt 5) { throw "Profondeur d'inclusion dépassée dans $procedurePath" }
}
```

Avantages :

- **Single source of truth** pour le router : `core/procedures/_router.md` n'existe qu'une fois, inclus par toutes les procédures d'ingestion.
- **Testabilité** : un bloc `_router.md` modifié propage automatiquement à tous les skills qui l'incluent, après un `deploy.ps1`.
- **Extensible** à d'autres blocs communs : `_encoding.md` (la directive UTF-8 sans BOM), `_concurrence.md` (les patterns atomic write + hash check), `_frontmatter-universal.md`.

### 8.5 Renommages v0.4 → v0.5 (résumé)

Pour éviter la confusion, les commandes suivantes changent de nom. L'ancien nom reste disponible comme **alias déprécié** pour une version, puis retiré en v0.6 :

| Ancien | Nouveau |
|---|---|
| `mem-list-projects` | `mem-list` |
| `mem-rename-project` | `mem-rename` |
| `mem-merge-projects` | `mem-merge` |

Aucun autre renommage.

---

## 9. Plan de migration des archives existantes

### 9.1 Contexte

Au moment de la migration (fin 2026-04 prévue), le vault contient environ **50 archives** dans `archives/` (plat) et **7 projets** sous `projects/` (codemagdns, collectivebrain, gabrielle, gmt-knowledges, iris-sync, mcp-iris-connector, secondbrain). Aucun autre contenu (pas de notes de connaissance, pas de principes formalisés, pas d'objectifs explicites, pas de fiches personnes). Le refactor transforme cette structure project-centric en structure brain-centric.

### 9.2 Mapping v0.4 → v0.5

| v0.4 | v0.5 | Règle |
|---|---|---|
| `archives/YYYY-MM-DD-HHhMM-{slug}-{sujet}.md` (source `vecu\|doc\|archeo-*`) | `10-episodes/projects/{slug}/archives/YYYY-MM-DD-HHhMM-{slug}-{sujet}.md` | Le slug projet est extrait du frontmatter `projet:` ou du nom de fichier. Toutes les archives d'un projet sont déplacées dans son sous-dossier `archives/`. |
| `archives/YYYY-MM-DD-HHhMM-inbox-{sujet}.md` | `00-inbox/YYYY-MM-DD-{sujet}.md` | Préfixe `inbox-` dans le nom ou frontmatter `projet: inbox` → déplacement en inbox. |
| `projets/{slug}/context.md` | `10-episodes/projects/{slug}/context.md` | Déplacement tel quel. Le frontmatter est enrichi avec `zone: episodes`, `kind: project`, `slug`, `scope` (défaut `pro`, à confirmer manuellement). |
| `projets/{slug}/history.md` | `10-episodes/projects/{slug}/history.md` | Déplacement tel quel. Les liens relatifs `../../archives/...` sont réécrits en `archives/...` (archives désormais scopées au projet). |
| `_index.md` (legacy v0.4, à la racine) | `index.md` (à la racine, renommé) | Renommage + refonte : l'index doit refléter la nouvelle arborescence (liste par zone, plus par projet seulement). |
| `.obsidian/`, `.excalidraw.md`, `.canvas`, `.base` | Inchangés | Non touchés par la migration. |

### 9.3 Enrichissement du frontmatter à la migration

Les archives v0.4 ont un frontmatter partiel. À la migration, le script ajoute les champs manquants :

| Champ | Valeur à la migration |
|---|---|
| `zone` | `episodes` |
| `kind` | `projet` (tous les projets actuels sont des projets, pas des domaines — aucun domaine n'existait avant v0.5) |
| `scope` | **défaut `pro`**, à réviser manuellement après migration pour les archives perso (aucune pour l'instant a priori) |
| `collective` | `false` (toujours à la migration) |
| `modality` | `left` (toutes les archives actuelles sont textuelles) |
| `source` | conservé du frontmatter existant, ou `vecu` par défaut si absent |
| `type` | `archive` |
| `tags` | reconstruits à partir des champs ci-dessus, écrasent les tags existants (au risque de perdre des tags libres — limitation acceptée) |

### 9.4 Script de migration

Fichier : `scripts/migrate-vault-v0.5.py`. Implémentation Python pour robustesse cross-platform et accès UTF-8 natif.

**Principes** :

1. **Dry-run par défaut** (`--apply` pour exécuter). Le dry-run affiche le plan complet (source → destination, enrichissement frontmatter) sans rien écrire.
2. **Backup obligatoire** avant `--apply` : copie du vault entier en `{vault}.backup-YYYY-MM-DD-HHhMM/`. Le script refuse de s'exécuter sans backup.
3. **Idempotent** : si une archive a déjà été migrée (détection par hash ou présence dans la cible), le script la skip.
4. **Rapport** final avec compteurs : N fichiers déplacés, N enrichis, N ignorés, N erreurs.
5. **Rollback** possible via `scripts/rollback-vault-v0.5.py` qui restaure depuis le backup (opération simple : `rm -rf {vault} && cp -R {backup} {vault}`).

**Pseudo-étapes** :

```
1. Vérifier présence de {vault}/archives/ (sinon déjà migré).
2. Créer backup {vault}.backup-{timestamp}/.
3. Créer arborescence v0.5 dans le vault :
   00-inbox/ 10-episodes/projects/ 10-episodes/domains/
   20-knowledge/ 30-procedures/ 40-principles/ 50-goals/
   60-people/ 70-cognition/ 99-meta/
4. Pour chaque projet dans {vault}/projets/ :
   a. Déplacer context.md, history.md vers 10-episodes/projects/{slug}/
   b. Enrichir frontmatter (zone, kind, slug, scope, collectif)
5. Pour chaque archive dans {vault}/archives/ :
   a. Extraire le slug projet (frontmatter ou nom de fichier)
   b. Déterminer destination : 00-inbox/ ou 10-episodes/projects/{slug}/archives/
   c. Déplacer le fichier
   d. Enrichir frontmatter (zone, kind, scope, collectif, modality, type, tags)
   e. Réécrire les liens internes si nécessaire
6. Renommer {vault}/_index.md en {vault}/index.md (reste à la racine), refonte structurelle.
7. Copier docs/architecture/brain-architecture-v0.5.md vers {vault}/99-meta/doctrine.md.
8. Supprimer dossiers vides (archives/, projets/).
9. Rapport final + commit Git suggéré (si le vault est versionné).
```

### 9.5 Cas particulier — archives sans projet identifiable

Certaines archives peuvent manquer d'information projet claire (frontmatter incomplet, nom ambigu). Règle : **en cas de doute, route vers `00-inbox/`** avec tag `migration-v0.5-ambigu`. L'utilisateur les reclasse manuellement via `mem-reclass` après migration.

### 9.6 Validation post-migration

Checklist à exécuter manuellement après `--apply` :

- [ ] Backup présent et accessible.
- [ ] `archives/` et `projects/` supprimés (ou vides).
- [ ] `10-episodes/projects/` contient 7 sous-dossiers (codemagdns, collectivebrain, gabrielle, gmt-knowledges, iris-sync, mcp-iris-connector, secondbrain).
- [ ] Chaque projet a `context.md`, `history.md`, `archives/` (non vide).
- [ ] Frontmatter d'une archive au hasard contient `zone`, `kind`, `projet`, `scope`, `tags`.
- [ ] Tags Obsidian Graph affiche les 9 zones distinctes (si Extended Graph configuré).
- [ ] `index.md` présent, structure à jour.
- [ ] `99-meta/doctrine.md` présent (copie du doc de cadrage).
- [ ] `mem-recall secondbrain` charge le contexte correctement via les nouveaux skills v0.5.
- [ ] Aucun fichier en inbox (ou minimal + identifié).

---

## 10. Plan de livraison (phasage v0.5.0)

### 10.1 Vue d'ensemble

La refonte v0.5.0 se décompose en **6 phases séquentielles**. Durée cible (hors aléas) : **10 à 15 sessions de travail** utilisateur, sur 2 à 4 semaines calendaires.

| Phase | Livrable principal | Durée indicative | Dépendances |
|---|---|---|---|
| A | Doc de cadrage signé | 2 sessions | — |
| B | Infrastructure : arbo v0.5 + directive `{{INCLUDE}}` | 1 session | A |
| C | Router core (`_router.md`) + tests unitaires | 2 sessions | B |
| D | Refonte des 17 skills | 4–6 sessions | C |
| E | Script de migration + dry-run sur vault réel | 1–2 sessions | D |
| F | Release v0.5.0 (migration, tests terrain, tag, release notes) | 1 session | E |

### 10.2 Phase A — Cadrage

**Objectif** : ce document finalisé, revu et validé par l'utilisateur.

**Livrables** :
- `docs/architecture/brain-architecture-v0.5.md` avec les 11 sections rédigées
- Relecture utilisateur : chaque section validée ou amendée
- Signature (mention `statut: validé` dans le frontmatter du doc)

**Sortie** : document figé, utilisé comme référence par les phases suivantes.

### 10.3 Phase B — Infrastructure

**Objectif** : préparer le kit pour la v0.5 sans encore toucher aux skills.

**Livrables** :

1. **Nouvelle mécanique `deploy.ps1`** pour la directive `{{INCLUDE _xxx}}` (cf. section 8.4).
2. **Blocs réutilisables** dans `core/procedures/` :
   - `_encoding.md` (extraction de la directive UTF-8 sans BOM, actuellement dupliquée dans chaque procédure)
   - `_concurrence.md` (extraction des patterns atomic write + hash check)
   - `_frontmatter-universal.md` (réf aux 6 champs universels section 7.1)
   - `_router.md` (créé vide en phase B, rempli en phase C)
3. **Scaffold de la nouvelle arborescence** : création de 9 dossiers racines vides dans un **vault de test dédié** (pas encore dans le vault production).
4. **`memory-kit.json`** : ajout du champ `default_scope` (cf. section 3.5).

**Sortie** : deploy.ps1 capable d'assembler des procédures incluant des blocs, testé avec au moins une procédure refactorisée de demo.

### 10.4 Phase C — Router core

**Objectif** : implémenter le composant central, validé isolément avant d'être branché aux skills.

**Livrables** :

1. `core/procedures/_router.md` complet (procédure d'ingestion conforme à section 5).
2. **Jeu de tests** (manuel ou scripté) : 20 inputs représentatifs couvrant les 9 zones et les cas ambigus. Vérification que le router classe correctement.
3. Documentation intégrée à la procédure : exemples de segmentation, cascade d'heuristiques, format de rapport.

**Sortie** : un bloc `_router.md` prêt à être inclus dans toutes les procédures d'ingestion.

### 10.5 Phase D — Refonte des skills

**Objectif** : réécrire les 17 skills pour la v0.5. Découpage en lots prioritaires :

**Lot D1 — skills de lecture (non destructifs)** :
- `mem-recall` (refonte)
- `mem-search` (refonte)
- `mem-list` (renommage + refactor)
- `mem-digest` (refactor)

Validation : tests sur vault de test sans écriture, vérif que lecture fonctionne.

**Lot D2 — skills d'ingestion (utilisent le router)** :
- `mem` (nouveau, universal)
- `mem-archive` (refonte)
- `mem-doc` (refactor)
- `mem-archeo` (refonte)
- `mem-archeo-atlassian` (refonte, Claude-only)
- `mem-note`, `mem-principle`, `mem-goal`, `mem-person` (nouveaux)

Validation : tests sur vault de test, chaque skill produit les atomes attendus dans les bonnes zones.

**Lot D3 — skills de maintenance** :
- `mem-reclass` (nouveau)
- `mem-rename` (renommage + refactor)
- `mem-merge` (renommage + refactor)
- `mem-rollback-archive` (refactor mineur)
- `mem-promote-domain` (nouveau)

Validation : tests sur vault de test avec opérations destructives + rollback.

### 10.6 Phase E — Script de migration

**Objectif** : script prêt à transformer un vault v0.4 en vault v0.5 sans perte.

**Livrables** :
1. `scripts/migrate-vault-v0.5.py` conforme à section 9.
2. `scripts/rollback-vault-v0.5.py` pour retour backup.
3. **Test dry-run sur le vault réel de l'utilisateur** (`C:\_BDC\GMT\memory\`) — pas d'écriture, juste le plan. Validation manuelle du plan.
4. Checklist post-migration (section 9.6) exécutable.

**Sortie** : plan de migration validé, prêt pour exécution en phase F.

### 10.7 Phase F — Release v0.5.0

**Objectif** : bascule production.

**Étapes** :

1. **Git** : état propre, branche `main` à jour, tous les commits v0.5 pushés.
2. **Migration du vault réel** via `scripts/migrate-vault-v0.5.py --apply` (après backup automatique).
3. **Validation post-migration** : exécuter la checklist section 9.6.
4. **Tests terrain des skills refondus** :
   - `mem-recall secondbrain`
   - `mem-search --zone principes --scope pro`
   - `mem "test de l'ingestion libre"`
   - `mem-archeo` sur un dépôt Git pour valider la segmentation multi-atomes
5. **Tag annoté v0.5.0** + push tag.
6. **Release GitHub** via `gh release create v0.5.0` avec release notes complètes (breaking changes, nouvelle architecture, migration obligatoire, lien vers doctrine).
7. **Mise à jour README + CLAUDE.md du kit** pour refléter la nouvelle structure.

**Release notes v0.5.0 — trame** :

```markdown
# v0.5.0 — Refonte brain-centric

Breaking change. Structure du vault entièrement réorganisée autour des
fonctions mémorielles (épisodique, sémantique, procédurale, principes,
objectifs, personnes, cognition, meta). Les skills sont régénérés pour
travailler avec cette nouvelle structure.

## Migration obligatoire
- Exécuter `scripts/migrate-vault-v0.5.py` sur le vault existant avant
  d'utiliser les skills v0.5. Backup automatique du vault v0.4.

## Nouveautés
- Router sémantique `/mem` : ingestion libre avec classement automatique
- 5 nouveaux skills : mem-note, mem-principle, mem-goal, mem-person, mem-reclass
- Distinction projets / domaines dans 10-episodes/
- Flag scope perso/pro avec filtrage par skill
- Préparation CollectiveBrain via flag collectif

## Retirés
- L'ancienne structure projets/* + archives/* plat

## Documentation
- docs/architecture/brain-architecture-v0.5.md (doctrine complète)
- Copie dans 99-meta/doctrine.md du vault après migration
```

### 10.8 Post-v0.5.0

- **v0.5.1** : intégration de la batterie de doc-readers Python pour `mem-doc` (feature reportée depuis v0.4.1).
- **v0.6.0** : Phase 3 MCP — serveur `memory-kit` qui expose les skills refondus comme outils MCP. Stack déjà actée (SDK Python, hatchling + uv, stdio, Python ≥ 3.12).
- **CollectiveBrain v0.1** (projet séparé) : plugin Obsidian qui lit les atomes `pro` + `collective: true` et synchronise vers le vault collectif sur GMT Knowledges.

---

## 11. Questions ouvertes / décisions différées

*[À compléter au fil du cadrage]*

- **Q11.1** Numérotation des zones : préfixes numériques (`10-`, `20-`...) pour ordre visible ou noms propres seulement (`episodes/`, `knowledge/`) ? Pas de préférence utilisateur exprimée.
- **Q11.2** Profondeur max sous `20-knowledge/` — faut-il borner à N niveaux pour éviter l'explosion ?
- **Q11.3** Stratégie d'archivage des archives elles-mêmes (archives de plus de X années → zone cold storage ?).
- **Q11.4** Interface vault ↔ CollectiveBrain — à documenter dans CollectiveBrain, pas ici, mais à garder cohérent.
- **Q11.5** Router — cf. section 5.8 (Q5.1 mode safe vs fluide, Q5.2 seuil de confidence, Q5.3 liens bidirectionnels).
- ~~Q3.1 à Q3.4~~ → **tranchées 2026-04-24**, voir décisions D3.1 à D3.4 section 3.7.
- ~~Q4.2 à Q4.5~~ → **tranchées 2026-04-24**, voir section 4 (4.3 methodes, 4.7 sensitive) et section 5 (router).

---

*Fin du document de cadrage v0.2. Les 11 sections sont rédigées. Prochaine étape : revue utilisateur section par section, signature (statut: validé), puis démarrage phase B (infrastructure) selon le plan section 10.*
