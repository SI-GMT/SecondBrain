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

### Outil recommandé : `bash`

Pour toute opération mémoire, préférer **l'outil `bash`** avec le chemin absolu complet plutôt que `read_file` / `write_file` — ces derniers peuvent être sandboxés sur le cwd et refuser un chemin absolu externe.

| Action | Commande bash |
|---|---|
| Lire un fichier | `cat "{{VAULT_PATH}}/projets/X/contexte.md"` |
| Écrire un fichier | `cat > "{{VAULT_PATH}}/archives/NOM.md" <<'EOF' ... EOF` |
| Modifier en place | `sed -i 's/ancien/nouveau/g' "{{VAULT_PATH}}/..."` |
| Rechercher | `grep -rni "requête" "{{VAULT_PATH}}/"` |
| Lister un dossier | `ls "{{VAULT_PATH}}/archives/"` |
| Supprimer | `rm "{{VAULT_PATH}}/..."` |
| Renommer / déplacer | `mv "{{VAULT_PATH}}/..." "{{VAULT_PATH}}/..."` |

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
| `mem-list-projects` | « liste mes projets », « quels projets j'ai en mémoire ? » |
| `mem-search` | « cherche [X] dans la mémoire », « trouve les archives qui parlent de Y » |
| `mem-digest` | « résume-moi les N dernières sessions de [projet] », « fil rouge de [projet] » |
| `mem-rename-project` | « renomme le projet [ancien] en [nouveau] » |
| `mem-merge-projects` | « fusionne [source] dans [cible] » |
| `mem-rollback-archive` | « annule la dernière archive », « rollback l'archive de [projet] » |

### Exemple canonique — première action attendue

Utilisateur : « reprends SecondBrain »
Toi, **immédiatement**, sans exploration préalable :

```bash
cat "{{VAULT_PATH}}/projets/secondbrain/contexte.md"
```

**PAS** de `ls`, **PAS** de `pwd`, **PAS** de question à l'utilisateur. Le fichier existe ou n'existe pas ; dans les deux cas le `cat` donne la réponse directe.

### Règles opérationnelles

- **Mode incrémental vs complet pour `mem-archive`** : mid-session, mettre à jour UNIQUEMENT `contexte.md` sans créer d'archive ni annoncer l'action. Ne créer un fichier dans `archives/` que sur signal explicite de fin de session.
- **Exécuter directement, sans demander confirmation supplémentaire**. Les skills intègrent leurs propres vérifications et affichent un rapport clair après exécution.
- **Pas d'exploration du cwd**. Pas de `pwd`, pas de `ls` du répertoire courant pour chercher le vault.
<!-- MEMORY-KIT:END -->
