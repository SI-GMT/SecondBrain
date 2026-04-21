# memory-kit

Mémoire persistante inter-sessions pour CLI LLM. Vault Markdown local, adapters natifs par plateforme, déclenchement automatique sur langage naturel.

> Basé sur le travail original de **Raphaël Fages** ([Fractality Studio](https://fractality.studio/)) — voir [Crédits](#crédits).

## Aperçu

Claude Code, Gemini CLI, Codex et Mistral Vibe ne persistent pas le contexte entre sessions. `memory-kit` déploie dans chaque CLI détectée un adapter natif qui lit et écrit un vault Markdown structuré — `/clear` cesse d'être une perte de contexte, et le langage naturel (« reprends », « on s'arrête ») déclenche chargement et archivage automatiquement.

Logique procédurale canonique dans `core/procedures/`, traduite en livrables plateforme-spécifiques par `deploy.ps1`.

## Plateformes supportées

| Plateforme     | Binaire  | Mécanisme d'auto-trigger                    | Statut                                    |
| -------------- | -------- | ------------------------------------------- | ----------------------------------------- |
| Claude Code    | `claude` | Skills (frontmatter `description` → auto)   | ✅ Validé                                 |
| Gemini CLI     | `gemini` | Extension + `GEMINI.md` (instructions)      | ✅ Validé                                 |
| Codex (OpenAI) | `codex`  | Skills `SKILL.md` + prompts fallback        | ⚠️ Partiel — format skills extrapolé      |
| Mistral Vibe   | `vibe`   | `~/.vibe/instructions.md`                   | ⚠️ Partiel — pas de slash commands natifs |

Détection : présence du binaire sur `$PATH` **ou** dossier de config utilisateur (`~/.{claude,gemini,codex,vibe}/`). Une plateforme absente est ignorée sans erreur ; aucune CLI trouvée entraîne un message informatif et une sortie propre.

## Prérequis

- **PowerShell 7+** (`pwsh`) pour `deploy.ps1`.
- Au moins une CLI LLM initialisée (dossier de config créé par la CLI à son premier lancement).
- Obsidian (optionnel) pour visualiser le vault comme graphe.

## Installation

```powershell
git clone <repo> C:\path\to\memory-kit
cd C:\path\to\memory-kit
.\deploy.ps1
```

Vault ailleurs que dans le dépôt :

```powershell
.\deploy.ps1 -VaultPath "D:\notes\cerveau"
```

Redéploiement après édition d'un template ou d'une procédure :

```powershell
.\deploy.ps1 -Force   # réécrit memory-kit.json
```

Test depuis une nouvelle session Claude Code :

```
/recall
```

Réponse attendue sur vault vierge :

> Aucune session trouvée. Mémoire initialisée — memory/_index.md est prêt. Décris ce sur quoi tu travailles et on commence.

## Architecture

```
memory-kit/
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
