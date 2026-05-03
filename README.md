# SecondBrain

> Mémoire persistante pour agents CLI et apps desktop — Claude Code, Gemini CLI, Codex, Mistral Vibe, GitHub Copilot CLI, Claude Desktop, Codex Desktop. Serveur MCP `secondbrain-memory-kit` (v0.9.0) + skills fallback transparente.

[![License: MIT](https://img.shields.io/github/license/SI-GMT/SecondBrain?color=blue)](./LICENSE)
[![Latest release](https://img.shields.io/github/v/release/SI-GMT/SecondBrain)](https://github.com/SI-GMT/SecondBrain/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#prérequis)
[![Shells](https://img.shields.io/badge/shells-PowerShell%207%2B%20%7C%20bash-5391FE)](#prérequis)
[![CLIs](https://img.shields.io/badge/CLIs-Claude%20Code%20%7C%20Gemini%20%7C%20Codex%20%7C%20Vibe%20%7C%20Copilot%20%7C%20Desktop-8A2BE2)](#cli-supportées)
[![MCP](https://img.shields.io/badge/MCP-secondbrain--memory--kit-success)](#mode-mcp-v080)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR%20%7C%20ES%20%7C%20DE%20%7C%20RU-orange)](#langues-supportées)

SecondBrain s'appuie sur un concept développé à l'origine par **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)). Voir la section [Licence et crédits](#licence-et-crédits) pour les détails sur le travail original et l'adaptation menée chez SI Groupe Mondial Tissus.

> **v0.9.0** — **Port archeo natif + hygiène complète + doc-readers vendorisés + spec-drift**. Quatre axes structurants. (1) **Port archeo natif** : Phases 0 (topology scan partagé), 2 (`mem_archeo_stack` — résolution stack via manifests), 3 (`mem_archeo_git` — reconstruction Git par tags) et orchestrator (`mem_archeo`) sont désormais des outils MCP natifs Python. Phase 1 (`mem_archeo_context`, sémantique) et `mem_archeo_atlassian` restent skills-only par décision design — territoire LLM (classification 7-catégories) ou couverture déjà fournie par le MCP Atlassian client-side. Pattern `execute_X` module-level extrait du décorateur `@mcp.tool()` pour permettre la composition orchestrator sans appels MCP imbriqués. (2) **`mem_health_scan` complet via lib partagée** : la 9 catégorie d'audit hygiène (frontmatter, stray-zone, empty-md, missing-zone-index, missing-display, dangling-wikilinks, orphan-atoms, missing-archeo-hashes, mcp-tool-spec-drift) est exposée via `memory_kit_mcp.health.scan` que `tools/health_scan.py` consomme comme thin wrapper. La discipline `scripts/mem-health-scan.py ↔ memory_kit_mcp.health.scan` est documentée dans `CLAUDE.md` (3e paire de cohérence). (3) **Doc-readers vendorisés** : les 6 readers PDF/DOCX/PPTX/XLSX/CSV/HTML deviennent un package interne `memory_kit_mcp.readers/` (dispatcher `read_document(path) -> tuple[str, list[str]]` + 6 modules avec API uniforme `extract(path)`). Imports lazy via extra `[doc-readers]`. `tools/doc.py` étend son fast-path natif (.md/.txt) au dispatcher pour les autres formats. Discipline `scripts/doc-readers/*.py ↔ memory_kit_mcp.readers.*` documentée (4e paire de cohérence). (4) **Spec-drift scanner** : nouveau module `memory_kit_mcp.sync` + manifest versionné `mcp-server/src/memory_kit_mcp/sync.json` qui trace le SHA-256 du body de chaque `core/procedures/mem-X.md` au moment de la dernière re-synchronisation manuelle avec son module Python. La 9 catégorie health-scan `mcp-tool-spec-drift` compare et émet un finding `info` si dérive — filet doctrinal contre la divergence silencieuse. CLI `python -m memory_kit_mcp.sync update --kit-repo ...` pour réécrire le manifest après une synchronisation core ↔ Python. **189 tests pytest, 84 % coverage.**
>
> **v0.8.0** — **Phase 3 MCP server**. Le serveur Python `secondbrain-memory-kit` (installé via `pipx install ./mcp-server`) expose les **24 skills `mem-*` comme outils MCP** consommables nativement par toute CLI ou app desktop compatible MCP. Stack : `fastmcp 2.x` + Pydantic v2 + hatchling + uv, **114 tests pytest, 94 % coverage** via `fastmcp.Client` in-memory. **7 cibles MCP** auto-configurées par `deploy.ps1` : Claude Code (`~/.claude.json`), Claude Desktop (`~/AppData/Roaming/Claude/claude_desktop_config.json`), Codex CLI (`~/.codex/config.toml`), **Codex Desktop** (héritage de Codex CLI), Copilot CLI (`~/.copilot/mcp-config.json`), Mistral Vibe (`~/.vibe/config.toml`), Gemini CLI (`~/.gemini/settings.json`). Pattern **MCP-first / skills-fallback** : un bloc `_mcp-first.md` injecté en tête de chaque procédure indique au LLM d'invoquer l'outil MCP s'il est disponible, sinon d'exécuter la procédure complète comme avant. Aucune coupure de compatibilité — les skills déployés en v0.5+ continuent de fonctionner sur les CLI sans MCP. Côté outils : 19 outils fonctionnels in-memory tested (`mem_recall`, `mem_archive`, `mem_list`, `mem_search`, `mem_digest`, 6 vault management, 2 hygiene, 6 ingestion) + 5 stubs `mem_archeo*` qui surfacent un fallback explicite vers les skills (port complet en v0.8.x). Une primitive `vault/atomic_io.py` garantit UTF-8 sans BOM, LF, rename atomique et hash check pour la concurrence multi-session.
>
> **v0.7.5** — **5e adapter : GitHub Copilot CLI**. Le kit se déploie maintenant dans `~/.copilot/` en plus des 4 CLI précédentes. Surface installée : 24 skills au format Anthropic dans `~/.copilot/skills/{nom}/SKILL.md` (chacun expose nativement son slash command `/mem-recall`, `/mem-archive`, …) + bloc MEMORY-KIT injecté dans `~/.copilot/copilot-instructions.md` (équivalent CLAUDE.md user-level) + `memory-kit.json` au niveau utilisateur. Override du config dir via `$COPILOT_HOME` supporté. Détection automatique par `deploy.ps1` / `deploy.sh` — rien à faire de plus pour un poste qui a déjà tourné `copilot` au moins une fois. Copilot CLI ne lit plus `~/.claude/skills/` depuis sa version 1.0.35, l'écriture explicite dans `~/.copilot/skills/` est donc nécessaire (et faite par l'adapter).
>
> **v0.7.4** — `mem-historize` + renforcements doctrinaux. (1) **Nouveau skill `mem-historize`** : déplace un projet terminé vers `10-episodes/archived/{slug}/` pour le sortir du scope par défaut des skills d'accès (`mem-recall`, `mem-list`, `mem-search`, `mem-digest`) et réduire la consommation tokens du briefing au démarrage. Réversible via `--revive`. Délégation à `scripts/mem-historize.py` (versionné, idempotent, pattern when-to-script). Patch atomique de `context.md` (phase, archived_at, display suffix `[archived]`) + `shutil.move` du dossier. (2) **Bloc doctrinal `core/procedures/_archived.md`** qui définit la règle de résolution (projets d'abord, archivés ensuite) et la matrice de comportement par skill (refuse / skip / collapse par défaut, override `--include-archived` / `--from-archived` / `--allow-archived` selon le contexte). 6 skills d'accès patchés (`mem-recall`, `mem-list`, `mem-search`, `mem-digest`, `mem-archive`, `mem-archeo*`). `rebuild-vault-index.py` rend une section `## Archived projects` séparée. i18n EN/FR/ES/DE/RU étendue. (3) **Renforcement `mem-promote-domain`** : mode CREATE vs EXTEND automatique (idempotent sur ré-invocation), nouvelles sources `--from-sub-zone` / `--from-tag` pour promouvoir des atomes existants hors `00-inbox/`, override anti-drift `--allow-2-items` documenté. Distinction move-vs-retag clarifiée (notes inbox déplacées, atomes transverses retaggés en place). (4) **Renforcement `_linking.md`** : invariant binding sur la résolution des wikilinks dans la prose persistée (DOIT résoudre au moment de l'écriture, sinon backticks ou TODO marqué) + politique de fix rétroactif sur archives immuables. Scanner patche le bug stem-resolution (`[[X.md]]` résout maintenant comme `[[X]]`).
>
> **v0.7.3.1** — Doctrinal hotfix. (1) Le scanner `mem-health-scan` est promu en `scripts/mem-health-scan.py` versionné — la version v0.7.3 ne décrivait que la procédure et laissait le LLM créer un script ad-hoc dans `$TEMP/` à chaque invocation, ce qui n'est ni reproductible ni auditable. La procédure `core/procedures/mem-health-scan.md` est refactorée en délégation explicite au script. Une 8e catégorie **`malformed-frontmatter`** (sévérité `error`) est ajoutée au scanner pour éviter les cascades de faux positifs (un frontmatter YAML mal-quoté faisait conclure "missing display" sur des fichiers qui en avaient pourtant un — bug observé sur 10 archives `gmt-ia-devops` produites par `mem-archeo-atlassian` antérieurement). Exit code 1 si erreurs, utile pour CI. (2) Nouveau bloc doctrinal `core/procedures/_when-to-script.md` qui formalise la règle : toute procédure avec parcours systématique du vault, parsing structuré multi-fichier ou agrégation cross-file DOIT déléguer à un script versionné dans `scripts/`, jamais re-implémenter ad-hoc. (3) Procédure `mem-archeo-atlassian` patchée pour toujours quoter `confluence_page_title:`, `jira_summary:` et `confluence_url:` à l'écriture (cause racine corrigée à la source). (4) Script one-shot `scripts/migrate-fix-archeo-atlassian-frontmatter.py` pour réparer les archives existantes (10 archives patchées sur le vault prod GMT — quote des `[TAG]` non-quotés + restauration des newlines après `---`).
>
> **v0.7.3** — Hygiene release. Trois corrections doctrinales du vault + deux nouveaux skills d'hygiène. (1) **Bridge Front Matter Title** : `adapters/obsidian-style/` livre désormais aussi `plugins/obsidian-front-matter-title-plugin/data.json`, configuré pour lire le champ `display` du frontmatter universel (clé `templates.common.main: "display"`, fallback `title`). Active les substitutions sur graph view, file explorer, tabs et backlinks panel. Sans cette config, le plugin par défaut cherche `title` qui n'existe pas dans le schéma SecondBrain et tombe sur le filename — d'où les nœuds graph "history"/"context" indistinguables vus en v0.7.2. Le bridge `Deploy-ObsidianStyle` scanne désormais récursivement `adapters/obsidian-style/` et reproduit l'arborescence dans `.obsidian/`. (2) **Index par zone** : chaque zone (`00-inbox`, `10-episodes`, ..., `99-meta`) reçoit son propre `{zone}/index.md` avec frontmatter `type: zone-index`. Les liens `[20-knowledge](20-knowledge/)` du squelette `index.md` racine pointaient vers des cibles inexistantes — Obsidian les résolvait en nœuds graph fantômes et créait des MD vides à la racine au clic. Le rendu de `rebuild-vault-index.py` pointe maintenant vers `[20-knowledge](20-knowledge/index.md)` (cibles réelles) et le script crée idempotemment les fichiers manquants au passage. Un script `scaffold-vault.py` neuf produit aussi ces hubs. (3) **`mem-health-scan` / `mem-health-repair`** : audit + réparation des défauts d'hygiène du vault. Le scan détecte 7 catégories (stray-zone-md, empty-md-at-root, missing-zone-index, missing-display, dangling-wikilinks, orphan-atoms, missing-archeo-hashes), produit un rapport horodaté `99-meta/health/scan-{ts}.md`. Le repair applique les fixes idempotents (dry-run par défaut, `--apply` opt-in) en délégant aux scripts utilitaires existants (`inject-display-frontmatter.py`, `inject-archeo-hashes.py`, `rebuild-vault-index.py`). `index.md` racine liste désormais une section `## Health` avec les rapports. Cadrage `mem-historize` (déplacement projets finis vers `10-episodes/archived/` pour réduire le coût en tokens du briefing) acté pour v0.7.4 — voir `docs/architecture/v0.7.4-mem-historize-cadrage.md`.
>
> **v0.7.2** — DX du vault enrichi : `mem-search` gagne les filtres `--source archeo-*` (wildcard), `--branch`, `--extracted-category`, `--detected-layer`, `--author`. `mem-list` annote chaque projet avec une coverage archeo compacte (`T B{N} [{C}c {S}s {G}g]`) + `--detail` enrichi (repo_path, workspace_member, breakdown par source). `mem-digest` distingue **Foundations** (stature stable : stack, archeo-context principles, archeo-stack architecture) de **Sessions** (archives lived + archeo-git) — la frame ne se mélange plus à la trajectoire. Champ **`display`** ajouté au frontmatter universel (recommandé) pour disambiguer les nœuds homonymes dans la vue graph d'Obsidian via le plugin Front Matter Title — sans le plugin, le champ est silently ignoré donc safe à ajouter partout. Script `inject-display-frontmatter.py` pour patcher rétroactivement un vault existant. Bridge **`Deploy-ObsidianStyle`** intégré à `deploy.ps1`/`deploy.sh` qui copie une palette de couleurs canonique pour le graph view (un coloris distinct par zone) avec backup horodaté avant écrasement, refus si Obsidian ouvert (sauf `--force-obsidian-style`), respect du marker `_secondbrain_canonical` pour ne pas écraser les personnalisations utilisateur.
>
> **v0.7.1** — Mode **`--branch-first`** sur `mem-archeo` et ses sous-skills : focus serré sur une branche feature (commits depuis la divergence avec `--branch-base`, fichiers touchés, manifests modifiés) avec contexte ambient en mode léger. Granularité **`--by-author`** par défaut en branch-first — un atome par auteur par fenêtre temporelle, avec section "Author signature" pour capturer les patterns par contributeur. Co-Authored-By collectés comme métadonnée (utile pour distinguer les contributions humaines vs LLM). **Détection des workspaces monorepo** (npm/pnpm, Cargo, uv, Maven multi-module, Gradle, generic apps/+packages/) avec liaison cross-projet : si la branche traverse plusieurs workspaces, la topologie de branche devient un carrefour de wikilinks vers les projets vault correspondants. Topologie de branche dédiée dans `99-meta/repo-topology/{slug}-branches/{branch-san}.md` à côté de la topologie main. Champ `workspace_member` dans `context.md` pour déclaration explicite (suggéré par `mem-archive` si détectable). `_router.md` : clé d'idempotence étendue avec `branch` pour éviter les collisions main vs feature.
>
> **v0.7.0** — Refonte `mem-archeo` triphasée pour rendre la reconstruction de projet **déterministe inter-LLM**. La cause racine identifiée par l'analyse 3-LLM (`docs/analyses/2026-04-28-mem-archeo-comparatif-3-llm.md`) : un mem-archeo Git-only force chaque LLM à extrapoler différemment le contexte organisationnel et technique manquant. Solution : 3 phases distinctes orchestrées qui partagent un scan topologique unique. Phase 1 `archeo-context` (organisationnel/décisionnel/fonctionnel — AI files, README, docs/, cadrage/, adr/), Phase 2 `archeo-stack` (technique — manifests, infra, CI), Phase 3 `archeo-git` (temporel — la procédure existante, enrichie par 0/1/2). Topologie persistée dans `99-meta/repo-topology/{slug}.md`. Skills `mem-archive` et `mem-recall` alignés (snapshot topologique, lecture au briefing). Router (`_router.md`) durci : R10 idempotence par-source, R11 collisions sémantiques, R4.5 invariants frontmatter (no duplicate keys, enum values en anglais canonique, hashes mandatory). Deux nouveaux scripts : `inject-archeo-hashes.py` (correction rétroactive des hashes/enum), `validate-archeo-frontmatter.py` (lint CI-able).
>
> **v0.6.0** — Doc-readers Python multi-format pour `/mem-doc` : ingestion de `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.csv`, `.html` en plus du texte natif et des images. Convention PEP 723 inline metadata via `uv run` — pas de venv ni `requirements.txt` à gérer. Stratégie option C pour PDF : extraction Python par défaut, fallback automatique vers la lecture vision native du LLM si le PDF est scanné. Champ `kit_repo` ajouté à `memory-kit.json` pour résoudre l'emplacement des readers.
>
> **v0.5.4** — Refonte brain-centric (9 zones mémorielles), schéma 100 % anglais (folders, frontmatter, tags), instructions LLM en anglais (efficacité maximale), conversation dans la langue native de l'utilisateur (EN/FR/ES/DE/RU bundle, sélection à l'install). Invariant **zero orphan atom** : tout fichier persisté carries au moins un lien (croisés `context.md` ↔ `history.md`, frontmatter `project:` + `context_origin` pour les atomes transverses). Tooling : migration FR→EN, régénération de l'index, enforcement linking rétroactif.

---

## Sommaire

- [Présentation](#présentation)
- [Fonctionnement](#fonctionnement)
- [Mode MCP (v0.8.0)](#mode-mcp-v080)
- [Installation](#installation)
- [Architecture](#architecture)
- [Commandes](#commandes)
- [Langues supportées](#langues-supportées)
- [Performances](#performances)
- [Multi-projets](#multi-projets)
- [Outils de maintenance](#outils-de-maintenance)
- [Feuille de route](#feuille-de-route)
- [Désinstallation](#désinstallation)
- [Licence et crédits](#licence-et-crédits)

---

## Présentation

Les CLI LLM agentiques n'ont pas de mémoire entre les sessions. Après un `/clear` ou une fermeture d'IDE, l'intégralité du contexte — état du projet, décisions prises, prochaines étapes — doit être ré-exposée manuellement à l'agent.

SecondBrain installe une mémoire locale structurée que l'agent lit et écrit automatiquement, au niveau utilisateur (dans `~/.claude/`, `~/.gemini/`, `~/.codex/`, `~/.vibe/` ou `~/.copilot/` selon la CLI). Le contexte devient disponible depuis n'importe quel projet sur le poste.

Depuis la **v0.8.0**, un serveur MCP `secondbrain-memory-kit` expose en plus les 24 skills comme outils MCP natifs — utilisés en priorité quand disponibles, avec fallback transparent vers les skills. Voir [Mode MCP](#mode-mcp-v080). La **v0.9.0** étend le périmètre MCP : port archeo natif, audit hygiène 9-catégories complet, doc-readers vendorisés et scanner de spec-drift.

**Gain mesurable** : la reprise de session consomme environ 2× moins de tokens qu'un re-briefing manuel équivalent.

### CLI et apps desktop supportées

| Cible | Maturité | MCP (v0.8.0) | Skills fallback |
|---|---|---|---|
| **Claude Code** | Référence, éprouvée en production | ✅ `~/.claude.json` | Skills + slash commands + bloc `CLAUDE.md` + permissions |
| **Claude Desktop** | Fonctionnel (v0.8.0) | ✅ `~/AppData/Roaming/Claude/claude_desktop_config.json` | (pas de skills, MCP only) |
| **Codex CLI** | Fonctionnel, validé en conditions réelles | ✅ `~/.codex/config.toml` (`[mcp_servers.secondbrain-memory-kit]`) | Prompts + skills |
| **Codex Desktop** | Fonctionnel (v0.8.0) | ✅ via héritage de Codex CLI | (partage de la config Codex CLI) |
| **GitHub Copilot CLI** | Fonctionnel (v0.7.5) | ✅ `~/.copilot/mcp-config.json` | Skills dans `~/.copilot/skills/` + bloc dans `~/.copilot/copilot-instructions.md` |
| **Mistral Vibe** | Fonctionnel, validé en conditions réelles | ✅ `~/.vibe/config.toml` (`[[mcp_servers]]`) | Skills dans `~/.vibe/skills/` + bloc dans `~/.vibe/AGENTS.md` |
| **Gemini CLI** | Fonctionnel, validé en conditions réelles | ✅ `~/.gemini/settings.json` (`mcpServers`) | Extension `memory-kit` + `GEMINI.md` + commandes TOML |

Le script d'installation détecte automatiquement les CLI/apps présentes sur le poste et ne déploie que les adapters correspondants. Le serveur MCP est installé une fois via `pipx`, puis sa déclaration est injectée dans la config MCP de chaque cible compatible.

---

## Fonctionnement

Le cycle de mémoire se décompose en trois phases :

1. **Reprise** — L'utilisateur écrit « reprends », « on continue », ou tape `/mem-recall`. L'agent charge le contexte du projet en quelques secondes, sans re-briefing.
2. **Session** — L'agent met à jour silencieusement le `context.md` du projet dès qu'une décision structurante émerge. Aucune intervention explicite requise.
3. **Archivage** — L'utilisateur écrit « on s'arrête », « je pars », ou tape `/mem-archive`. L'agent produit un résumé horodaté de la session (décisions, état, prochaines étapes) avant que `/clear` ne soit lancé.

### Fiabilité du déclenchement par langage naturel

Le déclenchement automatique repose sur des instructions injectées dans la config utilisateur de la CLI (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `copilot-instructions.md`). Sa fiabilité dépend du modèle sous-jacent : très élevée sur Claude Code, bonne sur Gemini CLI, variable ailleurs. Les slash commands explicites (`/mem-recall`, `/mem-archive`, etc.) produisent un comportement identique sur toutes les plateformes qui les exposent.

### Anglais structurel, conversation native

Toutes les **instructions destinées au LLM** (procédures, frontmatter, tags, valeurs persistées) sont en anglais — les LLM modernes raisonnent et exécutent plus précisément sur instructions EN. Mais **l'agent répond toujours dans la langue conversationnelle de l'utilisateur**, configurée à l'installation et stockée dans `memory-kit.json`. Le contenu structuré (titres de sections, libellés persistés) est résolu via `core/i18n/strings.yaml` qui bundle EN/FR/ES/DE/RU.

---

## Mode MCP (v0.8.0)

Le serveur MCP `secondbrain-memory-kit` (Python, dans `mcp-server/`) expose les 24 skills `mem-*` comme outils MCP natifs consommables par toute CLI ou app desktop compatible MCP. Quand le serveur est démarré, l'agent invoque les outils en priorité (logique métier exécutée en Python, déterministe, économe en tokens). Sinon, il retombe automatiquement sur les skills classiques.

### Stack et installation

- **Framework** : `fastmcp` 2.x (standalone, pas le SDK officiel intégré) — choisi pour le `Client` in-memory qui rend les tests pytest triviaux sans subprocess stdio.
- **Validation** : Pydantic v2 (args + retours typés), sérialisés automatiquement en `structuredContent` MCP.
- **Build** : hatchling + uv (Python ≥3.12), packaging via `pipx install ./mcp-server`.
- **Tests** : pytest + pytest-asyncio + pytest-cov, **114 tests, 94 % coverage**, fixture `vault_tmp` qui copie un mini-vault de référence dans `tmp_path` à chaque test.
- **Transport** : stdio uniquement (lancé par le client CLI à chaque session).

`deploy.ps1` / `deploy.sh` détecte `pipx`, installe ou met à jour `memory-kit-mcp`, écrit `~/.memory-kit/config.json` (vault, scope, langue, kit_repo), et inject la déclaration MCP dans les configs des cibles compatibles. En cas de WinError 32 (binaire verrouillé par une CLI active), l'upgrade est différé proprement et la version précédente reste fonctionnelle.

### Inventaire des 24 outils

| Catégorie | Outils MCP (snake_case) | État v0.8.0 |
|---|---|---|
| Cycle session | `mem_recall`, `mem_archive` | ✅ fonctionnels |
| Inventaire | `mem_list`, `mem_search`, `mem_digest` | ✅ fonctionnels |
| Vault management | `mem_rename`, `mem_merge`, `mem_reclass`, `mem_rollback_archive`, `mem_promote_domain`, `mem_historize` | ✅ fonctionnels |
| Hygiene | `mem_health_scan`, `mem_health_repair` | ✅ fonctionnels (POC subset 4 catégories) |
| Ingestion | `mem`, `mem_doc`, `mem_note`, `mem_principle`, `mem_goal`, `mem_person` | ✅ fonctionnels (`mem_doc` POC md/txt natif, autres formats via skills) |
| Archeo | `mem_archeo`, `mem_archeo_context`, `mem_archeo_stack`, `mem_archeo_git`, `mem_archeo_atlassian` | ⏳ stubs MCP avec fallback explicite vers skills (port complet en v0.8.x) |

Convention de nommage : `mem-X` (kebab côté skills/CLI/langage naturel) ↔ `mem_X` (snake côté outils MCP / Python). Les invocations utilisateur (slash commands, intents) ne changent pas.

### Pattern MCP-first / skills-fallback

Chaque procédure `core/procedures/mem-X.md` résolue par `deploy.ps1` est préfixée par un bloc `_mcp-first.md` qui indique :

> Si l'outil `mcp__secondbrain-memory-kit__mem_X` est disponible, l'invoquer. Sinon, exécuter la procédure ci-dessous.

Le LLM décide à l'invocation, sans intervention de l'utilisateur. Les CLI sans MCP (cas où l'utilisateur n'a pas installé `pipx`, ou serveur non démarré) gardent la même expérience qu'avant — les skills exécutent la procédure complète comme en v0.7.x.

### Source de vérité

`core/procedures/mem-X.md` reste la **source de vérité fonctionnelle**. Le module Python `mcp-server/src/memory_kit_mcp/tools/X.py` en est la traduction exécutable. Discipline de cohérence : tout changement dans une procédure doit s'accompagner d'un changement dans le module Python correspondant (et vice-versa) dans la même PR.

Voir `docs/architecture/v0.8.0-mcp-server-cadrage.md` pour le cadrage complet (5 axes structurants, 13 sections).

---

## Installation

### Prérequis

- **PowerShell 7+** (`pwsh`) sur Windows, **ou** **bash** sur macOS/Linux/git-bash.
- **Au moins une CLI ou app desktop supportée** installée, avec une session préalablement lancée pour que le dossier de config utilisateur existe (`~/.claude/`, `~/.gemini/`, `~/.codex/`, `~/.vibe/`, `~/.copilot/`, `~/AppData/Roaming/Claude/` selon la cible).
- **`pipx`** (recommandé) ou `pip` — pour installer le serveur MCP `secondbrain-memory-kit` via `deploy.ps1`. Sans `pipx`, le déploiement bascule sur `pip install --user` ; sans Python, le serveur MCP est skip et les CLI restent en mode skills classique. Voir [Mode MCP](#mode-mcp-v080).
- **Obsidian** (optionnel) — pour visualiser le vault sous forme de graphe.
- **`uv`** (optionnel) — requis uniquement pour `/mem-doc` sur les formats non-natifs (`.docx`, `.pdf`, `.pptx`, `.xlsx`, `.csv`, `.html`). Voir [Formats supportés par `/mem-doc`](#formats-supportés-par-mem-doc). Installation : <https://docs.astral.sh/uv/>.

### Déploiement

1. Cloner le dépôt dans un dossier stable du poste :
   ```bash
   git clone https://github.com/SI-GMT/SecondBrain.git
   ```

2. Lancer le déploiement depuis la racine :
   ```powershell
   # Windows
   .\deploy.ps1
   ```
   ```bash
   # macOS / Linux
   ./deploy.sh
   ```

Le script détecte les CLI présentes, déploie l'adapter correspondant à chacune, et ignore silencieusement les CLI absentes. Si aucune CLI n'est trouvée, un message listant les liens d'installation est affiché puis l'exécution s'arrête proprement.

À la première installation, le script propose la **langue conversationnelle** du LLM (détectée depuis la locale système, modifiable à la volée). Voir [Langues supportées](#langues-supportées).

### Surfaces installées par plateforme

| Cible | Skills fallback (déployés) | MCP server (v0.8.0) |
|---|---|---|
| Claude Code | `~/.claude/commands/mem-*.md`, `~/.claude/skills/mem-*.md`, `memory-kit.json`, bloc dans `CLAUDE.md`, vault ajouté à `permissions.additionalDirectories` dans `settings.json` | `~/.claude.json` → `mcpServers.secondbrain-memory-kit` |
| Claude Desktop | (pas de skills) | `~/AppData/Roaming/Claude/claude_desktop_config.json` → `mcpServers.secondbrain-memory-kit` |
| Codex CLI | `~/.codex/prompts/mem-*.md`, `~/.codex/skills/mem-*/SKILL.md`, `memory-kit.json` | `~/.codex/config.toml` → `[mcp_servers.secondbrain-memory-kit]` (markers `# MEMORY-KIT:START/END`) |
| Codex Desktop | (partage de la config Codex CLI) | héritage `~/.codex/config.toml` |
| GitHub Copilot CLI | `~/.copilot/copilot-instructions.md` (bloc injecté), `~/.copilot/skills/mem-*/SKILL.md`, `memory-kit.json`. Override via `$COPILOT_HOME` | `~/.copilot/mcp-config.json` → `mcpServers.secondbrain-memory-kit` |
| Mistral Vibe | `~/.vibe/AGENTS.md` (bloc injecté), `~/.vibe/skills/mem-*/SKILL.md` | `~/.vibe/config.toml` → `[[mcp_servers]]\nname = "secondbrain-memory-kit"` (markers) |
| Gemini CLI | Extension dans `~/.gemini/extensions/memory-kit/`, `memory-kit.json`, activation dans `extension-enablement.json` | `~/.gemini/settings.json` → `mcpServers.secondbrain-memory-kit` |
| **Tous (commun MCP)** | — | Binaire `memory-kit-mcp` installé via `pipx install ./mcp-server` + `~/.memory-kit/config.json` (vault, scope, langue, kit_repo) |

### Choix du vault et de la langue

| Scénario | Commande |
|---|---|
| Première installation (défaut, vault `{kit}/memory`, langue détectée) | `.\deploy.ps1` ou `./deploy.sh` |
| Première installation, chemin personnalisé | `.\deploy.ps1 -VaultPath "D:\mes-notes\cerveau"` |
| Forcer la langue conversationnelle | `.\deploy.ps1 -Language fr` ou `./deploy.sh --language fr` |
| Mise à jour | `.\deploy.ps1` — chemin et langue relus depuis `memory-kit.json` existants |
| Migration vers un nouvel emplacement | `.\deploy.ps1 -VaultPath "D:\nouveau\chemin"` — met à jour les configs mais ne déplace pas les fichiers existants (à faire manuellement) |

### Vérification

Depuis n'importe quel projet, ouvrir une CLI supportée et taper :

```
/mem-recall
```

L'agent doit répondre dans votre langue, par exemple :

```
Aucun projet/domaine trouvé. Mémoire initialisée — memory/index.md est prêt.
Décris ce sur quoi tu travailles et on commence.
```

### Ouvrir le vault dans Obsidian (optionnel)

1. Installer Obsidian : <https://obsidian.md>
2. Ouvrir Obsidian → *Open folder as vault* → sélectionner `memory/`.

Le dossier `memory/` est déjà un vault Obsidian valide.

### Configurations Obsidian canoniques (v0.7.2)

`deploy.ps1` / `deploy.sh` déploie automatiquement une palette de couleurs canonique pour le graph view (un coloris distinct par zone : `episodes`, `knowledge`, `principles`, `goals`, etc.). Le bridge **refuse silencieusement si Obsidian est ouvert** sur le vault (pour éviter une corruption des configs en mémoire), respecte les personnalisations utilisateur (ne touche pas aux fichiers sans le marker `_secondbrain_canonical`), et fait un backup horodaté avant tout écrasement.

Pour bypass (force) : `--force-obsidian-style`. Pour skip : `--skip-obsidian-style`.

Plugin community **fortement recommandé** : **Front Matter Title** (par snezhig). Il lit le champ `display` du frontmatter universel et l'utilise comme label dans le graph view, le file explorer et les wikilinks — sans lui, les nœuds homonymes (`context.md` répétés par projet) sont indistinguables. Le champ `display` est défini par les conventions de `core/procedures/_frontmatter-universal.md` et patché rétroactivement par `scripts/inject-display-frontmatter.py`.

Voir `adapters/obsidian-style/README.md` pour les détails.

---

## Architecture

```
SecondBrain/
├── core/
│   ├── procedures/             Spec procédurale agnostique (source de vérité)
│   │   ├── _router.md          Router sémantique — pattern central d'ingestion
│   │   ├── _frontmatter-universal.md, _encoding.md, _concurrence.md
│   │   ├── mem-recall.md, mem-archive.md, mem-list.md, mem-search.md
│   │   ├── mem-doc.md, mem-archeo.md, mem-archeo-atlassian.md
│   │   ├── mem-note.md, mem-principle.md, mem-goal.md, mem-person.md
│   │   ├── mem-rename.md, mem-merge.md, mem-reclass.md, mem-promote-domain.md
│   │   ├── mem-digest.md, mem-rollback-archive.md
│   │   └── mem.md              Router universel d'ingestion
│   └── i18n/strings.yaml       Chaînes structurelles localisées (EN/FR/ES/DE/RU)
├── adapters/
│   ├── claude-code/            Skills + slash commands + bloc CLAUDE.md
│   ├── gemini-cli/             Extension memory-kit + GEMINI.md + TOML
│   ├── codex/                  Prompts + skills
│   ├── mistral-vibe/           Bloc AGENTS.md + skills (format Anthropic)
│   └── copilot-cli/            Bloc copilot-instructions.md + skills (format Anthropic)
├── mcp-server/                 Serveur MCP Python (v0.8.0)
│   ├── pyproject.toml          hatchling + fastmcp ≥2.13 + Pydantic v2
│   ├── src/memory_kit_mcp/
│   │   ├── server.py           FastMCP instance + main() entry stdio
│   │   ├── config.py           ~/.memory-kit/config.json loader
│   │   ├── tools/              24 outils mem_* (1 fichier par tool)
│   │   └── vault/              Primitives partagées (paths, frontmatter,
│   │                           atomic_io, scanner)
│   └── tests/                  pytest, 114 tests, 94% coverage
├── memory/                     Vault Obsidian local (non versionné — voir .gitignore)
│   ├── index.md                Catalogue maître à la racine
│   ├── 00-inbox/               Captation brute non qualifiée
│   ├── 10-episodes/
│   │   ├── projects/{slug}/
│   │   │   ├── context.md      Snapshot mutable (fast lane)
│   │   │   ├── history.md      Fil chronologique
│   │   │   └── archives/       Une archive par session complète (immuable)
│   │   └── domains/{slug}/     Domaines transverses (sans date de fin)
│   ├── 20-knowledge/           Mémoire sémantique (faits, concepts, fiches)
│   ├── 30-procedures/          Savoir-faire / how-to
│   ├── 40-principles/          Heuristiques et lignes rouges
│   ├── 50-goals/               Intentions prospectives
│   ├── 60-people/              Carnet relationnel
│   ├── 70-cognition/           Productions non verbales (cerveau droit)
│   └── 99-meta/                Méta-mémoire du vault (doctrine, taxonomie)
├── deploy.ps1                  Déploiement Windows (PowerShell)
└── deploy.sh                   Déploiement macOS/Linux (bash)
```

**Single source of truth** — toute logique procédurale vit dans `core/procedures/`. Les adapters n'apportent que du frontmatter et du formatage spécifique à leur plateforme. Les scripts de déploiement substituent à la volée le marqueur `{{PROCEDURE}}` par le contenu du fichier core correspondant. Pas de duplication, pas de divergence entre plateformes.

**Architecture brain-centric** — depuis v0.5, le vault est organisé par **fonctions mémorielles** (épisodique, sémantique, procédurale, prospective…) et non plus par projet. Un projet devient un tag transverse qui se projette dans plusieurs zones via le router sémantique.

---

## Commandes

Toutes les commandes sont préfixées `mem-*` pour éviter les collisions avec les commandes natives des CLI.

### Cycle de session

| Déclencheur | Contexte | Effet |
|---|---|---|
| Langage naturel (« reprends », « on continue », « tu te rappelles ») | Début de session | Chargement automatique du contexte |
| `/mem-recall` | Début de session (explicite) | Chargement + briefing affiché |
| `/mem-recall {projet}` | Plusieurs projets existent | Chargement direct du projet nommé |
| *Silencieux (incrémental)* | Fait important émergeant en cours de session | Mise à jour de `context.md` sans création d'archive |
| Langage naturel (« on s'arrête », « je pars ») | Fin de session | Mode archive complet |
| `/mem-archive` | Avant `/clear` (explicite) | Résumé + écriture des fichiers |

### Ingestion (router universel + shortcuts)

| Commande | Intention | Effet |
|---|---|---|
| `/mem` | Capture libre, le router classe | Segmente en atomes et route vers la bonne zone (cascade d'heuristiques) |
| `/mem-doc {chemin}` | Ingérer un document local | 1 fichier (PDF, MD, texte, image, docx) → archive single-shot |
| `/mem-archeo [repo]` | Archeo triphasée (orchestrateur) | Phase 0 topologie + Phase 1 contexte (`archeo-context`) + Phase 2 stack (`archeo-stack`) + Phase 3 Git (`archeo-git`). Topologie persistée. |
| `/mem-archeo-context [repo]` | Phase 1 isolée — contexte projet | Lit AI files + README + docs/ + cadrage/ + adr/. Atomes principles/goals/knowledge ADR. Idempotent par `(project, source_doc, extracted_category)`. |
| `/mem-archeo-stack [repo]` | Phase 2 isolée — stack technique | Résout par layer (frontend/backend/db/ci/infra/tests/tooling). Idempotent par `(project, source_manifest, detected_layer)`. |
| `/mem-archeo-git [repo]` | Phase 3 isolée — historique Git | Archives datées par tag/release/merge/fenêtre. Surfacage des frictions (≥3 commits successifs même thème). |
| `/mem-archeo --branch-first {branch}` | Mode branch-first (v0.7.1) | Focus serré sur une branche feature, ambient context léger, granularité `--by-author` par défaut, détection workspaces monorepo et liaison cross-projet. Topologie de branche dans `99-meta/repo-topology/{slug}-branches/{branch-san}.md`. |
| `/mem-archeo-atlassian {url}` | Rétro Confluence + Jira | 1 archive par page Confluence, enrichies par les tickets Jira liés |
| `/mem-note` | Note de connaissance | Insère dans `20-knowledge/` |
| `/mem-principle` | Principe / heuristique / ligne rouge | Insère dans `40-principles/` |
| `/mem-goal` | Objectif (intention future) | Insère dans `50-goals/` (horizon court/moyen/long détecté) |
| `/mem-person` | Fiche personne | Insère dans `60-people/` (sensitive=true par défaut) |

### Formats supportés par `/mem-doc`

| Extension | Stratégie | Dépendance Python |
|---|---|---|
| `.md`, `.txt`, `.json` | Lecture native | — |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | Description par vision LLM native | — |
| `.pdf` | `read_pdf.py` ; fallback automatique vers la vision LLM si le PDF est scanné | `pypdf` |
| `.docx` | `read_docx.py` | `python-docx` |
| `.pptx` | `read_pptx.py` | `python-pptx` |
| `.xlsx` | `read_xlsx.py` (clip à 200 lignes × 30 colonnes par feuille) | `openpyxl` |
| `.csv` | `read_csv.py` (auto-détection du délimiteur) | stdlib |
| `.html`, `.htm` | `read_html.py` (extraction texte + tables, anti-noise script/style/nav) | `beautifulsoup4` + `lxml` |

Les readers vivent dans `scripts/doc-readers/`. Chacun déclare ses dépendances via [PEP 723](https://peps.python.org/pep-0723/) inline metadata et est invoqué par `uv run` — `uv` résout et installe les dépendances à la volée, sans venv ni `requirements.txt`. Les fichiers texte natifs et images n'ont pas besoin de `uv`.

### Gestion du vault

| Commande | Intention | Effet |
|---|---|---|
| `/mem-list` | Lister projets + domaines | Tableau : slug, kind, scope, dernière session, nb de sessions |
| `/mem-search {requête}` | Rechercher dans le vault | Recherche plein-texte avec contexte |
| `/mem-rename {old} {new}` | Renommer un projet ou domaine | Renomme partout (dossier, frontmatters, tags, index) |
| `/mem-merge {source} {target}` | Fusionner deux projets ou domaines | Retaggue, concatène, supprime la source. `context.md` à fusionner manuellement |
| `/mem-reclass {chemin}` | Changer scope/zone d'un contenu | Met à jour frontmatter + tags + déplace le fichier |
| `/mem-promote-domain {slug}` | Promouvoir des items inbox en domaine permanent | Vérifie l'anti-dérive (≥3 items au même fil) |
| `/mem-digest {projet} [N]` | Synthétiser les N dernières sessions | Arcs majeurs, décisions, dérive. Lecture seule (N=5 par défaut) |
| `/mem-rollback-archive [projet]` | Annuler la dernière archive | Supprime l'archive et retire ses références. N'auto-restaure pas `context.md` |
| `/mem-health-scan` | Auditer l'hygiène du vault (v0.7.3) | Détecte stray-zone-md, missing-zone-index, missing-display, dangling-wikilinks, orphan-atoms, missing-archeo-hashes. Rapport read-only dans `99-meta/health/scan-{ts}.md` |
| `/mem-health-repair` | Appliquer les fixes d'hygiène (v0.7.3) | Dry-run par défaut, `--apply` opt-in. Délègue aux scripts utilitaires existants. Orphan-atoms semi-automatique avec prompt par fichier |

---

## Langues supportées

Le LLM converse avec l'utilisateur dans la langue choisie à l'installation. Les chaînes structurelles écrites dans le vault (titres de sections d'index, libellés `## Projects` / `## Domains` / `## Archives`, placeholders empty-state) sont résolues via `core/i18n/strings.yaml`.

| Code | Langue |
|---|---|
| `en` | English (défaut, fallback) |
| `fr` | Français |
| `es` | Español |
| `de` | Deutsch |
| `ru` | Русский |

**Sélection** : à la première installation, le script propose la langue détectée depuis la locale système (`$PSCulture` / `$LANG`). Modifiable plus tard via `.\deploy.ps1 -Language fr` (Windows) ou `./deploy.sh --language fr` (macOS/Linux), ou en éditant directement le champ `language` dans `~/.{cli}/memory-kit.json`.

**Ajouter une langue** : dupliquer le bloc `en:` de `core/i18n/strings.yaml`, traduire les valeurs en gardant les clés identiques. Le fallback EN est garanti pour toute clé manquante.

---

## Performances

Chaque archive complet produit deux fichiers :

- Une **archive** complète (~70 lignes) — immuable, trace historique.
- Un **`context.md`** synthétisé (~25 lignes) — écrasé à chaque session.

Au `/mem-recall` suivant, l'agent lit `context.md` en priorité. Le briefing fait donc 25 lignes au lieu de 70, soit approximativement 2× moins de tokens qu'un re-briefing manuel qui reproduirait tout le contexte historique.

---

## Multi-projets

Un seul vault peut contenir N projets et N domaines. Chaque projet a son propre dossier dans `memory/10-episodes/projects/{slug}/` :

```
/mem-recall site-client-a
/mem-recall app-mobile
```

Le kit étant installé au niveau utilisateur, il n'est pas nécessaire de le recopier dans chaque projet.

---

## Outils de maintenance

Scripts Python livrés dans `scripts/` pour les opérations de maintenance ponctuelles sur un vault existant. Tous tournent en **dry-run par défaut** ; ajouter `--apply` pour écrire.

| Script | Quand l'utiliser |
|---|---|
| `migrate-vault-v0.5.py` | Migrer un vault **v0.4** (project-centric, `archives/` + `projets/` à plat) vers la structure brain-centric **v0.5** (9 zones). Backup automatique avant `--apply`. |
| `migrate-vault-v05-to-v052.py` | Migrer un vault **v0.5 encore en français** (zones `40-principes`, valeurs `kind: projet`, etc.) vers le schéma **v0.5.2 anglais** (`40-principles`, `kind: project`, …). Préserve la prose française des archives narratives. |
| `rebuild-vault-index.py` | Régénérer `{vault}/index.md` depuis un scan du filesystem en consommant `core/i18n/strings.yaml`. Utile après une migration ou une réorganisation manuelle. Détecte la langue de l'utilisateur depuis `~/.{cli}/memory-kit.json`. |
| `enforce-linking.py` | Appliquer rétroactivement l'invariant **zero orphan atom** sur un vault existant : ajoute la ligne d'intro localisée avec liens croisés dans chaque `context.md` ↔ `history.md`. Idempotent. À utiliser une fois après upgrade vers v0.5.4. |
| `scaffold-vault.py` | Bootstrap d'un nouveau vault v0.5 vide (9 zones + sous-dossiers + `.gitignore` + `index.md` squelette i18n via `rebuild-vault-index.py`). Idempotent. Appelé automatiquement par `deploy.{sh,ps1}` lors d'une première installation (vault sans `10-episodes/`). |
| `fix-double-encoding.py` | Correction rétroactive du double-encodage UTF-8→CP1252→UTF-8 sur les fichiers du vault (signature `Ã©`, `â€"`, `Â `). À utiliser uniquement si l'agent a écrit via un shell mal configuré. |
| `inject-archeo-hashes.py` | Correction rétroactive des frontmatters d'atomes archeo-* et de fichiers topologie produits avant le durcissement v0.7.0 : injecte `content_hash` (SHA-256 du body normalisé), `previous_atom`/`previous_topology_hash` vides, `source_doc_hash`, `friction_detected`. Dédup les top-level keys YAML doublées. Normalise les enum localisées (`force: ligne-rouge` → `red-line`). Pour les archives `archeo-git` sans `commit_sha` : tente `git rev-list -n 1 <tag>` via `--repo-root`. Idempotent. |
| `validate-archeo-frontmatter.py` | Lint des frontmatters d'atomes archeo-* et de fichiers topologie contre le schéma v0.7.0 (no duplicate keys, MUST fields par source, enum values en anglais canonique). Exit 0 si conforme, 1 sinon — utilisable en CI. |
| `inject-display-frontmatter.py` | Backfill du champ `display` du frontmatter universel sur tous les fichiers du vault (v0.7.2). Conventions par kind : `{slug} — context`, `{slug} — history`, `{slug} — {date} {short}` (archives), `{slug} — topology`, `principle: {title}`, etc. Idempotent, dry-run par défaut. Préserve les `display` custom (utiliser `--force` pour les écraser). Sans valeur ajoutée tant que le plugin Obsidian Front Matter Title n'est pas installé, mais safe à exécuter de toute façon (le champ reste un no-op si non lu). |

Exemple de migration FR→EN d'un vault existant :

```bash
# 1. Backup obligatoire
cp -r ~/vault ~/vault.backup-$(date +%Y-%m-%d)

# 2. Dry-run pour inspecter le plan
python scripts/migrate-vault-v05-to-v052.py --vault ~/vault

# 3. Apply
python scripts/migrate-vault-v05-to-v052.py --vault ~/vault --apply

# 4. Régénérer l'index avec le bon i18n
python scripts/rebuild-vault-index.py --vault ~/vault

# 5. Appliquer l'invariant zero-orphan-atom (liens croisés context ↔ history)
python scripts/enforce-linking.py --vault ~/vault
```

---

## Feuille de route

| Phase | État | Portée |
|---|---|---|
| **Phase 1** | Terminée | Détection multi-CLI et adapters pour Claude Code, Gemini CLI, Codex, Mistral Vibe, GitHub Copilot CLI. |
| **Phase 3** | **Terminée (v0.8.0)** | Serveur MCP `secondbrain-memory-kit` (Python, fastmcp 2.x). 24 outils MCP, 7 cibles auto-configurées (Claude Code/Desktop, Codex CLI/Desktop, Copilot CLI, Mistral Vibe, Gemini CLI). Pattern MCP-first / skills-fallback : les adapters skills restent en place et servent de fallback transparent. |
| **Phase 2** | À venir | Déploiement standardisé pour équipe ; vault partagé sur infrastructure locale ; promotion `CollectiveBrain` (flag `collective` déjà persisté en v0.5). |
| **Phase 3.x** | À venir | Port complet des 5 outils archeo (actuellement stubs MCP avec fallback skills) + intégration des doc-readers Python (`scripts/doc-readers/`) dans `mem_doc` pour PDF/DOCX/PPTX/XLSX/CSV/HTML. |

---

## Désinstallation

Retirer les installations correspondant aux CLI déployées. Chemins par défaut ci-dessous ; adapter si `CLAUDE_CONFIG_DIR` (ou équivalent) est défini.

```powershell
# Serveur MCP secondbrain-memory-kit (v0.8.0)
pipx uninstall memory-kit-mcp
Remove-Item "$HOME\.memory-kit\config.json" -Force
# Retirer manuellement l'entrée mcpServers.secondbrain-memory-kit dans :
#   $HOME\.claude.json
#   $HOME\AppData\Roaming\Claude\claude_desktop_config.json
#   $HOME\.copilot\mcp-config.json
#   $HOME\.gemini\settings.json
# Retirer manuellement la section MEMORY-KIT (entre markers # MEMORY-KIT:START/END) dans :
#   $HOME\.codex\config.toml
#   $HOME\.vibe\config.toml

# Claude Code (skills fallback)
Remove-Item "$HOME\.claude\commands\mem-*.md" -Force
Remove-Item "$HOME\.claude\skills\mem-*.md" -Force
Remove-Item "$HOME\.claude\memory-kit.json" -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.claude\CLAUDE.md
# Retirer manuellement les patterns allow mem-* dans $HOME\.claude\settings.json

# Gemini CLI (skills fallback)
Remove-Item "$HOME\.gemini\extensions\memory-kit" -Recurse -Force
Remove-Item "$HOME\.gemini\memory-kit.json" -Force
# Retirer l'entrée memory-kit dans $HOME\.gemini\extension-enablement.json

# Codex CLI (skills fallback)
Remove-Item "$HOME\.codex\prompts\mem-*.md" -Force
Remove-Item "$HOME\.codex\skills\mem-*" -Recurse -Force
Remove-Item "$HOME\.codex\memory-kit.json" -Force

# Mistral Vibe (skills fallback)
Remove-Item "$HOME\.vibe\skills\mem-*" -Recurse -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.vibe\AGENTS.md

# GitHub Copilot CLI (skills fallback)
Remove-Item "$HOME\.copilot\skills\mem-*" -Recurse -Force
Remove-Item "$HOME\.copilot\memory-kit.json" -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.copilot\copilot-instructions.md
```

Le vault `memory/` reste intact. Les archives, projets et domaines sont préservés.

---

## Licence et crédits

### Licence

Distribué sous licence **MIT** — © SI Groupe Mondial Tissus.

### Concept original — Raphaël Fages / Fractality Studio

SecondBrain est l'adaptation d'un concept développé à l'origine par **Raphaël Fages** au sein de son agence [Fractality Studio](https://fractality.studio/) : structurer la mémoire d'un agent LLM comme un *second cerveau* personnel, avec un cycle de prise de notes et de relecture analogue à un rythme biologique veille-sommeil.

Les principes fondateurs suivants viennent directement de ce travail initial :

- Une couche de fichiers Markdown lus et écrits par l'agent suffit à briser l'amnésie inter-sessions, sans infrastructure serveur.
- Le triptyque **archive immuable / contexte mutable / historique chronologique** permet à la fois la traçabilité et la reprise rapide.
- Le déclenchement par langage naturel — et pas seulement par commande explicite — rend le cycle ergonomique pour l'utilisateur final.

L'implémentation présente dans ce dépôt adapte ces principes au contexte SI Groupe Mondial Tissus : support multi-CLI, vault Obsidian, procédures factorisées en une source unique de vérité, déploiement PowerShell + bash, refonte brain-centric (v0.5), schéma anglais + i18n conversationnel (v0.5.2), préparation aux Phases 2 (déploiement équipe) et 3 (serveur MCP).

### Double nommage

Le projet conserve volontairement un double nom pour honorer cette origine :

- **SecondBrain** — nom de la distribution SI-GMT, du dépôt GitHub et de la documentation utilisateur.
- **memory-kit** — nom technique conservé pour les artefacts internes : fichier de configuration (`memory-kit.json`), extension Gemini CLI, futur serveur MCP.
