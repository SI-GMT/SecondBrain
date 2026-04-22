# KIT-MÉMOIRE — Mémoire de session pour Claude Code

Résout l'amnésie inter-sessions de Claude : quand tu fais `/clear`, le contexte n'est pas perdu. Il est archivé localement et rechargeable en 30 secondes à la prochaine session.

**Gain concret** : la reprise de session consomme 2× moins de tokens qu'un re-briefing manuel.

---

## Le problème

Claude Code n'a pas de mémoire entre les sessions. Après un `/clear` ou une fermeture d'IDE, tu dois tout ré-expliquer : l'état du projet, les décisions prises, les prochaines étapes.

Ce kit installe une mémoire locale structurée que Claude lit et écrit automatiquement, au niveau **utilisateur** (dans `~/.claude/`) — donc disponible depuis n'importe quel projet sur ton poste.

---

## Le cycle de la mémoire

C'est un rituel biologique : l'agent prend des notes en continu, les relit en se réveillant.

```
En arrivant    →  Dire « reprends », « on continue », ou taper /mem-recall.
                  Claude charge le contexte en 30 secondes.
                  Pas de re-briefing. Travail immédiat.

En travaillant →  Claude met à jour silencieusement le contexte
                  dès qu'une décision ou un fait important émerge.

En partant     →  Dire « on s'arrête », « je pars », ou taper /mem-archive.
                  Claude résume la session (décisions, état, prochaines étapes).

                  /clear
                  Session propre. Mémoire intacte.
```

Le `/clear` n'est plus une perte — c'est un sommeil propre.

---

## Installation

### Prérequis
- **PowerShell 7+** (`pwsh`) pour exécuter `deploy.ps1`.
- **Claude Code** installé (au moins une session déjà lancée pour que `~/.claude/` existe).
- **Obsidian** (optionnel) — pour visualiser le vault comme graphe.

### Étape 1 — Placer le kit

Cloner ou copier le kit dans un dossier stable de ton poste, par exemple :

```
C:\Users\{toi}\memory-kit\
```

Le dossier contiendra `core/`, `adapters/`, `memory/`, `deploy.ps1` et ce README.

### Étape 2 — Lancer le déploiement

Depuis la racine du kit, dans un terminal PowerShell :

```powershell
.\deploy.ps1
```

Le script :
- Détecte les CLI IA installées sur le poste : **Claude Code**, **Gemini CLI**, **Codex**, **Mistral Vibe**. Binaire sur le `PATH` ou dossier de config utilisateur présent.
- Déploie l'adapter correspondant pour chaque CLI détectée. Une CLI absente est simplement ignorée (pas d'erreur).
- Si **aucune** CLI n'est trouvée, affiche un message amical avec les liens d'installation et s'arrête proprement.

Par plateforme :

- **Claude Code** — slash commands dans `~/.claude/commands/`, skills dans `~/.claude/skills/`, `memory-kit.json` + bloc MEMORY-KIT injecté dans `~/.claude/CLAUDE.md`, vault ajouté à `permissions.additionalDirectories` dans `~/.claude/settings.json`.
- **Gemini CLI** — extension `memory-kit` dans `~/.gemini/extensions/memory-kit/` (manifest, `GEMINI.md`, slash commands TOML), `memory-kit.json` + activation dans `extension-enablement.json`.
- **Codex** — slash commands dans `~/.codex/prompts/`, skills dans `~/.codex/skills/{nom}/SKILL.md`, `memory-kit.json`.
- **Mistral Vibe** — bloc MEMORY-KIT injecté dans `~/.vibe/instructions.md` (Vibe n'a pas de slash commands user-level exposés ; tout passe par les instructions globales et le tool use).

**Choix du vault** :

- **Première installation** : par défaut `{racine du kit}\memory` (créé côté kit). Surcharge possible :
  ```powershell
  .\deploy.ps1 -VaultPath "D:\mes-notes\cerveau"
  ```
- **Mise à jour** (le kit est déjà installé sur le poste) : `deploy.ps1` lit le chemin du vault déjà enregistré dans les `memory-kit.json` existants (`~/.claude/`, `~/.gemini/`, `~/.codex/`) et le réutilise automatiquement. **Plus besoin de repasser `-VaultPath`**. Le script peut donc être relancé depuis n'importe quel répertoire de travail sans avoir à se positionner sur le vault.
- **Migration du vault** vers un nouvel emplacement : passer explicitement `-VaultPath "D:\nouveau\chemin"`. Note : `deploy.ps1` met à jour les configs, mais ne déplace pas les fichiers existants — c'est à faire manuellement avant ou après.

### Étape 3 — (Optionnel) Ouvrir le vault dans Obsidian

1. Télécharger Obsidian : https://obsidian.md
2. Ouvrir Obsidian → « Ouvrir un vault » → sélectionner `memory/`.

Le dossier `memory/` est déjà un vault Obsidian valide.

### Étape 4 — Vérifier

Depuis n'importe quel projet, ouvrir Claude Code et taper :

```
/mem-recall
```

Claude doit répondre :

```
Aucune session trouvée. Mémoire initialisée — memory/_index.md est prêt.
Décris ce sur quoi tu travailles et on commence.
```

La mémoire est opérationnelle.

---

## Architecture

```
kit/
├── core/procedures/            Spec procédurale agnostique (source de vérité)
│   ├── mem-archive.md
│   ├── mem-recall.md
│   ├── mem-list-projects.md
│   ├── mem-search.md
│   ├── mem-rename-project.md
│   ├── mem-merge-projects.md
│   ├── mem-digest.md
│   └── mem-rollback-archive.md
├── adapters/
│   └── claude-code/            Seul adapter actif pour l'instant
│       ├── skills/             Templates (frontmatter + {{PROCEDURE}})
│       ├── commands/           Slash commands user-facing
│       └── claude-md-block.md  Bloc injecté dans ~/.claude/CLAUDE.md
├── memory/                     Vault Obsidian local (non versionné)
│   ├── _index.md
│   ├── archives/               Une archive par session complète (immuable)
│   └── projets/                Un dossier par projet
│       └── {nom}/
│           ├── contexte.md     Snapshot mutable — toujours à jour
│           └── historique.md   Fil chronologique des sessions
└── deploy.ps1                  Assemble et installe dans ~/.claude/
```

---

## Déclenchement automatique et commandes

Toutes les commandes sont préfixées `mem-*` pour éviter les collisions avec de futures commandes natives des CLI.

### Cycle session

| Canal | Quand | Ce que Claude fait |
|---|---|---|
| Langage naturel (« reprends », « on continue », « tu te rappelles ») | Début de session | Charge le contexte automatiquement |
| `/mem-recall` | Début de session (explicite) | Charge le contexte, affiche le briefing |
| `/mem-recall {projet}` | Si plusieurs projets existent | Charge directement le projet nommé |
| **Silencieux (incrémental)** | Pendant la session, dès qu'un fait important émerge | Met à jour `contexte.md` sans créer d'archive |
| Langage naturel (« on s'arrête », « je pars ») | Fin de session | Mode archive complet |
| `/mem-archive` | Avant `/clear` (explicite) | Résume la session, écrit les fichiers |

### Gestion du vault

| Commande | Intention naturelle | Ce que ça fait |
|---|---|---|
| `/mem-list-projects` | « liste mes projets », « quels projets j'ai en mémoire ? » | Tableau des projets : slug, phase, dernière session, nb sessions |
| `/mem-search {requête}` | « cherche dans la mémoire X », « trouve les archives qui parlent de Y » | Recherche plein-texte sur le vault avec contexte |
| `/mem-rename-project {ancien} {nouveau}` | « renomme le projet X en Y » | Renomme le slug partout (dossier, frontmatters, tags, index). Préserve les noms de fichiers d'archives |
| `/mem-merge-projects {source} {cible}` | « fusionne X dans Y » | Retaggue les archives de la source, concatène l'historique, supprime le dossier source. `contexte.md` à fusionner manuellement |
| `/mem-digest {projet} [N]` | « résume-moi les N dernières sessions de X », « fil rouge de X » | Synthèse des arcs, décisions structurantes, dérive (N=5 par défaut). Lecture seule |
| `/mem-rollback-archive [projet]` | « annule la dernière archive », « rollback l'archive de X » | Supprime la dernière archive + retire ses références. N'auto-restaure PAS `contexte.md` |

---

## Pourquoi 2× moins de tokens ?

Chaque archive complet produit deux fichiers :

- Une **archive** complète (~70 lignes) — immuable, trace historique
- Un **`contexte.md`** synthétisé (~25 lignes) — écrasé à chaque session

Au `/mem-recall` suivant, Claude lit `contexte.md` en priorité. Résultat : briefing en 25 lignes au lieu de parser 70 lignes d'archive.

---

## Multi-projets

Un seul vault, N projets. Chaque projet a son propre dossier dans `memory/projets/`.

```
/mem-recall site-client-a
/mem-recall app-mobile
```

Le kit est installé au niveau utilisateur — pas besoin de le recopier dans chaque projet.

---

## Feuille de route

- **Phase 1 (terminée)** — Détection multi-CLI + adapters Claude Code, Gemini CLI, Codex et Mistral Vibe sur un poste unique.
- **Phase 2** — Déploiement standardisé pour équipe ; vault partagé sur infrastructure locale.
- **Phase 3** — Migration de la logique vers un serveur MCP `memory-kit`. Les adapters deviennent des shims qui délèguent au MCP ; une seule implémentation, tous les LLM compatibles via le protocole MCP.

---

## Désinstallation

```powershell
# Supprimer les fichiers installés (adapter les chemins si CLAUDE_CONFIG_DIR est défini)
Remove-Item "$HOME\.claude\commands\mem-*.md" -Force
Remove-Item "$HOME\.claude\skills\mem-*.md" -Force
Remove-Item "$HOME\.claude\memory-kit.json" -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.claude\CLAUDE.md
# Retirer manuellement les patterns allow mem-* dans $HOME\.claude\settings.json
```

Le vault `memory/` reste intact — tes archives sont conservées.
