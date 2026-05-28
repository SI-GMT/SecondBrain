<p align="center">
  <img src="docs/assets/SecondBrain-lockup-horizontal-dark.png" alt="SecondBrain" width="380">
</p>

> **Une mémoire persistante pour vos agents LLM.** Ne re-briefez plus jamais Claude, Gemini, Codex ou Mistral. Le contexte de vos projets vous suit d'une session à l'autre — et même d'un LLM à l'autre.

[![License: AGPL v3+](https://img.shields.io/badge/license-AGPL%20v3%2B-blue)](./LICENSE)
[![Latest release](https://img.shields.io/github/v/release/SI-GMT/SecondBrain)](https://github.com/SI-GMT/SecondBrain/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#prérequis)
[![CLIs](https://img.shields.io/badge/CLIs-Claude%20%7C%20Gemini%20%7C%20Codex%20%7C%20Vibe%20%7C%20Copilot%20%7C%20Antigravity-8A2BE2)](#cli-compatibles)
[![MCP](https://img.shields.io/badge/MCP-secondbrain--memory--kit-success)](#sous-le-capot)
[![i18n](https://img.shields.io/badge/conversation-EN%20%7C%20FR%20%7C%20ES%20%7C%20DE%20%7C%20RU-orange)](#langues-supportées)
[![Desktop](https://img.shields.io/badge/desktop-installer%20Windows%20%7C%20DMG%20macOS-blue)](#installation)

SecondBrain s'appuie sur un concept originel proposé par **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)). Voir [Licence et crédits](#licence-et-crédits).

---

## Le problème

Votre agent LLM oublie tout entre deux sessions. À chaque `/clear`, redémarrage d'IDE ou changement de modèle :

- **Vous re-briefez à la main** — état du projet, décisions, prochaines étapes.
- **Vous payez deux fois les mêmes tokens** — le contexte de la session précédente est rechargé en clair.
- **Vous perdez le fil** — ce que vous aviez décidé hier est noyé dans un nouveau prompt.
- **Vous êtes prisonnier d'un LLM** — basculer chez un concurrent veut dire tout recommencer.

## Ce que SecondBrain change

Une **mémoire locale Markdown** que l'agent lit et écrit lui-même. Vous ne touchez à rien.

| Sans SecondBrain | Avec SecondBrain |
|---|---|
| « Je reprends sur le projet X. État : ... Décisions : ... Prochaine étape : ... » | « On continue. » |
| Re-briefing manuel de 5-15 minutes | Reprise en quelques secondes |
| Contexte coincé chez un fournisseur | Portable entre Claude, Gemini, Codex, Vibe, Copilot, Antigravity |
| L'historique se perd à chaque `/clear` | Archives horodatées immuables, recherchables |
| Vous décidez quand sauvegarder | L'agent met à jour silencieusement à chaque décision |

---

## Les capacités clés

### Reprise instantanée

Vous tapez `/mem-recall` (ou simplement « on continue », « tu te rappelles ? »). L'agent charge en quelques secondes le contexte du projet : phase actuelle, décisions cumulées, prochaines étapes, atomes d'architecture pertinents. Pas de prompt à relire, pas de fichiers à rouvrir.

### Continuité cross-LLM

`/mem-archive` chez un agent. `/mem-recall` chez un autre. Le contexte suit. Utile quand vous :

- **Atteignez le cap quotidien** d'un fournisseur — basculez sans perdre la session.
- **Voulez exploiter une force spécifique** d'un modèle (vision Gemini, raisonnement Claude, vitesse Mistral, gratuit Copilot).
- **Comparez deux LLMs** sur la même tâche, avec exactement le même contexte initial.

### Archivage silencieux pendant la session

L'agent met à jour le contexte du projet **dès qu'une décision structurante émerge**, sans intervention. Vous ne sauvegardez pas — c'est fait pour vous. À la fin de session, `/mem-archive` produit un résumé horodaté immuable + met à jour le contexte vif.

### Archeo de vos dépôts Git existants

Pointez SecondBrain sur n'importe quel dépôt Git. L'agent reconstruit son historique en archives narratives :

- **Une archive par release**, par PR mergée, par cycle de branche, ou par fenêtre temporelle (au choix).
- **Topologie projet automatique** : composants, modèles de données, conventions, décisions implicites.
- **Récupération de contexte fonctionnel** depuis le code lui-même, pas seulement depuis les commits.

Idéal pour onboarder une équipe sur un projet legacy, ou pour redonner vie à un dépôt repris d'un autre développeur.

### Intelligence projet — l'agent lit votre code

Au lieu de simplement lister des fichiers, SecondBrain force l'agent à **ouvrir, lire et synthétiser** le contenu réel de votre projet. Le résultat : une vraie cartographie fonctionnelle (rôles des composants, méthodes clés, patterns récurrents, risques) dans un atome unique consultable d'un coup d'œil.

### Visualisation Obsidian

Le vault est un dossier Markdown standard, lisible avec Obsidian. Vous obtenez gratuitement :

- Un **graphe de connaissance** navigable, coloré par zone fonctionnelle.
- Une **recherche plein-texte** instantanée sur tout l'historique.
- Des **wikilinks** entre projets, décisions, personnes, principes.

Aucune obligation : si vous préférez `grep`, ça marche aussi.

### Multi-projets, multi-langues

Un seul vault contient autant de projets que vous voulez. L'agent vous parle dans la langue de votre choix (FR / EN / ES / DE / RU) — la mémoire interne reste structurellement en anglais pour la précision LLM.

### Hygiène automatique

Le vault s'audite tout seul (`/mem-health-scan`) et se répare en un clic (`/mem-health-repair`). Frontmatter incohérent, liens cassés, atomes orphelins : détectés et corrigés.

---

## Pour qui

- **Développeurs solo** qui jonglent entre plusieurs projets et LLMs.
- **Équipes tech** qui veulent capitaliser le contexte d'un projet entre leurs membres.
- **Consultants** qui doivent reprendre rapidement un projet client après plusieurs semaines.
- **Utilisateurs non-tech** qui utilisent Claude Desktop / Codex / Gemini et veulent une mémoire sans toucher au terminal — installateur **`.exe` Windows** (et bientôt **DMG macOS**) à télécharger + assistant guidé au premier lancement.
- **Toute personne** qui en a marre de réexpliquer son travail à chaque session.

---

## CLI compatibles

| CLI / App | Statut | Mode MCP | Skills fallback |
|---|---|---|---|
| **Claude Code** | Référence, production | ✅ | ✅ |
| **Claude Desktop** | Fonctionnel | ✅ | (MCP only) |
| **Codex CLI** | Production | ✅ | ✅ |
| **Codex Desktop** | Fonctionnel | ✅ (héritage Codex CLI) | — |
| **Gemini CLI** | Production | ✅ | ✅ |
| **Mistral Vibe** | Production | ✅ | ✅ |
| **GitHub Copilot CLI** | Fonctionnel | ✅ | ✅ |
| **Antigravity CLI** | Fonctionnel | ✅ | ✅ |
| **Antigravity Desktop** | Fonctionnel | ✅ | ✅ |

Le script d'installation détecte automatiquement les CLI présentes sur votre poste et ne déploie que celles correspondantes. Aucune CLI n'est requise — installer celles dont vous vous servez suffit.

---

## Installation

Deux chemins selon votre profil.

### Option A — Installateur graphique (recommandé pour la majorité)

Aucune ligne de commande, aucun pré-requis Python.

**Windows** — télécharger [`SecondBrainDesktop-{version}-setup.exe`](https://github.com/SI-GMT/SecondBrain/releases/latest) (~75 MB, runtime Python embarqué) puis double-cliquer. L'installateur dépose tout dans un répertoire que vous choisissez (par défaut `%LOCALAPPDATA%\SecondBrain`). Au premier lancement de l'icône dans la zone de notification, un assistant guidé vous demande :

1. Où placer votre vault (par défaut `~/Documents/SecondBrain`).
2. Votre langue de conversation (EN / FR / ES / DE / RU).
3. Quels clients LLM câbler (Claude Code, Claude Desktop, Codex, Gemini, Vibe, Copilot — auto-détectés).

L'install se fait sans terminal qui flashe, sans pipx à comprendre, sans `deploy.ps1` à invoquer. La présence du noyau Memory Kit et sa version sont surveillées en permanence par l'icône (vert / orange / rouge) ; un menu clic-droit donne accès à *Scan vault*, *Repair vault*, *Check for updates* et *Settings*.

**macOS** — DMG en cours de finalisation, instructions de build dans [`desktop-app/build/macos/README.md`](./desktop-app/build/macos/README.md). Apple Developer ID + notarization requis pour passer Gatekeeper.

**Linux** — pas encore packagé en installateur. Utiliser l'option B.

### Option B — Script de déploiement source (développeurs)

Pour qui veut le repo cloné, ou un poste de dev où d'autres outils déjà installent via pipx :

```bash
git clone https://github.com/SI-GMT/SecondBrain.git
cd SecondBrain
```

```powershell
# Windows
.\deploy.ps1
```

```bash
# macOS / Linux
./deploy.sh
```

### Prérequis

- **Option A** — aucun pré-requis utilisateur. Le Python 3.12 et le `memory-kit-mcp` voyagent dans l'installateur. Inno Setup 6 nécessaire **uniquement** côté builder.
- **Option B** — **PowerShell 7+** (Windows) ou **bash** (macOS/Linux). **Python 3.12+** + **`pipx`** recommandé. Sans `pipx`, mode skills classique reste fonctionnel.
- Dans tous les cas, **au moins une CLI compatible** installée (voir tableau ci-dessus).

Le script (option B) comme l'assistant (option A) détecte les CLI présentes sur votre poste et ne câble que celles correspondantes. Aucune CLI n'est requise pour installer — celles dont vous vous servez suffisent.

### Vérification

Ouvrez une CLI compatible, tapez :

```
/mem-recall
```

L'agent répond dans votre langue :

```
Aucun projet trouvé. Mémoire initialisée.
Décris ce sur quoi tu travailles et on commence.
```

Vous êtes prêt.

Si vous avez installé l'app desktop (option A), l'icône dans la zone de notification doit être verte. Un clic-droit donne l'inventaire des actions disponibles ; survol du nom donne la version d'engine bundlée + celle installée pour vos CLI.

### Visualiser dans Obsidian (optionnel)

1. Installer [Obsidian](https://obsidian.md).
2. *Open folder as vault* → sélectionner le dossier `memory/`.

Le vault est immédiatement consultable.

---

## Concepts

### Le triptyque mémoire

Chaque projet a trois fichiers vivants :

- **`context.md`** — le snapshot mutable, mis à jour à chaque décision. C'est ce que l'agent lit en priorité au `/mem-recall`. Court, précis, toujours à jour.
- **`history.md`** — le fil chronologique des sessions, avec liens vers chaque archive.
- **`archives/`** — un fichier horodaté immuable par session complète. Trace historique, jamais modifiée.

### Architecture brain-centric

Le vault est organisé par **fonctions cognitives**, pas par projet :

| Zone | Contenu |
|---|---|
| `00-inbox` | Captation brute non triée |
| `10-episodes` | Mémoire épisodique — projets et domaines |
| `20-knowledge` | Mémoire sémantique — faits, concepts, fiches |
| `30-procedures` | Savoir-faire — comment faire X |
| `40-principles` | Heuristiques et lignes rouges |
| `50-goals` | Intentions prospectives |
| `60-people` | Carnet relationnel |
| `70-cognition` | Productions non verbales |
| `99-meta` | Méta-mémoire du vault |

Un projet devient un tag transverse qui se projette dans plusieurs zones.

### Déclenchement par langage naturel

Les commandes `/mem-*` sont toujours disponibles, mais le plus souvent vous n'en avez pas besoin :

- « **on continue** », « **reprends** », « **tu te rappelles ?** » → `/mem-recall`
- « **on s'arrête** », « **je pars**, **/clear** » → `/mem-archive`
- « **note ça** », « **garde ce principe** » → `/mem-note`, `/mem-principle`

Le déclenchement automatique est très fiable sur les modèles principaux (Claude, Gemini), variable ailleurs. Les commandes explicites marchent partout.

---

## Aperçu des commandes

### Cycle de session

| Commande | Effet |
|---|---|
| `/mem-recall` | Charge le contexte du projet courant |
| `/mem-recall {projet}` | Charge un projet précis |
| `/mem-archive` | Sauvegarde la session, prêt à `/clear` |

### Capture et ingestion

| Commande | Usage |
|---|---|
| `/mem` | Capture libre — l'agent classe et range |
| `/mem-doc {fichier}` | Ingère un document local (PDF, DOCX, MD, image, ...) |
| `/mem-note`, `/mem-principle`, `/mem-goal`, `/mem-person` | Captures ciblées par type |

### Archeo de dépôt

| Commande | Effet |
|---|---|
| `/mem-archeo` | Archeo complète d'un dépôt Git (topologie + stack + historique) |
| `/mem-archeo --branch-first {branche}` | Focus sur une branche feature, avec analyse du périmètre fonctionnel |
| `/mem-archeo-atlassian {url}` | Archeo de pages Confluence + tickets Jira liés |

### Gestion du vault

| Commande | Effet |
|---|---|
| `/mem-list` | Lister projets et domaines |
| `/mem-search {requête}` | Recherche plein-texte |
| `/mem-digest {projet}` | Synthèse des dernières sessions |
| `/mem-rename`, `/mem-merge`, `/mem-reclass` | Réorganisation du vault |
| `/mem-health-scan`, `/mem-health-repair` | Audit + réparation automatique |
| `/mem-vault-migrate`, `/mem-relocate-project`, `/mem-archive-rewrite-paths` | Déplacement du vault / réindexation des chemins après une réorganisation disque |

Liste complète et options détaillées : voir [`docs/`](./docs/).

---

## Langues supportées

| Code | Langue |
|---|---|
| `en` | English (défaut) |
| `fr` | Français |
| `es` | Español |
| `de` | Deutsch |
| `ru` | Русский |

Choisie à l'installation, modifiable via `.\deploy.ps1 -Language fr` ou en éditant `~/.{cli}/memory-kit.json`. Ajout d'une langue : dupliquer le bloc `en:` de `core/i18n/strings.yaml`.

---

## Sous le capot

Pour ceux que ça intéresse : SecondBrain combine trois couches complémentaires.

- **Mode MCP** (recommandé) — un serveur `secondbrain-memory-kit` (Python, FastMCP) expose 40 outils que toute CLI compatible MCP appelle directement. Logique métier déterministe en Python, économe en tokens, testée (558 tests).
- **Mode skills fallback** — quand le serveur n'est pas démarré (ou pour les CLI sans MCP), les CLI exécutent les procédures Markdown originales. Comportement identique côté utilisateur.
- **App desktop SecondBrain Desktop** (optionnelle) — icône dans la zone de notification, runtime Python embarqué + wheels offline, assistant guidé, surveillance santé du vault, mise à jour confirm-then-run. Consomme l'engine en pur in-process, zéro subprocess MCP par action. Voir [`desktop-app/README.md`](./desktop-app/README.md).

Le pattern **MCP-first / skills-fallback** est transparent : l'agent décide à l'invocation, vous ne voyez aucune différence. L'app desktop est un complément consumer-friendly — l'engine fonctionne identiquement sans elle.

Documentation technique complète : [`docs/architecture/`](./docs/architecture/).

---

## Feuille de route

| Phase | État | Portée |
|---|---|---|
| **Phase 1** | ✅ Terminée | Multi-CLI individuel — Claude, Gemini, Codex, Vibe, Copilot, Antigravity (CLI + Desktop) |
| **Phase 3** | ✅ Terminée | Serveur MCP natif — 40 outils, 7 cibles auto-configurées |
| **Phase Desktop** | ✅ Windows livré, macOS en cours | Installateur self-contained + assistant guidé, runtime Python embarqué, surveillance vault, en-process kit, bootstrap engine fiable + PATH cross-OS, multi-user RDP, désinstallation propre, auto-update dual-canal (moteur + desktop), détection CLI étendue (npm globals + alt dirs), wiring MCP avec path absolu (immune au PATH cache RDP), i18n EN/FR/ES/DE/RU, vault scaffold complet (`sb-desktop-v0.10.5`) |
| **Phase 2** | À venir | Vault partagé en équipe, promotion `CollectiveBrain` |

---

## Désinstallation

- **Installé via le `.exe` Windows** — Panneau de configuration → Programmes → SecondBrain Desktop → Désinstaller. L'uninstaller retire le binaire desktop, l'engine bundlé et le PATH ajouté.
- **Installé via le script source** — le serveur MCP s'enlève via `pipx uninstall memory-kit-mcp`. Les fichiers déployés dans `~/.{cli}/` se retirent à la main (chemins listés dans `docs/uninstall.md`).

Dans les deux cas, **le vault `memory/` n'est jamais touché** — vos archives, projets et domaines restent intacts.

---

## Licence et crédits

### Licence

Distribué sous **GNU AGPL v3.0 ou ultérieure** — © 2026 SI-GMT.

- **Usage libre** sur poste personnel ou en équipe interne.
- **Modification autorisée** — adaptez à vos besoins.
- **Redistribution + dérivés** restent sous AGPL — partage des modifications obligatoire.
- **Clause SaaS AGPL** : héberger SecondBrain en service tiers oblige à publier les modifications de votre instance.

Choix volontaire : protéger l'innovation contre l'appropriation commerciale fermée, sans entraver les usages individuels, internes ou open source.

Les versions antérieures publiées sous MIT (v0.1.0 → v0.9.1) restent légalement disponibles sous MIT pour quiconque les avait téléchargées.

### Concept original — Raphaël Fages / Fractality Studio

SecondBrain est l'adaptation d'un concept proposé par **Raphaël Fages** au sein de [Fractality Studio](https://fractality.studio/) : structurer la mémoire d'un agent LLM comme un *second cerveau* personnel, avec un cycle de prise de notes et de relecture analogue à un rythme veille-sommeil.

Principes fondateurs hérités de ce travail initial :

- Une couche de fichiers Markdown lus et écrits par l'agent suffit à briser l'amnésie inter-sessions, sans infrastructure serveur.
- Le triptyque **archive immuable / contexte mutable / historique chronologique** permet à la fois la traçabilité et la reprise rapide.
- Le déclenchement par langage naturel rend le cycle ergonomique pour l'utilisateur final.

L'implémentation présente dans ce dépôt étend ces principes avec : support multi-CLI, vault Obsidian, procédures factorisées en source unique de vérité, déploiement PowerShell + bash, refonte brain-centric (v0.5), schéma anglais + i18n conversationnel (v0.5.2), serveur MCP natif (v0.8.0+).

### Double nommage

- **SecondBrain** — nom de la distribution, du dépôt GitHub et de la documentation utilisateur.
- **memory-kit** — nom technique des artefacts internes (`memory-kit.json`, extension Gemini, serveur MCP `secondbrain-memory-kit`).
