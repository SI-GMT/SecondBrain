<!-- MEMORY-KIT:START -->
## Kit Mémoire — Second cerveau persistant

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Mistral Vibe. Les procédures détaillées vivent dans les skills `mem-*` auto-découverts depuis `~/.vibe/skills/`. Ce bloc fixe les règles globales qui encadrent leur exécution.

### ⚠ Règle d'or — Vault

**VAULT = `{{VAULT_PATH}}`**

- C'est un **chemin absolu, immuable, EXTERNE au répertoire courant de travail**.
- **NE JAMAIS** lister le cwd (`ls`, `pwd`, `dir`) pour « trouver » le vault. Il ne s'y trouve **pas**.
- **NE JAMAIS** supposer que le vault est dans le projet courant.
- **NE JAMAIS** demander confirmation du chemin à l'utilisateur — il est écrit ci-dessus, en dur, à l'installation.
- **TOUJOURS** attaquer directement avec ce chemin absolu, dès la première commande.
- Si un doute émerge en cours d'opération, relire cette règle et repartir du chemin absolu.

### Outil recommandé : shell système (chemin absolu)

Pour toute opération mémoire, utiliser l'outil shell système avec le **chemin absolu complet**. Les outils `read_file` / `write_file` peuvent être sandboxés sur le cwd et refuser un chemin absolu externe — le shell n'a pas cette limite.

**Choisir les commandes en fonction du shell disponible** (bash, PowerShell, cmd). Les équivalents pour les opérations courantes :

| Action | bash / macOS / Linux / git-bash | PowerShell / pwsh | cmd (Windows) |
|---|---|---|---|
| Lister un dossier | `ls "{{VAULT_PATH}}/archives/"` | `Get-ChildItem "{{VAULT_PATH}}/archives/"` | `dir "{{VAULT_PATH}}\archives\"` |
| Lire un fichier | `cat "{{VAULT_PATH}}/projets/X/contexte.md"` | `Get-Content "{{VAULT_PATH}}/projets/X/contexte.md"` | `type "{{VAULT_PATH}}\projets\X\contexte.md"` |
| Écrire un fichier | `cat > "…" <<'EOF' … EOF` | `Set-Content -Path "…" -Value …` | `echo …> "…"` (limité) |
| Rechercher récursif | `grep -rni "requête" "{{VAULT_PATH}}/"` | `Select-String -Path "{{VAULT_PATH}}/**/*.md" -Pattern "requête"` | `findstr /s /i "requête" "{{VAULT_PATH}}\*.md"` |
| Supprimer | `rm "{{VAULT_PATH}}/…"` | `Remove-Item "{{VAULT_PATH}}/…"` | `del "{{VAULT_PATH}}\…"` |
| Renommer / déplacer | `mv "…" "…"` | `Move-Item "…" "…"` | `move "…" "…"` |
| Modifier en place | `sed -i 's/ancien/nouveau/g' "…"` | `(Get-Content "…") -replace 'ancien','nouveau' \| Set-Content "…"` | — (pas d'équivalent direct) |

Si une commande échoue ("command not found", "n'est pas reconnu"), **essayer l'équivalent du shell natif de la plateforme** avant de considérer que l'opération est impossible. Sur Windows, si `bash`/`ls`/`cat` échouent, retomber directement sur PowerShell ou cmd — le vault est toujours accessible via un chemin absolu, peu importe le shell.

### Structure du vault

- `{{VAULT_PATH}}/_index.md` — catalogue des projets et archives.
- `{{VAULT_PATH}}/archives/YYYY-MM-DD-HHhMM-{projet}-{résumé}.md` — archives de fin de session, **immuables** (nom de fichier et corps narratif). Le frontmatter peut être modifié par les skills `mem-rename-project` et `mem-merge-projects`.
- `{{VAULT_PATH}}/projets/{nom}/contexte.md` — snapshot mutable du projet (toujours à jour, voie rapide).
- `{{VAULT_PATH}}/projets/{nom}/historique.md` — fil chronologique des sessions du projet.

### Skills disponibles

Les skills `mem-*` sont installés dans `~/.vibe/skills/` et sont **auto-découverts** par Vibe. Chaque skill porte sa procédure complète. Déclenchement automatique sur langage naturel :

| Skill | Intention naturelle |
|---|---|
| `mem-recall` | « reprends [projet] », « on continue », « tu te rappelles de… », « où on en était ? » |
| `mem-archive` | « on s'arrête », « je pars », « on termine », `/clear` (mode complet) — **mid-session** : mise à jour silencieuse de `contexte.md` dès qu'une décision ou fait important émerge |
| `mem-doc` | « ingère ce document », « archive ce fichier », « enregistre ce PDF dans ma mémoire », « absorbe ce document » |
| `mem-list-projects` | « liste mes projets », « quels projets j'ai en mémoire ? » |
| `mem-search` | « cherche [X] dans la mémoire », « trouve les archives qui parlent de Y » |
| `mem-digest` | « résume-moi les N dernières sessions de [projet] », « fil rouge de [projet] » |
| `mem-rename-project` | « renomme le projet [ancien] en [nouveau] » |
| `mem-merge-projects` | « fusionne [source] dans [cible] » |
| `mem-rollback-archive` | « annule la dernière archive », « rollback l'archive de [projet] » |

### Exemple canonique — première action attendue

Utilisateur : « reprends SecondBrain »
Toi, **immédiatement**, sans exploration préalable, selon ton shell :

```
# bash / macOS / Linux / git-bash
cat "{{VAULT_PATH}}/projets/secondbrain/contexte.md"

# PowerShell
Get-Content "{{VAULT_PATH}}/projets/secondbrain/contexte.md"

# cmd (Windows)
type "{{VAULT_PATH}}\projets\secondbrain\contexte.md"
```

**PAS** de `ls`/`dir`/`Get-ChildItem` du cwd, **PAS** de `pwd`, **PAS** de question à l'utilisateur. Le fichier existe ou n'existe pas ; dans les deux cas la lecture directe donne la réponse.

### Règles opérationnelles

- **Mode incrémental vs complet pour `mem-archive`** : mid-session, mettre à jour UNIQUEMENT `contexte.md` sans créer d'archive ni annoncer l'action. Ne créer un fichier dans `archives/` que sur signal explicite de fin de session.
- **Exécuter directement, sans demander confirmation supplémentaire**. Les skills intègrent leurs propres vérifications et affichent un rapport clair après exécution.
- **Pas d'exploration du cwd**. Pas de `pwd`, pas de `ls`/`dir`/`Get-ChildItem` du répertoire courant pour chercher le vault.
- **Tolérance aux shells**. Si une commande shell échoue parce qu'elle n'est pas reconnue (ex: `ls` sur Windows sans git-bash), **ne pas abandonner** — retomber immédiatement sur l'équivalent natif (`dir` pour cmd, `Get-ChildItem` pour PowerShell) en gardant le même chemin absolu.

### ⚙ Encodage des fichiers du vault

Tous les fichiers écrits ou modifiés dans le vault (archives, `contexte.md`, `historique.md`, `_index.md`) doivent être en **UTF-8 sans BOM**, fins de ligne **LF**. Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ça corrompt les accents français et les caractères diacritiques (apparaît en `�` dans Obsidian).

| Shell | Commande d'écriture UTF-8 sans BOM |
|---|---|
| bash / macOS / Linux / git-bash | `cat > "path" <<'EOF' … EOF` (natif UTF-8 sans BOM) |
| PowerShell 7+ (pwsh) | `Set-Content -Path "path" -Value $contenu -Encoding utf8NoBOM` |
| Windows PowerShell 5.1 | `[System.IO.File]::WriteAllText("path", $contenu, [System.Text.UTF8Encoding]::new($false))` |
| cmd.exe | **à éviter pour le Markdown accentué** — basculer sur PowerShell ou bash |

Si la commande d'écriture du shell disponible ajoute un BOM ou corrompt les accents, **rebasculer sur un shell compatible** plutôt que tenter de produire le fichier ainsi.
<!-- MEMORY-KIT:END -->
