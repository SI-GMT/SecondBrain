<!-- MEMORY-KIT:START -->
## Kit Mémoire — Second cerveau persistant

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Claude Code. Le chemin absolu du vault est dans `~/.claude/memory-kit.json` (ou `$CLAUDE_CONFIG_DIR/memory-kit.json`) sous la clé `vault`.

Plusieurs skills `mem-*` sont installés. Ils doivent être utilisés de manière proactive — sans attendre une commande explicite — quand le langage naturel de l'utilisateur déclenche leur intention.

### `mem-recall` — chargement automatique du contexte

Invoquer ce skill **sans attendre que l'utilisateur tape `/mem-recall`** dès qu'il exprime, en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était », « on reprend le projet X », « on s'y remet ».
- Un besoin de consulter la mémoire : « tu te rappelles… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi ».

Si le projet visé est ambigu, demander confirmation avant d'exécuter. L'utilisateur peut aussi invoquer explicitement : `/mem-recall [projet]`.

### `mem-archive` — sauvegarde automatique

Ce skill fonctionne dans deux modes distincts. **Ne jamais les confondre.**

**Mode incrémental silencieux** (pendant la session) — dès qu'un fait, une décision ou une prochaine étape importante émerge et n'est pas déjà dans `contexte.md` du projet en cours, mettre à jour UNIQUEMENT `contexte.md`. Pas de nouveau fichier archive. Pas d'annonce à l'utilisateur. C'est le rôle de `contexte.md` : snapshot mutable, vivant.

**Mode archive complet** (fin de session) — déclenché par signal explicite : l'utilisateur dit « on s'arrête », « je pars », « on termine », tape `/clear` ou `/mem-archive`. Exécuter alors toute la procédure : fichier archive horodaté dans `archives/` + réécriture de `contexte.md` + mise à jour de `historique.md` + mise à jour de `_index.md`.

**Règle absolue** : ne jamais créer de nouveau fichier dans `archives/` en mode silencieux. Un archive complet = une session complète, pas une décision isolée.

### Autres skills `mem-*` — gestion du vault

À invoquer quand l'utilisateur exprime l'intention correspondante :

- `mem-doc` — « ingère ce document », « archive ce fichier », « enregistre ce PDF dans ma mémoire », « absorbe ce document », « indexe cette spec ». Ingère un document local (1 fichier par invocation). Résolution auto du projet cible (priorité : `--projet` → match chemin → match CWD → `inbox`).
- `mem-list-projects` — « liste mes projets », « quels projets j'ai en mémoire ? », « montre-moi tous les projets ».
- `mem-search` — « cherche dans la mémoire X », « trouve les archives qui parlent de Y », « où avait-on parlé de Z ? ».
- `mem-rename-project` — « renomme le projet X en Y », « change le slug de X ».
- `mem-merge-projects` — « fusionne le projet X dans Y », « regroupe X et Y sous Y ».
- `mem-digest` — « résume-moi les N dernières sessions de X », « fais un digest de X », « donne-moi le fil rouge de X ».
- `mem-rollback-archive` — « annule la dernière archive », « oublie la dernière session », « rollback l'archive de X ».

Pour toutes les opérations `mem-*` : exécuter directement, sans demander de confirmation supplémentaire à l'utilisateur. Les procédures intègrent déjà leurs propres vérifications (existence des fichiers, conflits de slug, etc.) et affichent un rapport clair après exécution.

### Encodage des fichiers du vault

Tous les fichiers écrits ou modifiés dans le vault (archives, `contexte.md`, `historique.md`, `_index.md`) doivent être en **UTF-8 sans BOM**, fins de ligne **LF**. Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ça corrompt les accents français et les caractères diacritiques (apparaît en `�` dans Obsidian). Les procédures détaillées précisent la commande exacte selon le shell/outil utilisé.
<!-- MEMORY-KIT:END -->
