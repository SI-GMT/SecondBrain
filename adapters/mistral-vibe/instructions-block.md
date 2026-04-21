<!-- MEMORY-KIT:START -->
## Kit Mémoire — Second cerveau persistant

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Mistral Vibe. Suivre les règles ci-dessous sans que l'utilisateur ait besoin de les rappeler.

**Vault** (chemin absolu) : `{{VAULT_PATH}}`

### Structure du vault

- `{{VAULT_PATH}}/_index.md` — catalogue des projets et archives.
- `{{VAULT_PATH}}/archives/YYYY-MM-DD-HHhMM-{projet}-{résumé}.md` — archives immuables (une par session complète).
- `{{VAULT_PATH}}/projets/{nom}/contexte.md` — snapshot mutable du projet (toujours à jour, voie rapide).
- `{{VAULT_PATH}}/projets/{nom}/historique.md` — fil chronologique des sessions du projet.

### Déclenchement automatique du chargement (recall)

Dès que l'utilisateur exprime en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était », « on reprend le projet X », « on s'y remet ».
- Un besoin de mémoire : « tu te rappelles de… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi ».

→ Exécuter automatiquement, sans attendre une commande explicite :

1. **Identifier le projet** dans cet ordre : argument utilisateur explicite, sinon nom du dossier de travail courant s'il correspond à un projet listé dans `_index.md`, sinon lire `_index.md` et demander à l'utilisateur lequel charger.
2. **Charger le contexte** : lire `{{VAULT_PATH}}/projets/{nom}/contexte.md` en priorité (voie rapide, ~25 lignes). Si absent, lire la dernière archive référencée dans `historique.md`.
3. **Présenter un briefing** avec : phase actuelle, état (validé / en cours), décisions clés, prochaines étapes, assets disponibles.
4. **Proposer la suite** : « On reprend à l'étape X ? »

Si `_index.md` est absent ou vide : répondre « Mémoire initialisée — aucune session trouvée. Décris ton projet et on commence. »

### Mémoire vivante silencieuse (archive incrémental)

**Pendant** la session, dès qu'un fait, une décision ou une prochaine étape **importante** émerge ET n'est pas déjà dans le `contexte.md` du projet en cours :

- Mettre à jour **uniquement** `{{VAULT_PATH}}/projets/{nom}/contexte.md` — ajouter la ligne dans la section appropriée (Décisions cumulées, Prochaines étapes, Assets actifs).
- Ne **pas** créer de nouveau fichier dans `archives/`.
- Ne **pas** annoncer l'action à l'utilisateur (sauf s'il demande).

Justification : `contexte.md` est un snapshot mutable fait pour évoluer en continu ; `archives/` est réservé aux instantanés de fin de session.

### Archive complet en fin de session

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

### Règle absolue

Ne jamais créer de nouveau fichier dans `archives/` sans signal explicite de fin de session. Un archive complet = une session complète, pas une décision isolée.
<!-- MEMORY-KIT:END -->
