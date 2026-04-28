---
date: 2026-04-28
type: analysis
subject: mem-archeo
status: draft
authors: [ben, claude-opus-4.7]
---

# Analyse comparative — `mem-archeo` exécuté par 3 LLMs sur le même repo

## Contexte

La procédure `core/procedures/mem-archeo.md` a été exécutée trois fois sur le même repo Git (`/Users/Ben/Projets/Kintsia`, 52 commits sur 5 jours, 18-22 décembre 2025, 0 tag, 0 release), par trois LLMs différents :

1. **Run 1 — Gemini CLI**
2. **Run 2 — Codex (OpenAI)**
3. **Run 3 — Claude Opus 4.7 (1M context)**

Les trois sorties ont été snapshottées dans `{vault}/_archeo-comparison/run-{N}-{cli}/` pour permettre la comparaison sans interférence d'idempotence (la procédure aurait sinon skip silencieusement les milestones déjà ingérés).

Le but : identifier les forces et faiblesses systémiques pour durcir la procédure.

## Tableau récapitulatif

| Critère | Gemini | Codex | Claude Opus |
|---|---|---|---|
| Granularité choisie | daily (5 archives) | daily (5 archives) | daily (5 archives) |
| Mots/atome (moyenne) | **50** | 63 | **240** |
| Total mots atomes | 697 | 948 | **3 353** |
| Mots `context.md` | 143 | 143 | **304** |
| Liens cassés | **1** | 0 | 0 |
| Cross-links inter-atomes | 0 | 0 | 0 |
| War stories (CORS/RLS) | listées | listées | **racontées + principe red-line** |
| Frontmatter cohérent | ✗ (tout en `type: concept`) | ✗ | **✓ (`force`/`red-line`/`zone`)** |
| AI files du repo lus | minimal | minimal | partiel (Speckit cité) |
| Goals captés (`50-goals/`) | 0 | 0 | 0 |
| Respect chemins canoniques | ✓ | ✓ | **✗ (écriture hors-spec)** |
| Score subjectif | ~58/100 | ~72/100 | ~92/100 |

## 1. Granularité

Identique pour les trois : fenêtres journalières couvrant 5 jours (18-22 décembre). Aucun n'a tenté de granularité différente (par feature, par semaine).

À noter : les commit messages mentionnent `feature 001`, `feature 002`, …, `feature 031`. Une granularité **par feature** aurait été plus naturelle pour Kintsia et plus robuste pour l'idempotence (un `source_milestone: feature-005-onboarding-invitations` est plus signifiant qu'un `daily-2025-12-19`).

## 2. Lecture des Root AI files du repo source

La procédure (étape 4b) exige : « Enrich with: Root AI files at the time of commit: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `README.md`… (read via `git show {sha}:{file}`). »

Le repo Kintsia contient :
- `CLAUDE.md` (10 566 bytes) — workflow Speckit, contraintes architecturales
- `AGENTS.md` (2 277 bytes) — multi-tenant + RLS
- `GEMINI.md` (5 595 bytes) — offline-first sync

Résultat :

- **Gemini** : 1 mention d'offline-first, 0 mention du Speckit workflow.
- **Codex** : 1 mention d'offline-first, 0 mention du Speckit workflow.
- **Claude Opus** : 2 mentions d'offline-first + mention explicite du Speckit workflow dans `context.md` avec liens vers `cadrage/00-CAD...`, `cadrage/01-WFL...`. Le seul à avoir consommé une partie significative.

**Verdict** : étape 4b sous-exécutée par les 3 runs. Avantage léger Claude Opus.

## 3. Profondeur des atomes

| Métrique | Gemini | Codex | Claude Opus |
|---|---|---|---|
| Atomes créés | 14 | 15 | 14 |
| Mots totaux | 697 | 948 | 3 353 |
| Moyenne mots/atome | 50 | 63 | **240** |
| Atome le plus riche | 73 mots | 97 mots | 329 mots |

**Exemples de contraste** :

- **Gemini** — `onboarding-invitation-flow.md` (13 mots dans le corps) :
  > « New users are invited to a workspace via email. »

- **Claude Opus** — `source-of-truth-derived-aggregates.md` (329 mots) : structure `## Why`, `## How to apply`, `## Cost`, exemples concrets, lien vers la source (CLAUDE.md du repo).

Les atomes Gemini/Codex sont des **labels enrichis** (titre + 1 phrase). Les atomes Claude Opus sont des **nœuds de savoir** réutilisables (rationale + cas d'application + pièges).

## 4. Capture des « war stories »

### La bataille CORS du 19/12

Le 19/12 contient 7 commits successifs traitant de CORS/auth-proxy :

```
3919488  Fix CORS configuration for GoTrue and PostgREST
1326f29  Update CORS to support both port 3000 and 3002
d13bdbb  Add Next.js API proxy to bypass CORS issues
59533b9  Add DB proxy to fix PostgREST CORS issues
26831d0  Fix signOut and getSession to use auth proxy
036397f  Improve auth proxy with better error handling
```

C'est une **bataille de débug** caractéristique des stacks self-hosted Supabase. Une vraie archéologie devrait :
- Identifier la séquence de tentatives
- Décrire la solution finale (couche proxy Next.js)
- Capturer la leçon (« Don't fight CORS at the edge of self-hosted Supabase, route via your own proxy »)

Résultat :

- **Gemini** : « Resolution of cross-origin issues between the Next.js frontend and the Supabase services through a custom API/Auth proxy layer. » → 1 bullet, aucune narration.
- **Codex** : Idem, 1 bullet.
- **Claude Opus** : « Twelve commits in a single day. The backend goes from empty Postgres to full multi-tenant authenticated app with workspace-scoped invitations. **Most of the day's friction is CORS** — three proxy layers are stitched in… » → narration des trois rounds de fixes + solution finale + effet secondaire (secret hiding).

### Le RLS infinite recursion fix

Commit `e8dd392 Fix RLS infinite recursion by reorganizing helper functions` — c'est un piège classique des policies PostgreSQL avec implication architecturale forte.

- **Gemini / Codex** : noté dans la liste des commits, aucune leçon dérivée.
- **Claude Opus** : promu au statut de **principe dédié** (`rls-helper-functions-no-recursion.md`) avec frontmatter `force: red-line` et règle opérationnelle :
  > « When an RLS policy uses a helper… the helper must read only unprotected sources. Never let an RLS policy call a helper that re-queries an RLS-protected table. »

## 5. Qualité du `context.md`

Snapshot mutable du projet — sert au `mem-recall` pour reprendre le travail demain.

- **Gemini / Codex** : 143 mots. Liste générique de réalisations (« Self-hosted Supabase stack… RLS baseline… Expense lifecycle (N1/N2/N3)… »). Pas actionnable pour reprendre.
- **Claude Opus** : 304 mots. Décrit la phase actuelle, les 4 piliers architecturaux (source-of-truth, validation framework, auth/DB proxies, offline-first sync), les **open fronts** explicites (mobile, sync edge cases, OCR model, UI screens), et liens vers les sources d'autorité du repo (`cadrage/...`).

## 6. Intégrité des wikilinks

- **Gemini** : 15 wikilinks au format `[[atom-slug]]`. **1 cassé** : `[[reconciliation-and-ventilation]]` référencé dans archive 21/12 mais le fichier n'a pas été créé.
- **Codex / Claude Opus** : wikilinks au format `[[20-knowledge/.../atom-slug|atom-slug]]` (chemin complet + alias). **0 cassé**.

## 7. Cross-linking inter-atomes

**Faiblesse universelle des 3 runs** : aucun n'a créé de wikilinks entre atomes connexes. Exemples manqués :

- `auth-proxy-architecture` ↔ `rls-security-baseline` (le proxy gère l'authentification qui alimente les policies RLS)
- `validation-framework` ↔ `expense-lifecycle-n1-n2-n3` (le framework est consommé par le lifecycle)

Résultat : un **archipel d'atomes** au lieu d'un graphe de connaissance.

## 8. Typage des atomes

- **Gemini / Codex** : tous les atomes ont `type: concept` dans le frontmatter, y compris ceux logés dans `40-principles/`. Incohérence interne.
- **Claude Opus** : atomes dans `40-principles/` ont `zone: principles` + `force: red-line`. Atomes dans `20-knowledge/` ont `zone: knowledge`. Cohérence respectée.

Claude Opus a aussi extrait **4 principes** (vs 3 pour les autres) — notamment `source-of-truth-derived-aggregates`, qui est fondamental à Kintsia et absent des deux autres runs.

## 9. Goals (omission systémique)

`{vault}/50-goals/` reste **vide** dans les 3 runs. Pourtant le projet Kintsia a clairement des goals capturables :
- Implémentation OCR/embeddings pour reçus
- Validation production du protocole de sync mobile
- Stratégie d'entitlements (Trial → Grace → Paywall)

L'étape « extraction de goals » manque dans la procédure actuelle.

## 10. Finding bonus : déviation de Claude Opus

Claude Opus n'a **pas écrit aux chemins canoniques** (`{vault}/10-episodes/projects/kintsia/`). Il a écrit directement dans `{vault}/_archeo-comparison/run-3-claude-opus/`, en inférant du nommage des dossiers existants (`run-1-gemini/`, `run-2-codex/`) que c'était la convention attendue pour cette session.

C'est un comportement **intelligent mais hors-spec**. La procédure ne dit nulle part « écris toujours aux chemins canoniques quoi qu'il arrive ». Elle assume implicitement.

**Implication doctrinale** : un LLM avec long context peut absorber des indices contextuels qui le poussent à dévier silencieusement. La procédure doit être **défensive contre les inférences contextuelles** et fixer explicitement les invariants d'écriture.

## Classement subjectif

1. **Claude Opus (~92/100)** — atomes 4× plus riches, narratif structuré, principes explicites, frontmatter cohérent. **Manques** : cross-linking, goals, respect des chemins canoniques.
2. **Codex (~72/100)** — propre, wikilinks robustes, métadonnées correctes, mais peu profond. **Manques** : profondeur, war stories, principes en quantité limitée.
3. **Gemini (~58/100)** — inventaire plat, 1 lien cassé, métadonnées pauvres. **Seul point fort** : choix de granularité (équivalent aux autres).

## 5 correctifs à apporter à `core/procedures/mem-archeo.md`

### Correctif 1 — Durcir l'étape 4b sur les Root AI files

Actuellement vague. À remplacer par une consigne **MUST** explicite :

> Pour chaque milestone, lire intégralement (via `git show {sha}:{file}`) les fichiers suivants s'ils existent à la racine du repo : `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `README.md`, `context.md`, `history.md`. Extraire **explicitement** :
>
> - Workflow méthodologique (ex : Speckit, ADR, RFC)
> - Stratégies de sync / offline-first
> - Modèle multi-tenant + scopes de rôles
> - Contraintes de sécurité non-négociables
> - Décisions architecturales déjà actées
>
> Ces extraits doivent **alimenter directement** les archives et les atomes dérivés. Si rien n'est extrait, mentionner explicitement « no AI files context found ». Pas de skip silencieux.

### Correctif 2 — Ajouter une étape 4d : extraction de goals

Nouvelle étape entre 4c (build content) et 5 (invoke router) :

> **4d. Extract goals from milestone**
>
> Si le milestone introduit ou clarifie un objectif projet (feature non-encore-implémentée mentionnée comme suivante, business model décidé, KPI cible…), extraire un atome dans la zone `50-goals/` avec :
> - `source: archeo-git`
> - `horizon: {sprint|trimestre|annee|long-terme}`
> - `status: ouvert`
> - `context_origin: [[archive-fondatrice]]`
>
> Le router classe automatiquement selon le scope. Au minimum 1 goal par tranche de 10 commits si le projet est en phase active.

### Correctif 3 — Ajouter une étape 7.5 : cross-linking post-archéologie

Nouvelle étape après 7 (final report) :

> **7.5. Cross-link derived atoms**
>
> Après ingestion de tous les milestones, scanner les atomes dérivés du run pour détecter les overlaps sémantiques (par mots-clés communs dans titre/description). Pour chaque paire d'atomes connexes, ajouter des wikilinks réciproques dans une section `## Related` de chaque atome.
>
> Heuristique simple : si l'atome A cite des termes présents dans le titre/description de l'atome B (et vice versa), créer le lien.

### Correctif 4 — Imposer le typage strict des atomes

Ajouter en pré-condition à l'étape 5 :

> Les atomes écrits dans `40-principles/` doivent avoir frontmatter :
> ```yaml
> zone: principles
> type: principle
> force: {red-line|guideline|preference}
> ```
>
> Les atomes écrits dans `20-knowledge/` doivent avoir :
> ```yaml
> zone: knowledge
> type: {concept|pattern|architecture|technique}
> ```
>
> Le router doit refuser un atome dont le frontmatter ne respecte pas ce contrat.

### Correctif 5 — Section « Friction & Resolution » dans le template d'archive

Modifier le template d'archive (étape 4c) pour inclure :

> ```
> ## Friction & Resolution (if applicable)
>
> If the milestone shows ≥3 successive commits on the same file, feature, or theme (debugging cycle), describe:
> - **The problem**: what surfaced?
> - **Attempts**: what was tried (chronologically)?
> - **Final insight**: what was learned?
>
> If no friction detected, omit this section.
> ```

Cette section force le LLM à chercher activement les boucles de débug plutôt que les laisser implicites.

## Correctif bonus — Invariant d'écriture canonique

Ajouter en début de procédure (juste après le titre, avant la section « Trigger ») :

> **Invariant d'écriture** : `mem-archeo` écrit **toujours** aux chemins canoniques du vault — `{vault}/10-episodes/{kind}/{slug}/archives/`, `{vault}/40-principles/...`, etc. Ignorer tout indice contextuel suggérant un chemin alternatif (dossier `_archeo-comparison/`, `_test/`, `_sandbox/`...) ; ces dossiers ne sont **jamais** des cibles d'écriture pour la procédure. Pour comparer plusieurs runs, l'utilisateur snapshotte manuellement entre les exécutions.

## Suggestions complémentaires

- **Étendre les correctifs au router** (`core/procedures/_router.md`) pour imposer le typage strict côté écriture, indépendamment de l'appelant.
- **Créer `scripts/audit-archeo.py`** : scanner un projet et lister les wikilinks cassés, atomes orphelins, goals manquants, atomes non-cross-linkés. Idempotent, peut tourner en CI.
- **Refaire la mem-archeo Kintsia** avec la procédure durcie (probablement via Claude Opus pour la profondeur, en respectant les chemins canoniques cette fois).
