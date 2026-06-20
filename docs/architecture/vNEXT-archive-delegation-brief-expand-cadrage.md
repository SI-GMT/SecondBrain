# vNEXT — Délégation de l'archivage : pattern brief→expand+gate (cadrage)

> Optimisation de coût et de latence du cycle `mem-archive` (mode full) par délégation de la **phase de rendu** à un subagent low-reasoning, en préservant la qualité d'une synthèse thinking-high. Le jugement reste au modèle fort ; seul l'expansion mécanique descend de tier. Filet de qualité déterministe en sortie.

## Table des matières

1. [Motivation chiffrée](#1-motivation-chiffrée)
2. [Où vit l'intelligence — analyse du flux actuel](#2-où-vit-lintelligence--analyse-du-flux-actuel)
3. [Architecture cible — 3 phases](#3-architecture-cible--3-phases)
4. [Le brief — schéma canonique](#4-le-brief--schéma-canonique)
5. [Phase A — orchestrateur (modèle fort)](#5-phase-a--orchestrateur-modèle-fort)
6. [Phase B — expander (subagent cheap)](#6-phase-b--expander-subagent-cheap)
7. [Le gate — invariants en écriture](#7-le-gate--invariants-en-écriture)
8. [Fallback et escalade](#8-fallback-et-escalade)
9. [Découpage d'implémentation](#9-découpage-dimplémentation)
10. [Discipline de cohérence](#10-discipline-de-cohérence)
11. [Risques et décisions ouvertes](#11-risques-et-décisions-ouvertes)

---

## 1. Motivation chiffrée

Benchmark d'un `/mem-archive` réel (session 2026-06-12, projet `secondbrain`, Opus 4.8 high-effort, 13 turns assistant uniques), extrait du log JSONL de session :

| Poste | Tokens | $/MTok | Coût |
|---|---|---|---|
| cache-creation | 575 395 | 6.25 | $3.60 |
| cache-read | 6 706 745 | 0.50 | $3.35 |
| output | 21 284 | 25 | $0.53 |
| fresh input | 726 | 5 | $0.004 |
| **Total** | | | **≈ $7.49** |
| **Wall clock** | | | **292 s** |

**Constat structurant : 93 % du coût = contexte, pas output.** Les 6,7 M de cache-read viennent de 13 turns Opus qui relisent chacun ~515 k tokens (toute la session vit dans la fenêtre). L'artefact persisté (archive 7 747 c + context 9 274 c + history 697 c ≈ 4,7 k tokens) ne représente que ~22 % de l'output, lui-même ~7 % du coût total.

Le levier n'est donc **pas** le tier du modèle ni le thinking output, mais le **collapse de la taille de contexte** : faire le jugement une fois sur 550 k, puis rendre l'artefact sur ~15 k au lieu de 515 k × 13.

Projection cible (détail §3, §11) : **~$0.66 (–91 %, ~11×), ~80-110 s (~3×)**. Plancher irréductible = la passe de jugement Opus (~$0.30-0.60), qui matérialise la contrainte « qualité = thinking-high ».

---

## 2. Où vit l'intelligence — analyse du flux actuel

Le tool MCP `mem_archive` (`mcp-server/src/memory_kit_mcp/tools/archive.py`) est **déjà 100 % déterministe, zéro LLM**. Il reçoit du contenu déjà synthétisé (`archive_subject`, `archive_body_md`, `context_md`, `phase`, `archive_extra_fm`) et exécute la mécanique : nom de fichier horodaté, frontmatter, insertion `history.md`, réécriture sigil `<repo>/...`, garde wikilinks (`_enforce_wikilinks`), refus projet archivé, MUST keys archeo-git.

Corollaire : **il n'y a rien à déléguer côté persist.** Un subagent qui appellerait simplement le tool = overhead pur.

Toute l'intelligence vit dans le **caller LLM** qui synthétise `archive_body_md` et `new_context_md` depuis la conversation : trancher décision vs remarque, séparer validé/en-cours, extraire atomes dérivés, **préserver les décisions cumulées**, prose dense resumable. C'est exactement la part « thinking-high » à préserver — décision structurante #20 (collecteur déterministe MCP + sémantique LLM) appliquée récursivement.

Tension frontale : *agent low-reasoning + qualité high* est incompatible si on confie le **jugement** à l'agent cheap. La résolution : ne déléguer que l'**expansion** d'un brief où tout le jugement est déjà figé par le modèle fort.

---

## 3. Architecture cible — 3 phases

```
┌─ Phase A : ORCHESTRATEUR (modèle fort, main thread) ──────────────┐
│  Lit la session (550k) UNE fois. Produit un BRIEF structuré       │
│  compact : tout le jugement, zéro prose longue.                   │
│  Output ~1.5-2.5k tokens.                                          │
└───────────────────────────┬───────────────────────────────────────┘
                            │ brief (JSON) + context.md actuel + template
                            ▼
┌─ Phase B : EXPANDER (subagent cheap, fenêtre fraîche ~15k) ───────┐
│  Reçoit le brief. AUCUN jugement. Expanse en :                    │
│   - archive_body_md (prose)                                        │
│   - new_context_md (snapshot réécrit)                              │
│  Appelle mem_archive(mode="full", ...).                           │
└───────────────────────────┬───────────────────────────────────────┘
                            │ archive_body_md, new_context_md
                            ▼
┌─ Phase C : GATE (déterministe, dans mem_archive) ────────────────┐
│  Invariants durs déjà en place : wikilinks, sigils, MUST keys,    │
│  refus archivé. + NOUVEAU : préservation des décisions cumulées.  │
│  Échec → refus d'écriture, message structuré → retry/escalade.    │
└────────────────────────────────────────────────────────────────────┘
```

Le brief est l'**interface** : il porte 100 % du jugement et 0 % de la prose. Phase B ne décide jamais quoi dire, seulement comment le formuler.

---

## 4. Le brief — schéma canonique

Le brief est un objet structuré (JSON, validé Pydantic côté MCP) produit par Phase A. Chaque champ « load-bearing » pour la qualité doit être **complet** dans le brief — Phase B ne comble aucun trou.

```jsonc
{
  "slug": "secondbrain",                    // projet/domaine résolu
  "kind": "project",                         // project | domain
  "branch_context": "main",                  // pour routing global vs feature
  "archive_subject": "worklog v0.14.1 + desktop in-place update v0.12.1",

  // --- JUGEMENT (figé par le modèle fort) ---
  "session_arcs": [                          // 1 entrée = 1 grand bloc de travail
    {
      "title": "mem-worklog finalisé (engine v0.14.0 → v0.14.1)",
      "points": [                            // bullets factuels, PAS de prose
        "3 niveaux brief/digest/detailed",
        "persist domaine worklogs, idempotent semaine ISO",
        "digest courriel 4 blocs sans temporalité"
      ],
      "files": ["<repo>/core/procedures/mem-worklog.md", "..."]
    }
  ],

  "decisions_new": [                         // décisions NOUVELLES de cette session
    { "text": "digest courriel = 4 blocs sans temporalité", "why": "durée portée par Jira" }
  ],

  "decisions_cumulative": [                  // LISTE COMPLÈTE des décisions à reporter
    "Bake-at-build pour artefacts gelés",    // dans le nouveau context.md.
    "Absolute path dans configs MCP",        // Source du gate de préservation (§7).
    "..."                                     // Phase A la fournit intégralement.
  ],

  "state": {
    "phase": "4 releases livrées — engine v0.14.1 + sb-desktop-v0.12.1",
    "validated": ["engine 577 passed/83%", "desktop 154 passed/73%"],
    "in_progress": []
  },

  "next_steps": [
    "deploy.ps1 -RepairMcp → pipx engine 0.14.1",
    "versionner ou gitignorer RELEASE_NOTES_* desktop"
  ],

  "derived_atoms": [                         // atomes à router hors archive
    { "zone": "40-principles", "title": "...", "body_hint": "..." }
  ],

  "active_assets": ["https://github.com/SI-GMT/SecondBrain/releases/tag/v0.14.1"],

  // --- VERBOSITÉ (paramètre de rendu, pas de jugement) ---
  "verbosity": "detailed"                    // brief | digest | detailed
}
```

Invariants du brief :

- **`decisions_cumulative` est exhaustif.** C'est le contrat dur : Phase B doit toutes les rendre, le gate (§7) le vérifie mécaniquement. Phase A les fournit en lisant le `context.md` courant + les décisions de la session.
- **`points` / `*_hint` = bullets, jamais de prose.** L'expansion en phrases est le travail de Phase B.
- **Aucun champ optionnel masquant du jugement.** Si une info manque au brief, Phase B ne l'invente pas — elle est perdue. La complétude du brief est la responsabilité de Phase A.

---

## 5. Phase A — orchestrateur (modèle fort)

Exécutée par le modèle fort dans le main thread, au déclenchement du mode full de `mem-archive` (signal explicite : `/mem-archive`, `/clear`, « on archive », etc.).

Responsabilités :

1. Résoudre projet/domaine + branche (logique inchangée, cf. `mem-archive.md` §Détection).
2. Lire le `context.md` courant (pour `decisions_cumulative` et le delta).
3. **Synthétiser le brief** depuis la conversation. C'est l'unique passe de raisonnement coûteuse — elle relit les ~550 k une fois. Output petit (le brief), pas la prose finale.
4. Déléguer à Phase B via le tool `Agent` :
   - `subagent_type` : agent dédié `mem-archive-expander` (cf. §6), **pas** `fork` (fork hérite les 550 k → annule le gain contexte).
   - `model: haiku` (ou le tier cheap courant).
   - `prompt` : le brief sérialisé + chemins (`context.md` actuel, template vault).
5. Relayer le reçu de Phase B à l'utilisateur (3 lignes : archive créée / atomes / context mis à jour).

Phase A **n'écrit jamais** `archive_body_md` ni `new_context_md`. Si elle le faisait, le gain serait nul (le coût est dans le contexte relu pour produire la prose, pas dans la prose).

---

## 6. Phase B — expander (subagent cheap) — design agnostique

Subagent à fenêtre fraîche, contexte ~15 k (brief + `context.md` actuel + template). Tier cheap (Haiku). Tools : `Read`, `mem_archive` (MCP), `mem_read_context`. **Pas** `Write`/`Edit` direct vers le vault — toute écriture passe par `mem_archive` (persist déterministe + gate).

**Le contrat de l'expander = un bloc `core/` unique** (`core/procedures/_archive-expander.md`), prose host-agnostique. Deux consommateurs, zéro duplication :

1. **Chemin universel** — la procédure `mem-archive.md` l'inline via `{{INCLUDE _archive-expander}}` → le contrat est dans le skill `mem-archive` déployé de **chaque** plateforme. L'orchestrateur le passe au subagent que son hôte sait spawner. Fonctionne sur **tout CLI ayant une capacité de subagent**, sans config par plateforme. (C'est ce chemin qu'a validé le dogfood : spawn inline d'un agent Haiku avec le contrat.)
2. **Agent enregistré Claude Code** — `adapters/claude-code/agents/mem-archive-expander.template.md` (frontmatter `model: haiku` + tools restreints + `{{INCLUDE _archive-expander}}`), déployé vers `~/.claude/agents/` par le pas « Agents » de `deploy.ps1`/`deploy.sh`. `subagent_type` first-class, modèle/tools forcés.

**Capability-gating, pas d'invention** : Claude Code est la seule plateforme dont le mécanisme d'agent enregistré est vérifié. Les autres (Codex/Gemini/Vibe/Copilot/Antigravity) reçoivent le contrat **inline** via leur skill (chemin 1) — on ne fabrique pas de format d'agent non vérifié. Un `adapters/{plateforme}/agents/` sera ajouté quand son mécanisme natif sera confirmé.

Le rendu prose à partir d'un squelette complet est faiblement « reasoning » : c'est de la mise en forme. La qualité tient parce que (a) le jugement est pré-figé dans le brief, (b) le gate rattrape les omissions de substance (pas le style).

---

## 7. Le gate — invariants en écriture

Le gate vit **dans `mem_archive`** (et son équivalent skill-mode). Trois invariants existent déjà ; un quatrième est ajouté.

| Invariant | Mécanisme | Statut |
|---|---|---|
| Wikilinks résolvent | `_enforce_wikilinks` / `find_dangling` | existant |
| Sigils `<repo>/...` | `rewrite_abs_paths_to_sigil` | existant |
| MUST keys archeo-git | `_validate_archeo_git_archive_fm` | existant |
| Refus projet archivé | `_resolve_active` | existant |
| **Préservation décisions cumulées** | `_enforce_cumulative_preserved` (param `expect_decisions`) | livré |

### Nouvel invariant — préservation des décisions cumulées

Le seul vrai risque qualité du pattern : Phase B (cheap) **droppe une décision cumulée** en réécrivant `context.md`. Filet déterministe :

1. `mem_archive` accepte un paramètre optionnel `expect_decisions: list[str]` (= `brief.decisions_cumulative`, identifiants courts).
2. Avant écriture du nouveau `context.md`, pour chaque entrée, vérifier qu'une signature normalisée (squelette alphanumérique, cf. `resolve_slug` tolérant, décision #18) apparaît dans `new_context_md`.
3. Toute entrée absente → lève `CumulativeDecisionDroppedError(ValueError)` listant les manquantes. **Aucune écriture partielle.**

Le check est lexical, pas sémantique — il garantit la **présence**, pas la qualité de reformulation. Suffisant : la reformulation prose est mécanique, l'oubli est le risque réel.

Note : `expect_decisions` est optionnel — en archivage classique (sans délégation) il vaut `None` et le check est no-op. Backward-compatible.

---

## 8. Fallback et escalade

Cascade en cas d'échec, du moins cher au plus cher :

1. **Gate échoue (décision droppée / wikilink dangling)** → `mem_archive` renvoie l'erreur structurée à Phase B (Haiku). L'agent corrige en une passe (la cause est listée) et re-appelle. Cheap.
2. **Phase B échoue 2× sur le même gate** → escalade : le main thread (Opus) reprend la main, produit lui-même `archive_body_md` + `new_context_md` et appelle `mem_archive` (= flux actuel). Coûteux mais sûr. Logge l'escalade.
3. **Phase B meurt (terminal API error, skip user)** → `Agent` renvoie `null` → escalade directe à l'étape 2.
4. **MCP indisponible** → skill-mode fallback inchangé (Phase A écrit directement, pas de délégation). Le pattern est une optimisation, jamais un point de défaillance unique.

La contrainte « qualité = thinking-high » est tenue par construction : tout chemin de défaillance escalade vers le modèle fort, jamais vers une archive dégradée persistée.

---

## 9. Découpage d'implémentation

Statut : 1-5 et 7-8 **livrés** (commits `feat/sub-agent-archiving`). 6 (bench formel) reste.

1. ✅ **Schéma brief** : `ArchiveBrief` + sous-modèles + validators dans `tools/_models.py`. Pas un tool MCP — contrat partagé Phase A ↔ Phase B.
2. ✅ **Gate** : `CumulativeDecisionDroppedError` + `_decision_signature` + `_enforce_cumulative_preserved` + param `expect_decisions` câblé (incremental + full) dans `archive.py`. 6 tests (`test_archive.py`), suite 583 passed / 83.23 %.
3. ✅ **Contrat expander = bloc core** `core/procedures/_archive-expander.md` (source unique, host-agnostique).
4. ✅ **Procédure `mem-archive.md`** : section « Delegated execution » (défaut full, pas de flag), Phase B agnostique (agent enregistré OU spawn inline), `{{INCLUDE _archive-expander}}` embarque le contrat dans le skill de chaque plateforme. Skill-mode = fallback.
5. ✅ **Agent Claude Code + deploy** : `adapters/claude-code/agents/mem-archive-expander.template.md` (frontmatter + include) + pas « Agents » dans `Deploy-ClaudeCode` / `deploy_claude_code` (includes-only, ni `{{PROCEDURE}}` ni MCP-first). `sync.json` recalculé via `sync update`.
6. ⏳ **Bench de validation** : un vrai `/mem-archive` délégué mesuré (output Opus, cache-read, latence) vs baseline §1. Data point dogfood : 51 s / 41 k tokens Haiku, 4 tool-uses, gate passé — à transformer en mesure propre.
7. ✅ **CLAUDE.md** : discipline classe d'asset `agents/` + capability-gating + procédure d'ajout d'un subagent.
8. ✅ **Vérif deploy** : parse `deploy.ps1` (Parser) + `bash -n deploy.sh` OK ; include résolu sans fuite (agent template ET procédure).

---

## 10. Discipline de cohérence

- **`core/procedures/mem-archive.md` ↔ `tools/archive.py`** : tout changement du gate ou du contrat brief co-commité, `sync.json` recalculé (cf. CLAUDE.md §manifest spec-drift).
- **Skill-mode ≡ MCP-mode** : le gate de préservation doit aussi être appliqué (checklist manuelle) par le caller skill-mode sans MCP. Documenter dans la procédure.
- **`deploy.ps1` ↔ `deploy.sh`** : le pas « Agents » (classe d'asset `agents/`) existe dans les deux (PowerShell `Resolve-IncludeDirectives` ; Bash `assemble_procedure` `skill_name` vide = includes-only). Tout subagent ajouté = co-commit + parse des deux scripts. Détail dans CLAUDE.md §Subagents.
- **Contrat = bloc core unique** : `_archive-expander.md` consommé par la procédure (inline, universel) ET l'agent claude-code. Jamais dupliquer le contrat dans un adapter.
- **Verbosité = pur rendu LLM** (décision #20) : `verbosity` dans le brief ne change que l'expansion de Phase B, jamais la mécanique ni le jugement.

---

## 11. Risques et décisions ouvertes

| # | Risque / question | Position |
|---|---|---|
| 1 | **Brief incomplet** → perte de jugement silencieuse. | Responsabilité Phase A. Le gate ne couvre que `decisions_cumulative` ; les autres champs (arcs, next-steps) ne sont pas vérifiés mécaniquement. Atténuation : prompt Phase A exigeant + revue manuelle initiale. |
| 2 | **Phase B reformule mal** (prose dégradée mais substance présente). | Gate lexical ne l'attrape pas. Accepté : la qualité prose d'archive est secondaire à la complétude/resumabilité. Si insuffisant → option « gate Opus court » : 1 passe Opus de relecture sur la sortie ~6k (~+$0.30, reste 5-10× gagnant). |
| 3 | **Latence** : estimée ~80-110 s, dogfood mesuré à **51 s** (Phase B Haiku, 41 k tokens, 4 tool-uses) vs baseline 292 s. | Confirmé ~3×+ sur un run réel. Bench formel §9.6 pour figer (incl. coût Phase A Opus). |
| 4 | **Nombre de turns Phase A** (hypothèse 1-2). | Si la synthèse du brief demande N turns Opus, Phase A ≈ N × $0.28. À 5 turns → total ~$1.5 (encore ~5×). Le gain dégrade gracieusement. |
| 5 | **Dépendance discipline incrémentale.** | Le brief est moins cher à produire si `context.md` est déjà tenu (mode silent-incremental). Pré-requis souhaitable, pas bloquant. |
| 6 | **Activation** : flag vs seuil vs défaut. | **Tranché : auto direct, pas de flag.** Le gain est avéré (~10×/~3×) et le filet d'escalade (§8) garantit qu'aucun chemin ne dégrade la qualité — fonctionner sans délégation n'a pas d'intérêt. Le mode full délègue **par défaut** dès que la capacité subagent-cheap est présente ; sinon skill-mode fallback (Phase A écrit directement). Pas de `--delegate`, pas de seuil. |
