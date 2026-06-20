# memory-kit-mcp v0.15.0 — Archivage délégué (brief→expand+gate)

Première release stable de SecondBrain. Le cycle `/mem-archive` (mode full) gagne une délégation économique qui divise son coût et sa latence sans toucher à la qualité.

## Nouveautés

**Délégation `brief→expand` de l'archivage.** Sur tout hôte capable de spawner un sous-agent, `/mem-archive` délègue désormais le **rendu** de l'archive à un modèle léger, en gardant le **jugement** sur le modèle fort :

- **Phase A (modèle fort)** : lit la session une fois, produit un `ArchiveBrief` structuré (tout le jugement, zéro prose).
- **Phase B (sous-agent économique)** : rédige l'archive + le contexte à partir du brief, puis persiste via `mem_archive`.
- **Phase C (gate déterministe)** : nouveau paramètre `expect_decisions` sur `mem_archive` → vérifie que **chaque décision cumulée survit** dans le nouveau `context.md` (signature alphanumérique, tolérante au reformatage, stricte sur l'omission). Aucune écriture partielle (`CumulativeDecisionDroppedError`).

Activation **automatique** (pas de flag). Cascade d'escalade garantissant qu'aucun chemin ne dégrade la qualité : retry sous-agent → reprise modèle fort → repli skill-mode. Gain mesuré (dogfood) : **~3× plus rapide, ~10× moins coûteux**, qualité préservée.

**4ᵉ classe d'asset : sous-agents enregistrés (agnostique multi-CLI).** Le contrat de l'expander vit dans un bloc core unique (`core/procedures/_archive-expander.md`), consommé sans duplication par deux chemins :
- inline dans le skill `mem-archive` de **chaque** plateforme (chemin universel — tout CLI avec capacité sous-agent) ;
- agent enregistré Claude Code (`~/.claude/agents/`), déployé par le nouveau pas « Agents » de `deploy.ps1` / `deploy.sh`.

Capability-gating strict : on n'invente pas de format d'agent non vérifié ; les autres CLI reçoivent le contrat inline.

## Qualité

- Suite : **583 passed / 1 skipped, 83.23 % coverage**.
- `deploy.ps1` (parse) + `deploy.sh` (`bash -n`) vérifiés ; includes résolus sans fuite.

## Assets

- `memory_kit_mcp-0.15.0-py3-none-any.whl`
- `memory_kit_mcp-0.15.0.tar.gz`
- `memory_kit_mcp-0.15.0-wheelhouse-win_amd64.zip` (70 wheels cp312/win, offline corporate-safe)

## Mise à jour

`deploy.ps1 -RepairMcp` (ou `deploy.sh --repair-mcp`) pour passer l'engine pipx à 0.15.0, puis relancer la CLI. App desktop : voir `sb-desktop-v0.12.2`.
