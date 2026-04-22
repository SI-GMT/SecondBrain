# Kit Mémoire — Second cerveau persistant (Gemini CLI)

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Gemini. Le chemin absolu du vault est dans `~/.gemini/memory-kit.json` sous la clé `vault`.

Plusieurs commandes `mem-*` sont disponibles. Elles doivent aussi être **déclenchées automatiquement** en fonction du langage naturel de l'utilisateur.

## `/mem-recall` — chargement du contexte

Invoquer cette logique **sans attendre que l'utilisateur tape `/mem-recall`** dès qu'il exprime, en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était », « on reprend le projet X », « on s'y remet ».
- Un besoin de consulter la mémoire : « tu te rappelles… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi ».

Si le projet visé est ambigu, demander confirmation avant d'exécuter.

## `/mem-archive` — sauvegarde

Deux modes distincts. **Ne jamais les confondre.**

**Mode incrémental silencieux** (pendant la session) — dès qu'un fait, une décision ou une prochaine étape importante émerge et n'est pas déjà dans le `contexte.md` du projet en cours, mettre à jour UNIQUEMENT `contexte.md`. Pas de nouveau fichier archive. Pas d'annonce à l'utilisateur. C'est le rôle de `contexte.md` : snapshot mutable, vivant.

**Mode archive complet** (fin de session) — déclenché par signal explicite : l'utilisateur dit « on s'arrête », « je pars », « on termine », tape `/clear` ou `/mem-archive`. Exécuter alors toute la procédure : fichier archive horodaté dans `archives/` + réécriture de `contexte.md` + mise à jour de `historique.md` + mise à jour de `_index.md`.

**Règle absolue** : ne jamais créer de nouveau fichier dans `archives/` en mode silencieux. Un archive complet = une session complète, pas une décision isolée.

## Autres commandes `mem-*` — gestion du vault

À déclencher sur intention exprimée en langage naturel :

- **`/mem-list-projects`** — « liste mes projets », « quels projets j'ai en mémoire ? ». Affiche un tableau des projets avec phase + dernière session + nb de sessions.
- **`/mem-search {requête}`** — « cherche dans la mémoire X », « trouve les archives qui parlent de Y ». Recherche plein-texte sur le vault.
- **`/mem-rename-project {ancien} {nouveau}`** — « renomme le projet X en Y ». Renomme le slug partout dans le vault (dossier, frontmatters, tags, index). Préserve les noms de fichiers et le contenu narratif des archives.
- **`/mem-merge-projects {source} {cible}`** — « fusionne le projet X dans Y ». Concatène les deux, retaggue les archives, supprime le dossier source. Le `contexte.md` de la cible est à fusionner manuellement.
- **`/mem-digest {projet} [N]`** — « résume-moi les N dernières sessions de X », « fais un digest de X ». Synthèse des arcs majeurs et décisions structurantes. Lecture seule.
- **`/mem-rollback-archive [projet]`** — « annule la dernière archive », « rollback l'archive de X ». Supprime la dernière archive + ses références ; n'auto-restaure pas `contexte.md`.

Pour toutes les opérations `mem-*` : exécuter directement, sans demander de confirmation supplémentaire à l'utilisateur. Les procédures intègrent déjà leurs vérifications et affichent un rapport après exécution.

## Encodage des fichiers du vault

Tous les fichiers écrits ou modifiés dans le vault (archives, `contexte.md`, `historique.md`, `_index.md`) doivent être en **UTF-8 sans BOM**, fins de ligne **LF**. Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ça corrompt les accents français et les caractères diacritiques (apparaît en `�` dans Obsidian). Les procédures détaillées précisent la commande exacte selon le shell/outil utilisé. Sur Windows, privilégier `pwsh` avec `Set-Content -Encoding utf8NoBOM` plutôt que Windows PowerShell 5.1 (qui ajoute un BOM avec `-Encoding UTF8`).
