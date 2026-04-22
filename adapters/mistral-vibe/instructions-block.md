<!-- MEMORY-KIT:START -->
## Kit Mémoire — Second cerveau persistant

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Mistral Vibe. Suivre les règles ci-dessous sans que l'utilisateur ait besoin de les rappeler.

### ⚠ Règle d'or — Vault

**VAULT = `{{VAULT_PATH}}`**

- C'est un **chemin absolu, immuable, EXTERNE au répertoire courant de travail**.
- **NE JAMAIS** lister le cwd (`ls`, `pwd`, `dir`) pour « trouver » le vault. Il ne s'y trouve **pas**.
- **NE JAMAIS** supposer que le vault est dans le projet courant.
- **NE JAMAIS** demander confirmation du chemin à l'utilisateur — il est écrit ci-dessus, en dur, à l'installation.
- **TOUJOURS** attaquer directement avec ce chemin absolu, dès la première commande.
- Si un doute émerge en cours d'opération, relire cette règle et repartir du chemin absolu.

### Outil recommandé : `bash`

Pour toute opération mémoire, utiliser **l'outil `bash`** avec le chemin absolu complet. C'est plus robuste que `read_file` / `write_file` — certains tools de lecture/écriture peuvent être sandboxés sur le cwd et refusent un chemin absolu externe. `bash` ne subit pas cette limite.

Cheat sheet des commandes :

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
- `{{VAULT_PATH}}/archives/YYYY-MM-DD-HHhMM-{projet}-{résumé}.md` — archives de fin de session, **immuables** (nom de fichier et corps narratif). Le frontmatter (`projet:`, `tags:`) peut être mis à jour par `mem-rename-project` et `mem-merge-projects`.
- `{{VAULT_PATH}}/projets/{nom}/contexte.md` — snapshot mutable du projet (toujours à jour, voie rapide).
- `{{VAULT_PATH}}/projets/{nom}/historique.md` — fil chronologique des sessions du projet.

---

### `mem-recall` — Charger le contexte d'un projet

**Déclenchement** : l'utilisateur dit « reprends [nom] », « on continue sur [nom] », « rappelle-moi le contexte de [nom] », « où on en était sur [nom] ? », ou tape `/mem-recall [nom]`.

**Exemple canonique — première action attendue** :

Utilisateur : « reprends SecondBrain »
Toi, **immédiatement**, sans exploration préalable :

```bash
cat "{{VAULT_PATH}}/projets/secondbrain/contexte.md"
```

**PAS** de `ls`, **PAS** de `pwd`, **PAS** de question à l'utilisateur. Le fichier existe ou n'existe pas ; dans les deux cas le `cat` donne la réponse directe.

**Étapes** :

1. Extraire le nom du projet (`[nom]`).
   - Si absent, lire le catalogue puis demander :
     ```bash
     cat "{{VAULT_PATH}}/_index.md"
     ```
2. Lire le contexte :
   ```bash
   cat "{{VAULT_PATH}}/projets/[nom]/contexte.md"
   ```
3. Si le fichier n'existe pas, fallback sur la dernière archive :
   ```bash
   cat "{{VAULT_PATH}}/projets/[nom]/historique.md"
   ```
   Extraire le chemin de la dernière archive listée puis :
   ```bash
   cat "{{VAULT_PATH}}/archives/LA-DERNIERE-ARCHIVE.md"
   ```
4. Présenter le briefing à l'utilisateur.

---

### `mem-archive` — Mémoire vivante silencieuse (mode incrémental)

**Pendant** la session, dès qu'un fait, une décision ou une prochaine étape **importante** émerge ET n'est pas déjà dans `contexte.md` du projet courant :

- Mettre à jour **uniquement** `{{VAULT_PATH}}/projets/{nom}/contexte.md` (ajout de la ligne dans la section appropriée).
- Ne **pas** créer de nouveau fichier dans `archives/`.
- Ne **pas** annoncer l'action à l'utilisateur (sauf s'il demande).

Commandes typiques :

```bash
# Lire l'état actuel
cat "{{VAULT_PATH}}/projets/[nom]/contexte.md"

# Réécrire le fichier avec la mise à jour
cat > "{{VAULT_PATH}}/projets/[nom]/contexte.md" <<'EOF'
[nouveau contenu complet]
EOF
```

Justification : `contexte.md` est un snapshot mutable fait pour évoluer en continu ; `archives/` est réservé aux instantanés de fin de session.

---

### `mem-archive` — Créer une archive (mode complet)

**Déclenchement** : l'utilisateur dit « on s'arrête », « je pars », « on termine », « archive la session » ou tape `/mem-archive`.

**Étapes** :

1. Construire le nom de fichier : `AAAA-MM-JJ-HHhMM-[projet]-[résumé].md` (date/heure actuelles).
2. Écrire l'archive :
   ```bash
   cat > "{{VAULT_PATH}}/archives/AAAA-MM-JJ-HHhMM-[projet]-[résumé].md" <<'EOF'
   ---
   date: [AAAA-MM-JJ]
   heure: "[HH:MM]"
   projet: [nom]
   phase: [phase actuelle]
   tags: [projet/[nom], type/archive]
   ---

   # Session [date] — [projet] — [résumé]

   ## Résumé
   [2-3 phrases]

   ## Travail effectué
   - [liste]

   ## Décisions
   - [décision] — [raison]

   ## État du projet
   - Phase : [phase]
   - Validé : [liste]
   - En cours : [liste]
   - Partiels : [liste]

   ## Prochaines étapes
   1. [étape]

   ## Fichiers modifiés
   - [chemin]

   ## Assets (URLs)
   - [url ou « Aucun. »]
   EOF
   ```
3. Réécrire `{{VAULT_PATH}}/projets/[nom]/contexte.md` avec une version synthétique (~25 lignes) qui reflète le nouvel état.
4. Ajouter une ligne à `{{VAULT_PATH}}/projets/[nom]/historique.md` :
   ```bash
   echo "- [AAAA-MM-JJ HHhMM — [résumé]](../../archives/AAAA-MM-JJ-HHhMM-[projet]-[résumé].md)" >> "{{VAULT_PATH}}/projets/[nom]/historique.md"
   ```
5. Ajouter une ligne à la section Archives de `{{VAULT_PATH}}/_index.md` (par `sed -i` ou réécriture).
6. Confirmer à l'utilisateur : « Archive créée. Le `/clear` est safe — redis simplement "reprends" la prochaine fois. »

**Règle absolue** : ne jamais créer de nouveau fichier dans `archives/` sans signal explicite de fin de session. Un archive = une session complète.

---

### `mem-list-projects` — Lister les projets du vault

**Déclenchement** : « liste mes projets », « quels projets j'ai en mémoire ? », `/mem-list-projects`.

**Étapes** :

1. Lire l'index :
   ```bash
   cat "{{VAULT_PATH}}/_index.md"
   ```
2. Pour chaque projet listé, lire son `contexte.md` pour extraire `phase` et `derniere-session` du frontmatter :
   ```bash
   cat "{{VAULT_PATH}}/projets/[nom]/contexte.md" | head -20
   ```
3. Compter les archives par projet :
   ```bash
   ls "{{VAULT_PATH}}/archives/" | grep -c "[nom]"
   ```
4. Afficher un tableau : Projet | Phase | Dernière session | Nombre d'archives.

---

### `mem-search` — Rechercher dans le vault

**Déclenchement** : « cherche [requête] dans la mémoire », « trouve les archives qui parlent de [requête] », `/mem-search [requête]`.

**Étapes** :

1. Recherche plein-texte :
   ```bash
   grep -rni --include="*.md" "[requête]" "{{VAULT_PATH}}/"
   ```
2. Grouper par fichier, archives récentes en premier.
3. Afficher avec 2 lignes de contexte avant/après chaque match :
   ```bash
   grep -rni -C 2 --include="*.md" "[requête]" "{{VAULT_PATH}}/"
   ```

---

### `mem-rename-project` — Renommer un projet

**Déclenchement** : « renomme le projet [ancien] en [nouveau] », `/mem-rename-project [ancien] [nouveau]`.

**Étapes** :

1. Renommer le dossier projet :
   ```bash
   mv "{{VAULT_PATH}}/projets/[ancien]" "{{VAULT_PATH}}/projets/[nouveau]"
   ```
2. Mettre à jour le contenu de `contexte.md` et `historique.md` (frontmatter, H1, corps) :
   ```bash
   sed -i "s/[ancien]/[nouveau]/g" "{{VAULT_PATH}}/projets/[nouveau]/contexte.md"
   sed -i "s/[ancien]/[nouveau]/g" "{{VAULT_PATH}}/projets/[nouveau]/historique.md"
   ```
3. Renommer les fichiers d'archives référençant l'ancien slug :
   ```bash
   for f in "{{VAULT_PATH}}/archives/"*[ancien]*; do
     mv "$f" "${f//[ancien]/[nouveau]}"
   done
   ```
4. Mettre à jour le contenu des archives (frontmatter, H1, corps narratif) :
   ```bash
   sed -i "s/[ancien]/[nouveau]/g" "{{VAULT_PATH}}/archives/"*[nouveau]*
   ```
5. Mettre à jour `{{VAULT_PATH}}/_index.md` (lignes Projets + Archives).
6. Vérification finale :
   ```bash
   grep -rni "[ancien]" "{{VAULT_PATH}}/"
   ```
   Attendu : 0 résultat.

---

### `mem-merge-projects` — Fusionner deux projets

**Déclenchement** : « fusionne [source] dans [cible] », `/mem-merge-projects [source] [cible]`.

**Étapes** :

1. Extraire les archives de la source :
   ```bash
   cat "{{VAULT_PATH}}/projets/[source]/historique.md"
   ```
2. Retagger chaque archive de la source (frontmatter `projet:` et `tags:`) :
   ```bash
   sed -i "s/^projet: [source]$/projet: [cible]/" "{{VAULT_PATH}}/archives/"*[source]*
   sed -i "s|projet/[source]|projet/[cible]|g" "{{VAULT_PATH}}/archives/"*[source]*
   ```
3. Fusionner l'historique (concaténer + trier par horodatage décroissant) dans `{{VAULT_PATH}}/projets/[cible]/historique.md`.
4. Supprimer le dossier source :
   ```bash
   rm -rf "{{VAULT_PATH}}/projets/[source]"
   ```
5. Retirer la ligne `[source]` de la section Projets de `{{VAULT_PATH}}/_index.md`.
6. **Ne pas** toucher à `contexte.md` de la cible — fusion sémantique manuelle par l'utilisateur. Le signaler dans le rapport.

---

### `mem-digest` — Synthétiser les N dernières sessions

**Déclenchement** : « résume-moi les [N] dernières sessions de [projet] », « digest de [projet] », `/mem-digest [projet] [N]`.

**Étapes (lecture seule)** :

1. Lire l'historique :
   ```bash
   cat "{{VAULT_PATH}}/projets/[projet]/historique.md"
   ```
2. Prendre les N lignes les plus récentes (N=5 par défaut).
3. Lire chaque archive référencée :
   ```bash
   cat "{{VAULT_PATH}}/archives/[archive].md"
   ```
4. Extraire les sections Résumé, Décisions, Prochaines étapes.
5. Synthétiser : arcs majeurs, décisions structurantes, dérive des prochaines étapes (annoncé vs réalisé), état actuel.
6. Si N > nombre d'archives disponibles, prendre tout et le signaler dans le rapport.

---

### `mem-rollback-archive` — Annuler la dernière archive

**Déclenchement** : « annule la dernière archive », « rollback l'archive de [projet] », `/mem-rollback-archive [projet]`.

**Étapes** :

1. Identifier l'archive cible :
   - Avec `[projet]` : prendre la dernière ligne de `{{VAULT_PATH}}/projets/[projet]/historique.md`.
   - Sans `[projet]` : archive la plus récente du vault global :
     ```bash
     ls -t "{{VAULT_PATH}}/archives/" | head -1
     ```
     Puis lire son frontmatter pour récupérer le projet.
2. Afficher ce qui va être supprimé (chemin, projet, date, résumé) **avant** de supprimer.
3. Supprimer l'archive :
   ```bash
   rm "{{VAULT_PATH}}/archives/[archive].md"
   ```
4. Retirer la ligne de l'historique :
   ```bash
   sed -i "\|[archive].md|d" "{{VAULT_PATH}}/projets/[projet]/historique.md"
   ```
5. Retirer la ligne de `{{VAULT_PATH}}/_index.md` (section Archives uniquement ; laisser le projet).
6. Avertir : « Archive supprimée. `contexte.md` n'a PAS été restauré — lance `mem-recall [projet]` pour régénérer un contexte à partir des archives restantes. »

---

### Rappel final — anti-drift

Pour **toute** opération `mem-*` :

1. Le vault est à **`{{VAULT_PATH}}`**, chemin absolu.
2. Utiliser **`bash`** avec ce chemin absolu, pas `read_file`.
3. **Pas d'exploration du cwd**. Pas de `pwd`, pas de `ls` du répertoire courant.
4. Exécuter directement, sans demander confirmation supplémentaire à l'utilisateur.
<!-- MEMORY-KIT:END -->
