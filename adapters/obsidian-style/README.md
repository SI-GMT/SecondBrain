# Obsidian Style Adapter (v0.7.2)

Configurations Obsidian canoniques **opinionées** pour un vault SecondBrain. Optionnelles — le kit fonctionne sans, mais ces configs rendent la vue graph plus lisible et exploitent le champ `display` du frontmatter universel via le plugin **Front Matter Title**.

## Ce que ça fait

Le bridge `Deploy-ObsidianStyle` (intégré dans `deploy.ps1` / `deploy.sh`) copie les fichiers de ce dossier vers `{vault}/.obsidian/` avec backup horodaté avant écrasement. Idempotent.

Fichiers livrés :

- **`graph.json`** — palette de couleurs des 9 zones racine appliquée à la vue graph. Le bloc `colorGroups` mappe `tag:#zone/episodes`, `tag:#zone/knowledge`, etc. à des couleurs distinctes pour rendre la topologie du vault immédiatement lisible.

Ce qui **n'est pas** livré (intentionnellement) :

- `community-plugins.json` — installer manuellement les plugins recommandés via Settings → Community plugins. La liste à jour est plus bas dans ce README.
- `core-plugins.json` — préférences personnelles, pas opinion du kit.
- `app.json`, `appearance.json`, `workspace.json` — état UI utilisateur, jamais écrasé.
- Les configs propriétaires des plugins community (`plugins/{plugin-id}/data.json`) — chaque plugin a son schéma propre, on ne les touche pas.

## Plugins community recommandés

Manuel via **Settings → Community plugins → Browse**, puis activer dans **Installed plugins** :

| Plugin | Pourquoi |
|---|---|
| **Front Matter Title** (par snezhig) | Lit le champ `display` du frontmatter et l'utilise comme label dans le graph view, le file explorer et les wikilinks. Sans lui, les nœuds homonymes (`context.md`, `history.md` répétés par projet) sont indistinguables dans le graph. **Le plus important** pour SecondBrain. |
| **Extended Graph** (optionnel) | Permet de pondérer les nœuds, masquer des sous-graphes, exporter le graph. Confort. |
| **Tag Wrangler** (optionnel) | Renomme un tag dans tout le vault. Utile pour les opérations de réorganisation manuelles. |

Après installation de Front Matter Title, ouvrir ses paramètres et ajouter `display` à la liste des champs lus (ou laisser le défaut si déjà présent). Aucune autre config requise — le plugin lit juste le frontmatter et substitue.

## Comportement du bridge `Deploy-ObsidianStyle`

À l'exécution de `deploy.ps1` / `deploy.sh` (ou via `--obsidian-style` explicite si on rend le bridge opt-in plus tard) :

1. **Détection Obsidian ouvert** : si un processus `Obsidian` tourne OU si le lock file `{vault}/.obsidian/workspace.json` a été modifié dans les dernières 60 secondes → **abort** avec message clair (Obsidian doit être fermé pour patcher le graph). L'utilisateur peut passer `--force-obsidian-style` pour bypass.
2. **Pour chaque fichier de cet adapter** :
   - Si la cible n'existe pas → écrire la version canonique.
   - Si la cible existe et son contenu est identique à la version canonique → skip silencieux.
   - Si la cible existe et son contenu diffère → backup `{cible}.bak-pre-style-{YYYY-MM-DD-HHmmss}` puis écrire la version canonique.
3. **Marker `_secondbrain_canonical`** : chaque fichier de cet adapter porte la clé `_secondbrain_canonical: "v0.7.2"` à la racine de son JSON. Permet de détecter au prochain déploiement si le fichier vault est encore une version canonique kit (à mettre à jour) ou une version personnalisée (à backup).

## Ajuster les couleurs du graph

Les valeurs RGB de `graph.json` sont des entiers décimaux (format Obsidian). Pour modifier, soit :

- Modifier directement `graph.json` puis re-deploy → applique la nouvelle palette.
- Modifier dans Obsidian via Graph view → Settings → Color groups → le fichier est sauvegardé avec un nouveau contenu, le marker `_secondbrain_canonical` disparaît, le prochain deploy backup avant d'écraser. Si tu veux **conserver** ta personnalisation, retire le marker manuellement et le deploy ne touchera plus à ce fichier (skip car content différent ET pas de marker = "user-customized").

## Convention `_secondbrain_canonical`

Présence du marker = "ce fichier est encore une version canonique du kit, je peux le mettre à jour à la prochaine release" (avec backup). Absence = "ce fichier a été personnalisé par l'utilisateur, je le laisse tranquille". Le bridge respecte cette convention pour ne pas écraser une personnalisation.
