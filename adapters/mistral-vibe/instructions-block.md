<!-- MEMORY-KIT:START -->
## Kit Mémoire — Second cerveau persistant

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Mistral Vibe. Suivre les règles ci-dessous sans que l'utilisateur ait besoin de les rappeler.

**Vault** (chemin absolu) : `{{VAULT_PATH}}`

### Structure du vault

- `{{VAULT_PATH}}/_index.md` — catalogue des projets et archives.
- `{{VAULT_PATH}}/archives/YYYY-MM-DD-HHhMM-{projet}-{résumé}.md` — archives de fin de session (une par session complète). Nom de fichier et contenu narratif immuables ; frontmatter (`projet:`, `tags:`) peut être mis à jour par les skills `mem-rename-project` et `mem-merge-projects`.
- `{{VAULT_PATH}}/projets/{nom}/contexte.md` — snapshot mutable du projet (toujours à jour, voie rapide).
- `{{VAULT_PATH}}/projets/{nom}/historique.md` — fil chronologique des sessions du projet.

### `mem-recall` — déclenchement automatique du chargement de contexte

Dès que l'utilisateur exprime en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était », « on reprend le projet X », « on s'y remet ».
- Un besoin de mémoire : « tu te rappelles de… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi ».

→ Exécuter automatiquement, sans attendre une commande explicite :

1. **Identifier le projet** dans cet ordre : argument utilisateur explicite, sinon nom du dossier de travail courant s'il correspond à un projet listé dans `_index.md`, sinon lire `_index.md` et demander à l'utilisateur lequel charger.
2. **Charger le contexte** : lire `{{VAULT_PATH}}/projets/{nom}/contexte.md` en priorité (voie rapide, ~25 lignes). Si absent, lire la dernière archive référencée dans `historique.md`.
3. **Présenter un briefing** avec : phase actuelle, état (validé / en cours), décisions clés, prochaines étapes, assets disponibles.
4. **Proposer la suite** : « On reprend à l'étape X ? »

Si `_index.md` est absent ou vide : répondre « Mémoire initialisée — aucune session trouvée. Décris ton projet et on commence. »

### `mem-archive` — mémoire vivante silencieuse (mode incrémental)

**Pendant** la session, dès qu'un fait, une décision ou une prochaine étape **importante** émerge ET n'est pas déjà dans le `contexte.md` du projet en cours :

- Mettre à jour **uniquement** `{{VAULT_PATH}}/projets/{nom}/contexte.md` — ajouter la ligne dans la section appropriée (Décisions cumulées, Prochaines étapes, Assets actifs).
- Ne **pas** créer de nouveau fichier dans `archives/`.
- Ne **pas** annoncer l'action à l'utilisateur (sauf s'il demande).

Justification : `contexte.md` est un snapshot mutable fait pour évoluer en continu ; `archives/` est réservé aux instantanés de fin de session.

### `mem-archive` — mode complet (fin de session)

Déclenché **uniquement** sur signal explicite : l'utilisateur dit « on s'arrête », « je pars », « on termine », ou demande explicitement d'archiver.

Exécuter alors la procédure complète :

1. **Créer** `{{VAULT_PATH}}/archives/YYYY-MM-DD-HHhMM-{projet}-{résumé-court}.md` avec le frontmatter YAML suivant :
   ```yaml
   ---
   date: YYYY-MM-DD
   heure: "HH:MM"
   projet: {nom}
   phase: {phase actuelle}
   tags: [projet/{nom}, type/archive]
   ---
   ```
   Puis le corps avec les sections : Résumé (2-3 phrases), Travail effectué, Décisions (avec raison), État du projet (phase / validé / en cours), Prochaines étapes, Fichiers modifiés (avec chemins), Assets (URLs ou « Aucun. »).

2. **Réécrire intégralement** `{{VAULT_PATH}}/projets/{nom}/contexte.md` avec l'état courant synthétisé (~25 lignes) : phase, validé, en cours, décisions cumulées, prochaines étapes, assets actifs.

3. **Ajouter une ligne** en fin de `{{VAULT_PATH}}/projets/{nom}/historique.md` pointant vers la nouvelle archive. Créer ce fichier s'il n'existe pas.

4. **Mettre à jour `{{VAULT_PATH}}/_index.md`** : ajouter une entrée dans la section « Archives » ; si c'est la première archive du projet, ajouter aussi « Projets ».

5. **Confirmer** à l'utilisateur : « Archive créée : {chemin}. Le /clear est safe — redis simplement "reprends" la prochaine fois. »

### Règle absolue (archive)

Ne jamais créer de nouveau fichier dans `archives/` sans signal explicite de fin de session. Un archive complet = une session complète, pas une décision isolée.

### Autres opérations `mem-*` — gestion du vault

Déclenchées sur intention exprimée en langage naturel :

- **`mem-list-projects`** — « liste mes projets », « quels projets j'ai en mémoire ? ». Lire `_index.md` (section Projets) + frontmatter de chaque `contexte.md`. Afficher un tableau : slug | label | phase | dernière session | nb de sessions. Trier par dernière session décroissante.

- **`mem-search {requête}`** — « cherche dans la mémoire X », « trouve les archives qui parlent de Y ». Rechercher récursivement dans `_index.md`, `archives/*.md`, `projets/**/*.md`. Exclure `.obsidian/`, `*.canvas`, `*.excalidraw.md`, `*.base`. Retourner les occurrences avec 2 lignes de contexte, groupées par fichier, triées archives récentes d'abord.

- **`mem-rename-project {ancien} {nouveau}`** — « renomme le projet X en Y ». Renommer de manière COMPLÈTE : aucune référence à l'ancien slug ni à l'ancien label ne doit subsister. Actions : (a) renommer le dossier `projets/{ancien}/` → `projets/{nouveau}/` ; (b) mettre à jour frontmatters + H1 + corps narratif de `contexte.md`, `historique.md` et de toutes les archives référencées ; (c) **renommer les fichiers archives** en remplaçant le slug dans leur nom (préserver l'horodatage) ; (d) mettre à jour `_index.md` (section Projets ET section Archives — labels + chemins) ; (e) nettoyer `.obsidian/workspace.json` des entrées stales. Si le nouveau label n'est pas fourni, le dériver du nouveau slug (tirets/underscores → espaces + capitalisation). Vérification finale : grep sur le vault pour confirmer zéro occurrence résiduelle. Refuser si le nouveau slug existe déjà (suggérer `mem-merge-projects`).

- **`mem-merge-projects {source} {cible}`** — « fusionne le projet X dans Y ». Retagger (frontmatter) les archives de la source au nom de la cible, concaténer `historique.md` (trié par horodatage), supprimer le dossier `projets/{source}/`, retirer la ligne de la section Projets de `_index.md`. Avertir l'utilisateur que `contexte.md` de la cible doit être fusionné manuellement (décision éditoriale).

- **`mem-digest {projet} [N=5]`** — « résume-moi les N dernières sessions de X », « fais un digest de X ». Lire les N dernières archives du projet, extraire Résumé / Décisions / Prochaines étapes de chacune, synthétiser en : arcs majeurs, décisions structurantes, dérive des prochaines étapes, état actuel. Lecture seule, n'écrit rien.

- **`mem-rollback-archive [projet]`** — « annule la dernière archive », « rollback l'archive de X ». Identifier la dernière archive (du projet si spécifié, sinon globale), afficher ce qui va être supprimé, puis supprimer le fichier + retirer la ligne de `historique.md` + retirer la ligne de `_index.md`. AVERTIR que `contexte.md` n'est PAS restauré (l'archive contenait elle-même le snapshot du moment) et suggérer `/mem-recall` pour régénérer un contexte à partir des archives restantes.

Pour toutes les opérations `mem-*` : exécuter directement, sans demander de confirmation supplémentaire. Les procédures intègrent déjà leurs propres vérifications et affichent un rapport clair après exécution.
<!-- MEMORY-KIT:END -->
