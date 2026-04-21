# SecondBrain

Mémoire persistante inter-sessions pour CLI LLM. Vault Markdown local, adapters natifs par plateforme, déclenchement automatique sur langage naturel.

> Basé sur le travail original de **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)) — voir [Crédits](#crédits).

## Aperçu

Claude Code, Gemini CLI, Codex et Mistral Vibe ne persistent pas le contexte entre sessions. `SecondBrain` déploie dans chaque CLI détectée un adapter natif qui lit et écrit un vault Markdown structuré — `/clear` cesse d'être une perte de contexte, et le langage naturel (« reprends », « on s'arrête ») déclenche chargement et archivage automatiquement.

Logique procédurale canonique dans `core/procedures/`, traduite en livrables plateforme-spécifiques par `deploy.ps1`.

## Plateformes supportées

| Plateforme     | Binaire  | Mécanisme d'auto-trigger                    | Statut                                    |
| -------------- | -------- | ------------------------------------------- | ----------------------------------------- |
| Claude Code    | `claude` | Skills (frontmatter `description` → auto)   | ✅ Validé                                 |
| Gemini CLI     | `gemini` | Extension + `GEMINI.md` (instructions)      | ✅ Validé                                 |
| Codex (OpenAI) | `codex`  | Skills `SKILL.md` + prompts fallback        | ⚠️ Partiel — format skills extrapolé      |
| Mistral Vibe   | `vibe`   | `~/.vibe/instructions.md`                   | ⚠️ Partiel — pas de slash commands natifs |

Détection : présence du binaire sur `$PATH` **ou** dossier de config utilisateur (`~/.{claude,gemini,codex,vibe}/`). Une plateforme absente est ignorée sans erreur ; aucune CLI trouvée entraîne un message informatif et une sortie propre.

## Rôle d'Obsidian

Le vault est un dossier de fichiers Markdown ordinaires. Les CLI LLM lisent et écrivent ces fichiers **directement** — il n'y a aucune API ni aucun serveur Obsidian dans la chaîne technique.

**Obsidian est l'interface humaine sur ce même dossier** : graphe des liens entre notes, backlinks automatiques, recherche transverse, édition rapide, daily notes, tags. Sans Obsidian, le kit continue d'écrire les archives et de maintenir `contexte.md`, mais la moitié de la valeur disparaît — un second cerveau qui ne peut pas être relu par le premier n'est qu'un tas de fichiers.

Pour cette raison, Obsidian est considéré comme **requis** à l'usage normal du kit. Gratuit, cross-platform, pas de compte à créer.

## Prérequis

- **PowerShell 7+** (`pwsh`) — exécute `deploy.ps1`. Installation : `winget install Microsoft.PowerShell` ou <https://github.com/PowerShell/PowerShell>.
- **Obsidian** — voir section précédente. Téléchargement : <https://obsidian.md>.
- **Au moins une CLI LLM** installée et initialisée (lancée au moins une fois pour que son dossier de config existe). Voir l'étape 2 ci-dessous.

## Installation

### 1. Installer Obsidian

Télécharger et installer depuis <https://obsidian.md>. Ne pas ouvrir de vault pour l'instant — on le fera à l'étape 5.

### 2. Installer au moins une CLI LLM

Une ou plusieurs — SecondBrain déploie dans toutes celles qu'il détecte :

| CLI             | Installation                           |
| --------------- | -------------------------------------- |
| Claude Code     | <https://claude.com/claude-code>       |
| Gemini CLI      | `npm install -g @google/gemini-cli`    |
| Codex (OpenAI)  | `npm install -g @openai/codex`         |
| Mistral Vibe    | <https://docs.mistral.ai/>             |

**Important** : lance chaque CLI au moins une fois après installation (`claude`, `gemini`, `codex`, `vibe`) pour que son dossier de config utilisateur (`~/.claude/`, `~/.gemini/`, `~/.codex/`, `~/.vibe/`) soit créé. Sans ça, `deploy.ps1` ignorera la CLI.

### 3. Cloner SecondBrain

```powershell
git clone https://github.com/SI-GMT/SecondBrain.git
cd SecondBrain
```

### 4. Déployer dans chaque CLI

```powershell
.\deploy.ps1
```

Le script détecte automatiquement les CLI présentes (binaire sur `$PATH` **ou** dossier de config présent) et déploie l'adapter pour chacune. Une CLI absente est ignorée sans erreur ; aucune CLI trouvée affiche un message et sort proprement.

Par défaut, le vault est créé à `SecondBrain/memory/`. Pour le placer ailleurs (partage réseau, synchro tierce, dossier de notes existant) :

```powershell
.\deploy.ps1 -VaultPath "D:\notes\cerveau"
```

### 5. Ouvrir le vault dans Obsidian

1. Lancer Obsidian.
2. **« Ouvrir un coffre »** → **« Ouvrir un dossier comme coffre »**.
3. Sélectionner le dossier `SecondBrain/memory/` (ou le chemin passé à `-VaultPath` à l'étape 4).
4. Obsidian crée son propre `.obsidian/` dans ce dossier à la première ouverture. Rien d'autre à configurer.

Le vault contient déjà un `_index.md` vide, prêt à être rempli au fil des archives.

### 6. Vérifier

Ouvrir une **nouvelle** session sur l'une des CLI déployées (ou redémarrer une session existante — les skills/prompts sont chargés au démarrage).

Depuis Claude Code, Gemini ou Codex, taper :

```
/recall
```

Depuis Mistral Vibe (pas de slash commands exposés au niveau user), simplement dire :

> reprends

Réponse attendue sur vault vierge, sur toutes les plateformes :

> Aucune session trouvée. Mémoire initialisée — memory/_index.md est prêt. Décris ce sur quoi tu travailles et on commence.

La mémoire est opérationnelle.

## Mise à jour

Après un `git pull` ou une modification locale (procédure, template d'adapter, frontmatter de skill) :

```powershell
.\deploy.ps1          # redéploie, préserve memory-kit.json existant
.\deploy.ps1 -Force   # idem, mais écrase memory-kit.json
```

Toutes les opérations sont idempotentes — redéployer ne duplique jamais d'entrée.

## Architecture

```
SecondBrain/
├── core/procedures/              # Spec canonique, agnostique plateforme
│   ├── archive.md                # Placeholder : {{CONFIG_FILE}}
│   └── recall.md
├── adapters/                     # Traducteurs plateforme (frontmatter + templating)
│   ├── claude-code/              # commands/, skills/*.template.md, claude-md-block.md
│   ├── gemini-cli/               # gemini-extension.json, GEMINI.md, commands/*.toml
│   ├── codex/                    # prompts/*.template.md, skills/{nom}/SKILL.md.template
│   └── mistral-vibe/             # instructions-block.md
├── memory/                       # Vault Obsidian (local, non versionné — voir .gitignore)
│   ├── _index.md                 # Catalogue
│   ├── archives/                 # Instantanés immuables (une archive = une session)
│   └── projets/{nom}/
│       ├── contexte.md           # Snapshot mutable (voie rapide, ~25 lignes)
│       └── historique.md         # Fil chronologique des sessions
└── deploy.ps1                    # Détection + assemblage + installation par plateforme
```

**Règle d'or** : toute logique procédurale vit dans `core/procedures/`. Les adapters n'ajoutent que du frontmatter et du formatage spécifique à leur plateforme. `deploy.ps1` compose à la volée via substitution de `{{PROCEDURE}}` et `{{CONFIG_FILE}}`. Jamais de duplication.

## Modèle de mémoire

Deux étages, coût token asymétrique :

| Fichier                                | Cardinalité   | Mutable | Lecture `recall` | ~Lignes  |
| -------------------------------------- | ------------- | ------- | ---------------- | -------- |
| `projets/{nom}/contexte.md`            | 1 par projet  | Oui     | **Priorité 1**   | ~25      |
| `archives/{YYYY-MM-DD-HHhMM}-*.md`     | 1 par session | Non     | Fallback         | ~70      |
| `projets/{nom}/historique.md`          | 1 par projet  | Append  | Index local      | N lignes |
| `_index.md`                            | 1 global      | Append  | Discovery        | N lignes |

`contexte.md` est la voie rapide : lu en premier par `recall`, coût token ~2× moindre qu'une archive. Mis à jour silencieusement dès qu'un fait important émerge durant la session, réécrit intégralement à chaque archive complet.

## Contrat de déclenchement

| Canal                        | Plateformes           | Déclencheur                                         | Action                               |
| ---------------------------- | --------------------- | --------------------------------------------------- | ------------------------------------ |
| Slash command explicite      | Claude, Gemini, Codex | `/recall [projet]`                                  | Mode complet recall                  |
| Slash command explicite      | Claude, Gemini, Codex | `/archive`                                          | Mode complet archive                 |
| Langage naturel — reprise    | Toutes                | « reprends », « on continue », « où on en était »   | Mode complet recall                  |
| Langage naturel — mémoire    | Toutes                | « tu te rappelles », « qu'est-ce qu'on a décidé »   | Mode complet recall                  |
| Langage naturel — fin        | Toutes                | « on s'arrête », « je pars », « on termine »        | Mode complet archive                 |
| Émergence (silencieux)       | Toutes                | Fait/décision important absent de `contexte.md`     | Mise à jour `contexte.md` uniquement |

Le mode silencieux ne crée **jamais** de fichier dans `archives/`. Invariant : une archive = une session complète.

## Ce que fait `deploy.ps1`

Par plateforme détectée :

- **Claude Code** — slash commands dans `~/.claude/commands/`, skills dans `~/.claude/skills/`, `memory-kit.json` + bloc MEMORY-KIT (markers délimités, idempotent) dans `~/.claude/CLAUDE.md`, vault ajouté à `permissions.additionalDirectories` dans `~/.claude/settings.json`.
- **Gemini CLI** — extension complète dans `~/.gemini/extensions/memory-kit/` (manifest, `GEMINI.md`, slash commands TOML), `memory-kit.json` + activation dans `extension-enablement.json`.
- **Codex** — slash commands dans `~/.codex/prompts/`, skills dans `~/.codex/skills/{nom}/SKILL.md`, `memory-kit.json`.
- **Mistral Vibe** — bloc MEMORY-KIT injecté dans `~/.vibe/instructions.md` (markers délimités, idempotent).

Toutes les opérations sont **idempotentes**. Le détecteur respecte `$env:CLAUDE_CONFIG_DIR` si défini.

## Développement du kit

Source unique de vérité : `core/procedures/*.md`. Les champs `description` des skills / prompts (dans les adapters) contrôlent l'auto-découverte et la sélection LLM — itérer là pour affiner le ciblage.

Workflow :

1. Éditer `core/procedures/{archive,recall}.md` (logique) ou le frontmatter d'un adapter (trigger).
2. `.\deploy.ps1` pour redéployer.
3. Redémarrer la session CLI cible (skills/prompts sont chargés au démarrage).

## Ajouter un adapter

Créer `adapters/{plateforme}/` suivant la structure native de la cible. Ajouter une entrée dans `$platforms` de `deploy.ps1` et implémenter `Deploy-{Plateforme}` selon le contrat :

1. Créer les sous-dossiers cibles dans `$ConfigDir`.
2. Assembler template + `core/procedures/{nom}.md` via substitution de `{{PROCEDURE}}` et `{{CONFIG_FILE}}`.
3. Écrire `{ConfigDir}/memory-kit.json` avec `{"vault": "<absolu>"}` (sauf pour Vibe : substitution directe dans le bloc instructions).
4. Injecter un bloc `<!-- MEMORY-KIT:START --> … <!-- MEMORY-KIT:END -->` dans le fichier de contexte de la plateforme, si applicable.

Ne jamais forker `core/`. Si une divergence plateforme apparaît, ajouter un paramètre ou un placeholder dans la spec canonique.

## Limitations connues

- **Codex — skills user-level** : le format `~/.codex/skills/{nom}/SKILL.md` est extrapolé du format des skills plugin observé sur une install réelle. Si Codex n'auto-découvre pas les skills user-level, les slash commands dans `~/.codex/prompts/` servent de fallback, mais l'auto-trigger sur langage naturel n'opère pas. Test terrain requis.
- **Mistral Vibe — pas de slash commands** côté user. Tout passe par `~/.vibe/instructions.md` + tool use. Requiert que Vibe ait accès à des outils de fichier (MCP ou natif) pour lire/écrire le vault.
- **Multi-postes** : le chemin absolu du vault est local à chaque poste. Aucune synchro incluse — pointer chaque poste vers un partage réseau ou utiliser un sync tiers (Obsidian Sync, Syncthing, git, etc.) est à la charge de l'utilisateur.
- **Cosmétique JSON** : `deploy.ps1` round-trip `~/.claude/settings.json` et `extension-enablement.json` via `ConvertFrom-Json` / `ConvertTo-Json` — l'indentation et l'ordre des clés peuvent changer au premier passage. Sans effet fonctionnel.

## Feuille de route

| Phase | État       | Scope                                                                          |
| ----- | ---------- | ------------------------------------------------------------------------------ |
| 1     | ✅ Livré   | Détection multi-CLI + adapters Claude, Gemini, Codex, Vibe sur un poste unique |
| 2     | À faire    | Déploiement équipe standardisé ; vault partagé sur infra locale                |
| 3     | Prospectif | Serveur MCP `memory-kit` — adapters deviennent des shims, provider-agnostic    |

## Désinstallation

```powershell
Remove-Item "$HOME\.claude\commands\archive.md","$HOME\.claude\commands\recall.md","$HOME\.claude\skills\archive.md","$HOME\.claude\skills\recall.md","$HOME\.claude\memory-kit.json" -Force
Remove-Item "$HOME\.gemini\extensions\memory-kit" -Recurse -Force
Remove-Item "$HOME\.codex\prompts\archive.md","$HOME\.codex\prompts\recall.md","$HOME\.codex\memory-kit.json" -Force
Remove-Item "$HOME\.codex\skills\archive","$HOME\.codex\skills\recall" -Recurse -Force
```

Retirer à la main le bloc `<!-- MEMORY-KIT:START --> … <!-- MEMORY-KIT:END -->` dans `~/.claude/CLAUDE.md` et `~/.vibe/instructions.md`. Retirer l'entrée vault de `permissions.additionalDirectories` dans `~/.claude/settings.json`. Le vault lui-même est conservé — les archives restent.

## Crédits

Le cycle d'archivage/recall, la séparation snapshot mutable (`contexte.md`) / instantané immuable (`archives/`), et le rituel `/clear` comme « sommeil propre » sont conçus par **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)).

Ressources de Raphaël :

- Agence : <https://fractality.studio/>
- Communauté Skool : <https://www.skool.com/ica-9283>
- YouTube : <https://www.youtube.com/@raphfages>

Ce dépôt étend le concept original avec une architecture `core/` + `adapters/` pour déployer le kit sur plusieurs CLI LLM (Claude Code, Gemini CLI, Codex, Mistral Vibe) depuis un seul script de déploiement.

## Licence

MIT — voir [LICENSE](LICENSE). Utilisez, modifiez, redistribuez. Attribution minimale (conserver la notice de copyright), aucune garantie, aucune restriction.
