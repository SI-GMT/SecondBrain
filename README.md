# SecondBrain

> Mémoire persistante pour agents CLI — Claude Code, Gemini CLI, Codex, Mistral Vibe.

[![License: MIT](https://img.shields.io/github/license/SI-GMT/SecondBrain?color=blue)](./LICENSE)
[![Latest release](https://img.shields.io/github/v/release/SI-GMT/SecondBrain)](https://github.com/SI-GMT/SecondBrain/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#prérequis)
[![PowerShell](https://img.shields.io/badge/PowerShell-7%2B-5391FE?logo=powershell&logoColor=white)](#prérequis)
[![CLIs](https://img.shields.io/badge/CLIs-Claude%20Code%20%7C%20Gemini%20%7C%20Codex%20%7C%20Vibe-8A2BE2)](#cli-supportées)
[![Docs](https://img.shields.io/badge/docs-français-informational)](#sommaire)

SecondBrain s'appuie sur un concept développé à l'origine par **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)). Voir la section [Licence et crédits](#licence-et-crédits) pour les détails sur le travail original et l'adaptation menée chez SI Groupe Mondial Tissus.

---

## Sommaire

- [Présentation](#présentation)
- [Fonctionnement](#fonctionnement)
- [Installation](#installation)
- [Architecture](#architecture)
- [Commandes](#commandes)
- [Performances](#performances)
- [Multi-projets](#multi-projets)
- [Feuille de route](#feuille-de-route)
- [Désinstallation](#désinstallation)
- [Licence et crédits](#licence-et-crédits)

---

## Présentation

Les CLI LLM agentiques n'ont pas de mémoire entre les sessions. Après un `/clear` ou une fermeture d'IDE, l'intégralité du contexte — état du projet, décisions prises, prochaines étapes — doit être ré-exposée manuellement à l'agent.

SecondBrain installe une mémoire locale structurée que l'agent lit et écrit automatiquement, au niveau utilisateur (dans `~/.claude/`, `~/.gemini/`, `~/.codex/` ou `~/.vibe/` selon la CLI). Le contexte devient disponible depuis n'importe quel projet sur le poste.

**Gain mesurable** : la reprise de session consomme environ 2× moins de tokens qu'un re-briefing manuel équivalent.

### CLI supportées

| CLI | Maturité | Surface d'installation |
|---|---|---|
| **Claude Code** | Référence, éprouvée en production | Skills + slash commands + bloc `CLAUDE.md` + permissions |
| **Gemini CLI** | Fonctionnel, tests terrain en cours | Extension `memory-kit` + `GEMINI.md` + commandes TOML |
| **Codex** | Fonctionnel, tests terrain en cours | Prompts + skills |
| **Mistral Vibe** | Fonctionnel (pas de slash commands : tout passe par les instructions) | Bloc injecté dans `instructions.md` |

Le script d'installation détecte automatiquement les CLI présentes sur le poste et ne déploie que les adapters correspondants. Les retours d'expérience et contributions sur les trois adapters non-Claude sont les bienvenus.

---

## Fonctionnement

Le cycle de mémoire se décompose en trois phases :

1. **Reprise** — L'utilisateur écrit « reprends », « on continue », ou tape `/mem-recall`. L'agent charge le contexte du projet en quelques secondes, sans re-briefing.
2. **Session** — L'agent met à jour silencieusement le `contexte.md` du projet dès qu'une décision structurante émerge. Aucune intervention explicite requise.
3. **Archivage** — L'utilisateur écrit « on s'arrête », « je pars », ou tape `/mem-archive`. L'agent produit un résumé horodaté de la session (décisions, état, prochaines étapes) avant que `/clear` ne soit lancé.

### Fiabilité du déclenchement par langage naturel

Le déclenchement automatique repose sur des instructions injectées dans la config utilisateur de la CLI (`CLAUDE.md`, `GEMINI.md`, `instructions.md`). Sa fiabilité dépend du modèle sous-jacent : très élevée sur Claude Code, bonne sur Gemini CLI, variable ailleurs. Les slash commands explicites (`/mem-recall`, `/mem-archive`, etc.) produisent un comportement identique sur toutes les plateformes qui les exposent.

---

## Installation

### Prérequis

- **PowerShell 7+** (`pwsh`) pour exécuter `deploy.ps1`.
- **Au moins une CLI supportée** installée, avec une session préalablement lancée pour que le dossier de config utilisateur existe (`~/.claude/`, `~/.gemini/`, `~/.codex/` ou `~/.vibe/`).
- **Obsidian** (optionnel) — pour visualiser le vault sous forme de graphe.

### Déploiement

1. Cloner le dépôt dans un dossier stable du poste :
   ```powershell
   git clone https://github.com/SI-GMT/SecondBrain.git
   ```

2. Lancer le déploiement depuis la racine :
   ```powershell
   .\deploy.ps1
   ```

Le script détecte les CLI présentes, déploie l'adapter correspondant à chacune, et ignore silencieusement les CLI absentes. Si aucune CLI n'est trouvée, un message listant les liens d'installation est affiché puis l'exécution s'arrête proprement.

### Surfaces installées par plateforme

| CLI | Fichiers déployés |
|---|---|
| Claude Code | `~/.claude/commands/mem-*.md`, `~/.claude/skills/mem-*.md`, `memory-kit.json`, bloc dans `CLAUDE.md`, vault ajouté à `permissions.additionalDirectories` dans `settings.json` |
| Gemini CLI | Extension dans `~/.gemini/extensions/memory-kit/`, `memory-kit.json`, activation dans `extension-enablement.json` |
| Codex | `~/.codex/prompts/mem-*.md`, `~/.codex/skills/mem-*/SKILL.md`, `memory-kit.json` |
| Mistral Vibe | Bloc injecté dans `~/.vibe/instructions.md` |

### Choix du vault

| Scénario | Commande |
|---|---|
| Première installation (défaut) | `.\deploy.ps1` — vault à `{racine du kit}\memory` |
| Première installation, chemin personnalisé | `.\deploy.ps1 -VaultPath "D:\mes-notes\cerveau"` |
| Mise à jour | `.\deploy.ps1` — le chemin du vault existant est relu automatiquement depuis les `memory-kit.json` déjà déployés. Le script peut être lancé depuis n'importe quel répertoire |
| Migration vers un nouvel emplacement | `.\deploy.ps1 -VaultPath "D:\nouveau\chemin"` — met à jour les configs mais ne déplace pas les fichiers existants (à faire manuellement) |

### Vérification

Depuis n'importe quel projet, ouvrir une CLI supportée et taper :

```
/mem-recall
```

L'agent doit répondre :

```
Aucune session trouvée. Mémoire initialisée — memory/_index.md est prêt.
Décris ce sur quoi tu travailles et on commence.
```

Sur Mistral Vibe, qui n'expose pas de slash commands user-level, déclencher avec une phrase : *« charge mon contexte mémoire »*.

### Ouvrir le vault dans Obsidian (optionnel)

1. Installer Obsidian : <https://obsidian.md>
2. Ouvrir Obsidian → *Open folder as vault* → sélectionner `memory/`.

Le dossier `memory/` est déjà un vault Obsidian valide.

---

## Architecture

```
SecondBrain/
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
│   ├── claude-code/            Skills + slash commands + bloc CLAUDE.md
│   ├── gemini-cli/             Extension memory-kit + GEMINI.md + TOML
│   ├── codex/                  Prompts + skills
│   └── mistral-vibe/           Bloc injecté dans ~/.vibe/instructions.md
├── memory/                     Vault Obsidian local (non versionné)
│   ├── _index.md
│   ├── archives/               Une archive par session complète (immuable)
│   └── projets/
│       └── {nom}/
│           ├── contexte.md     Snapshot mutable — toujours à jour
│           └── historique.md   Fil chronologique des sessions
└── deploy.ps1                  Assemble les procédures et installe chaque
                                adapter dans la config utilisateur de la CLI
```

**Single source of truth** — toute logique procédurale vit dans `core/procedures/`. Les adapters n'apportent que du frontmatter et du formatage spécifique à leur plateforme. `deploy.ps1` substitue à la volée le marqueur `{{PROCEDURE}}` par le contenu du fichier core correspondant. Pas de duplication, pas de divergence entre plateformes.

---

## Commandes

Toutes les commandes sont préfixées `mem-*` pour éviter les collisions avec les commandes natives des CLI.

### Cycle de session

| Déclencheur | Contexte | Effet |
|---|---|---|
| Langage naturel (« reprends », « on continue », « tu te rappelles ») | Début de session | Chargement automatique du contexte |
| `/mem-recall` | Début de session (explicite) | Chargement + briefing affiché |
| `/mem-recall {projet}` | Plusieurs projets existent | Chargement direct du projet nommé |
| *Silencieux (incrémental)* | Fait important émergeant en cours de session | Mise à jour de `contexte.md` sans création d'archive |
| Langage naturel (« on s'arrête », « je pars ») | Fin de session | Mode archive complet |
| `/mem-archive` | Avant `/clear` (explicite) | Résumé + écriture des fichiers |

### Gestion du vault

| Commande | Intention | Effet |
|---|---|---|
| `/mem-list-projects` | Lister les projets en mémoire | Tableau : slug, phase, dernière session, nombre de sessions |
| `/mem-search {requête}` | Rechercher dans le vault | Recherche plein-texte avec contexte |
| `/mem-rename-project {ancien} {nouveau}` | Renommer un projet | Renomme le slug partout (dossier, frontmatters, tags, index) |
| `/mem-merge-projects {source} {cible}` | Fusionner deux projets | Retaggue les archives, concatène l'historique, supprime la source. `contexte.md` à fusionner manuellement |
| `/mem-digest {projet} [N]` | Synthétiser les N dernières sessions | Arcs majeurs, décisions structurantes, dérive des prochaines étapes. Lecture seule (N = 5 par défaut) |
| `/mem-rollback-archive [projet]` | Annuler la dernière archive | Supprime l'archive et retire ses références. N'auto-restaure pas `contexte.md` |

---

## Performances

Chaque archive complet produit deux fichiers :

- Une **archive** complète (~70 lignes) — immuable, trace historique.
- Un **`contexte.md`** synthétisé (~25 lignes) — écrasé à chaque session.

Au `/mem-recall` suivant, l'agent lit `contexte.md` en priorité. Le briefing fait donc 25 lignes au lieu de 70, soit approximativement 2× moins de tokens qu'un re-briefing manuel qui reproduirait tout le contexte historique.

---

## Multi-projets

Un seul vault peut contenir N projets. Chaque projet a son propre dossier dans `memory/projets/` :

```
/mem-recall site-client-a
/mem-recall app-mobile
```

Le kit étant installé au niveau utilisateur, il n'est pas nécessaire de le recopier dans chaque projet.

---

## Feuille de route

| Phase | État | Portée |
|---|---|---|
| **Phase 1** | Terminée | Détection multi-CLI et adapters pour Claude Code, Gemini CLI, Codex, Mistral Vibe. Claude Code éprouvé ; les trois autres adapters fonctionnels mais tests terrain en cours. |
| **Phase 2** | À venir | Déploiement standardisé pour équipe ; vault partagé sur infrastructure locale. |
| **Phase 3** | À venir | Migration de la logique vers un serveur MCP `memory-kit`. Les adapters deviennent des shims délégant au MCP ; une seule implémentation pour toutes les CLI compatibles MCP. |

---

## Désinstallation

Retirer les installations correspondant aux CLI déployées. Chemins par défaut ci-dessous ; adapter si `CLAUDE_CONFIG_DIR` (ou équivalent) est défini.

```powershell
# Claude Code
Remove-Item "$HOME\.claude\commands\mem-*.md" -Force
Remove-Item "$HOME\.claude\skills\mem-*.md" -Force
Remove-Item "$HOME\.claude\memory-kit.json" -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.claude\CLAUDE.md
# Retirer manuellement les patterns allow mem-* dans $HOME\.claude\settings.json

# Gemini CLI
Remove-Item "$HOME\.gemini\extensions\memory-kit" -Recurse -Force
Remove-Item "$HOME\.gemini\memory-kit.json" -Force
# Retirer l'entrée memory-kit dans $HOME\.gemini\extension-enablement.json

# Codex
Remove-Item "$HOME\.codex\prompts\mem-*.md" -Force
Remove-Item "$HOME\.codex\skills\mem-*" -Recurse -Force
Remove-Item "$HOME\.codex\memory-kit.json" -Force

# Mistral Vibe
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.vibe\instructions.md
```

Le vault `memory/` reste intact. Les archives et les projets sont préservés.

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

L'implémentation présente dans ce dépôt adapte ces principes au contexte SI Groupe Mondial Tissus : support multi-CLI, vault Obsidian, procédures factorisées en une source unique de vérité, déploiement PowerShell, préparation aux Phases 2 (déploiement équipe) et 3 (serveur MCP).

### Double nommage

Le projet conserve volontairement un double nom pour honorer cette origine :

- **SecondBrain** — nom de la distribution SI-GMT, du dépôt GitHub et de la documentation utilisateur.
- **memory-kit** — nom technique conservé pour les artefacts internes : fichier de configuration (`memory-kit.json`), extension Gemini CLI, futur serveur MCP.
