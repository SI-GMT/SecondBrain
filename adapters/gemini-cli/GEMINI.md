# Kit Mémoire — Second cerveau persistant (Gemini CLI)

Ce poste dispose d'un vault mémoire qui persiste le contexte entre les sessions Gemini. Le chemin absolu du vault est dans `~/.gemini/memory-kit.json` sous la clé `vault`.

Deux commandes sont disponibles et doivent aussi être **déclenchées automatiquement** en fonction du langage naturel de l'utilisateur.

## `/recall` — chargement du contexte

Invoquer cette logique **sans attendre que l'utilisateur tape `/recall`** dès qu'il exprime, en langage naturel :

- Une intention de reprise : « reprends », « on continue », « où on en était », « on reprend le projet X », « on s'y remet ».
- Un besoin de consulter la mémoire : « tu te rappelles… », « qu'est-ce qu'on a décidé pour… », « on avait fait quoi déjà ? », « rappelle-moi ».

Si le projet visé est ambigu, demander confirmation avant d'exécuter.

## `/archive` — sauvegarde

Deux modes distincts. **Ne jamais les confondre.**

**Mode incrémental silencieux** (pendant la session) — dès qu'un fait, une décision ou une prochaine étape importante émerge et n'est pas déjà dans le `contexte.md` du projet en cours, mettre à jour UNIQUEMENT `contexte.md`. Pas de nouveau fichier archive. Pas d'annonce à l'utilisateur. C'est le rôle de `contexte.md` : snapshot mutable, vivant.

**Mode archive complet** (fin de session) — déclenché par signal explicite : l'utilisateur dit « on s'arrête », « je pars », « on termine », tape `/clear` ou `/archive`. Exécuter alors toute la procédure : fichier archive horodaté dans `archives/` + réécriture de `contexte.md` + mise à jour de `historique.md` + mise à jour de `_index.md`.

**Règle absolue** : ne jamais créer de nouveau fichier dans `archives/` en mode silencieux. Un archive complet = une session complète, pas une décision isolée.
