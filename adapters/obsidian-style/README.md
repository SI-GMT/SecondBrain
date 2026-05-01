# Obsidian Style Adapter (v0.7.3)

Configurations Obsidian canoniques **opinionées** pour un vault SecondBrain. Optionnelles — le kit fonctionne sans, mais ces configs rendent la vue graph plus lisible et exploitent le champ `display` du frontmatter universel via le plugin **Front Matter Title**.

## Ce que ça fait

Le bridge `Deploy-ObsidianStyle` (intégré dans `deploy.ps1` / `deploy.sh`) copie les fichiers de ce dossier vers `{vault}/.obsidian/` **en miroir de l'arborescence** (sous-dossiers inclus depuis v0.7.3) avec backup horodaté avant écrasement. Idempotent.

Fichiers livrés :

- **`graph.json`** — palette de couleurs des 9 zones racine appliquée à la vue graph. Le bloc `colorGroups` mappe `tag:#zone/episodes`, `tag:#zone/knowledge`, etc. à des couleurs distinctes pour rendre la topologie du vault immédiatement lisible.
- **`plugins/obsidian-front-matter-title-plugin/data.json`** _(v0.7.3)_ — config du plugin **Front Matter Title** réglée pour lire le champ `display` du frontmatter universel (clé `templates.common.main: "display"`, fallback `title`). Active les substitutions sur **graph view**, **file explorer**, **tabs** et **backlinks panel**. Sans ce fichier, le plugin par défaut cherche `title` (qui n'existe pas dans le schéma SecondBrain) et tombe systématiquement sur le filename — d'où des nœuds graph "history"/"context" homonymes indistinguables.

Ce qui **n'est pas** livré (intentionnellement) :

- `community-plugins.json` — installer manuellement les plugins recommandés via Settings → Community plugins. La liste à jour est plus bas dans ce README.
- `core-plugins.json` — préférences personnelles, pas opinion du kit.
- `app.json`, `appearance.json`, `workspace.json` — état UI utilisateur, jamais écrasé.
- Les configs propriétaires des autres plugins community (`plugins/{plugin-id}/data.json`) — chaque plugin a son schéma propre, on ne touche que celui dont la config est structurellement requise pour le fonctionnement de SecondBrain (Front Matter Title).

## Plugins community recommandés

Manuel via **Settings → Community plugins → Browse**, puis activer dans **Installed plugins** :

| Plugin | Pourquoi |
|---|---|
| **Front Matter Title** (par snezhig) | **Indispensable.** Lit le champ `display` du frontmatter et l'utilise comme label dans le graph view, le file explorer, les tabs et le backlinks panel. Sans lui, les nœuds homonymes (`context.md`, `history.md` répétés par projet) sont indistinguables dans le graph. La config canonique livrée par cet adapter (`plugins/obsidian-front-matter-title-plugin/data.json`) suffit — pas de réglage manuel à faire après installation. |
| **Extended Graph** (optionnel) | Permet de pondérer les nœuds, masquer des sous-graphes, exporter le graph. Confort. |
| **Tag Wrangler** (optionnel) | Renomme un tag dans tout le vault. Utile pour les opérations de réorganisation manuelles. |

## Comportement du bridge `Deploy-ObsidianStyle`

À l'exécution de `deploy.ps1` / `deploy.sh` (opt-out via `--skip-obsidian-style`, bypass garde-fou via `--force-obsidian-style`) :

1. **Détection Obsidian ouvert** : si un processus `Obsidian` tourne OU si le lock file `{vault}/.obsidian/workspace.json` a été modifié dans les dernières 60 secondes → **abort** avec message clair (Obsidian doit être fermé pour patcher en sécurité). Bypass possible via `--force-obsidian-style`.
2. **Pour chaque fichier `*.json` de cet adapter (récursif)** :
   - Calcul du chemin relatif depuis `adapters/obsidian-style/` (ex: `plugins/obsidian-front-matter-title-plugin/data.json`).
   - Création du dossier parent dans `.obsidian/` si manquant.
   - Si la cible n'existe pas → écrire la version canonique.
   - Si la cible existe et son contenu est identique à la version canonique → skip silencieux.
   - Si la cible existe et son contenu diffère → backup `{cible}.bak-pre-style-{YYYY-MM-DD-HHmmss}` puis écrire la version canonique **uniquement** si la cible porte le marker `_secondbrain_canonical`. Sinon (= personnalisation utilisateur) → skip.
3. **Marker `_secondbrain_canonical`** : chaque fichier de cet adapter porte la clé `_secondbrain_canonical: "v0.7.3"` à la racine de son JSON. Permet de détecter au prochain déploiement si le fichier vault est encore une version canonique kit (à mettre à jour) ou une version personnalisée (à laisser tranquille).

## Personnaliser la palette du graph ou la config Front Matter Title

Les valeurs RGB de `graph.json` sont des entiers décimaux (format Obsidian). Pour modifier :

- Modifier directement le fichier dans `adapters/obsidian-style/` (côté kit) puis re-deploy → applique la nouvelle palette/config canonique à tous les vaults où le marker est encore présent.
- Modifier dans Obsidian via Graph view → Settings → Color groups → le fichier vault est sauvegardé avec un nouveau contenu, le marker `_secondbrain_canonical` disparaît, le prochain deploy backup avant d'écraser. Si tu veux **conserver** ta personnalisation, retire le marker manuellement et le deploy ne touchera plus à ce fichier.

## Convention `_secondbrain_canonical`

Présence du marker = "ce fichier est encore une version canonique du kit, je peux le mettre à jour à la prochaine release" (avec backup). Absence = "ce fichier a été personnalisé par l'utilisateur, je le laisse tranquille". Le bridge respecte cette convention pour ne jamais écraser silencieusement une personnalisation.
