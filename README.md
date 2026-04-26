# SecondBrain

> Mémoire persistante pour agents CLI — Claude Code, Gemini CLI, Codex, Mistral Vibe.

[![License: MIT](https://img.shields.io/github/license/SI-GMT/SecondBrain?color=blue)](./LICENSE)
[![Latest release](https://img.shields.io/github/v/release/SI-GMT/SecondBrain)](https://github.com/SI-GMT/SecondBrain/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#prérequis)
[![Shells](https://img.shields.io/badge/shells-PowerShell%207%2B%20%7C%20bash-5391FE)](#prérequis)
[![CLIs](https://img.shields.io/badge/CLIs-Claude%20Code%20%7C%20Gemini%20%7C%20Codex%20%7C%20Vibe-8A2BE2)](#cli-supportées)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR%20%7C%20ES%20%7C%20DE%20%7C%20RU-orange)](#langues-supportées)

SecondBrain s'appuie sur un concept développé à l'origine par **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)). Voir la section [Licence et crédits](#licence-et-crédits) pour les détails sur le travail original et l'adaptation menée chez SI Groupe Mondial Tissus.

> **v0.5.3** — Refonte brain-centric (9 zones mémorielles), schéma 100 % anglais (folders, frontmatter, tags), instructions LLM en anglais (efficacité maximale), conversation dans la langue native de l'utilisateur (EN/FR/ES/DE/RU bundle, sélection à l'install). Tooling : migration FR→EN d'un vault existant + régénération de l'index depuis le filesystem.

---

## Sommaire

- [Présentation](#présentation)
- [Fonctionnement](#fonctionnement)
- [Installation](#installation)
- [Architecture](#architecture)
- [Commandes](#commandes)
- [Langues supportées](#langues-supportées)
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
| **Gemini CLI** | Fonctionnel, validé en conditions réelles | Extension `memory-kit` + `GEMINI.md` + commandes TOML |
| **Codex** | Fonctionnel, validé en conditions réelles | Prompts + skills |
| **Mistral Vibe** | Fonctionnel, validé en conditions réelles | Skills dans `~/.vibe/skills/` + bloc injecté dans `~/.vibe/AGENTS.md` |

Le script d'installation détecte automatiquement les CLI présentes sur le poste et ne déploie que les adapters correspondants.

---

## Fonctionnement

Le cycle de mémoire se décompose en trois phases :

1. **Reprise** — L'utilisateur écrit « reprends », « on continue », ou tape `/mem-recall`. L'agent charge le contexte du projet en quelques secondes, sans re-briefing.
2. **Session** — L'agent met à jour silencieusement le `context.md` du projet dès qu'une décision structurante émerge. Aucune intervention explicite requise.
3. **Archivage** — L'utilisateur écrit « on s'arrête », « je pars », ou tape `/mem-archive`. L'agent produit un résumé horodaté de la session (décisions, état, prochaines étapes) avant que `/clear` ne soit lancé.

### Fiabilité du déclenchement par langage naturel

Le déclenchement automatique repose sur des instructions injectées dans la config utilisateur de la CLI (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`). Sa fiabilité dépend du modèle sous-jacent : très élevée sur Claude Code, bonne sur Gemini CLI, variable ailleurs. Les slash commands explicites (`/mem-recall`, `/mem-archive`, etc.) produisent un comportement identique sur toutes les plateformes qui les exposent.

### Anglais structurel, conversation native

Toutes les **instructions destinées au LLM** (procédures, frontmatter, tags, valeurs persistées) sont en anglais — les LLM modernes raisonnent et exécutent plus précisément sur instructions EN. Mais **l'agent répond toujours dans la langue conversationnelle de l'utilisateur**, configurée à l'installation et stockée dans `memory-kit.json`. Le contenu structuré (titres de sections, libellés persistés) est résolu via `core/i18n/strings.yaml` qui bundle EN/FR/ES/DE/RU.

---

## Installation

### Prérequis

- **PowerShell 7+** (`pwsh`) sur Windows, **ou** **bash** sur macOS/Linux/git-bash.
- **Au moins une CLI supportée** installée, avec une session préalablement lancée pour que le dossier de config utilisateur existe (`~/.claude/`, `~/.gemini/`, `~/.codex/` ou `~/.vibe/`).
- **Obsidian** (optionnel) — pour visualiser le vault sous forme de graphe.

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

| CLI | Fichiers déployés |
|---|---|
| Claude Code | `~/.claude/commands/mem-*.md`, `~/.claude/skills/mem-*.md`, `memory-kit.json`, bloc dans `CLAUDE.md`, vault ajouté à `permissions.additionalDirectories` dans `settings.json` |
| Gemini CLI | Extension dans `~/.gemini/extensions/memory-kit/`, `memory-kit.json`, activation dans `extension-enablement.json` |
| Codex | `~/.codex/prompts/mem-*.md`, `~/.codex/skills/mem-*/SKILL.md`, `memory-kit.json` |
| Mistral Vibe | `~/.vibe/AGENTS.md` (bloc injecté), `~/.vibe/skills/mem-*/SKILL.md` |

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
│   └── mistral-vibe/           Bloc AGENTS.md + skills (format Anthropic)
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
| `/mem-archeo [repo]` | Reconstituer l'historique Git | N archives datées (1 par tag/release/merge/fenêtre de commits) |
| `/mem-archeo-atlassian {url}` | Rétro Confluence + Jira | 1 archive par page Confluence, enrichies par les tickets Jira liés |
| `/mem-note` | Note de connaissance | Insère dans `20-knowledge/` |
| `/mem-principle` | Principe / heuristique / ligne rouge | Insère dans `40-principles/` |
| `/mem-goal` | Objectif (intention future) | Insère dans `50-goals/` (horizon court/moyen/long détecté) |
| `/mem-person` | Fiche personne | Insère dans `60-people/` (sensitive=true par défaut) |

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
| `scaffold-vault-v0.5.ps1` | Bootstrap d'un nouveau vault v0.5 vide (9 zones + sous-dossiers + `index.md` squelette). Idempotent. |
| `fix-double-encoding.py` | Correction rétroactive du double-encodage UTF-8→CP1252→UTF-8 sur les fichiers du vault (signature `Ã©`, `â€"`, `Â `). À utiliser uniquement si l'agent a écrit via un shell mal configuré. |

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
```

---

## Feuille de route

| Phase | État | Portée |
|---|---|---|
| **Phase 1** | Terminée | Détection multi-CLI et adapters pour Claude Code, Gemini CLI, Codex, Mistral Vibe. |
| **Phase 2** | À venir | Déploiement standardisé pour équipe ; vault partagé sur infrastructure locale ; promotion `CollectiveBrain` (flag `collective` déjà persisté en v0.5). |
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
Remove-Item "$HOME\.vibe\skills\mem-*" -Recurse -Force
# Retirer manuellement le bloc MEMORY-KIT dans $HOME\.vibe\AGENTS.md
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
