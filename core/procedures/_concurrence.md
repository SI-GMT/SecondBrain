## Écritures atomiques et protection contre les accès concurrents

Le vault peut subir des accès concurrents — deux sessions LLM parallèles (ex: Claude Code + Codex), ou une session LLM qui écrit pendant qu'Obsidian édite manuellement le même fichier. Sans protection, last-write-wins corrompt ou fait perdre des entrées.

### Pattern 1 — Rename atomique (pour toutes les écritures)

Chaque fichier écrit ou réécrit suit cette séquence :

1. Écrire le nouveau contenu dans `{fichier}.tmp` (même répertoire que la cible).
2. Rename atomique `{fichier}.tmp` → `{fichier}`. Sur POSIX, `rename()` est atomique et remplace silencieusement. Sur Windows, `Move-Item -Force` (PowerShell) ou équivalent (MoveFileEx avec `MOVEFILE_REPLACE_EXISTING`).
3. Si le rename échoue, supprimer le `.tmp` et remonter l'erreur à l'utilisateur.

Commandes concrètes :

| Shell | Séquence |
|---|---|
| bash / POSIX | `printf '%s' "$contenu" > "$cible.tmp" && mv -f "$cible.tmp" "$cible"` |
| PowerShell 7+ | `Set-Content -Path "$cible.tmp" -Value $contenu -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$cible.tmp" -Destination $cible -Force` |
| Python | `Path(f"{cible}.tmp").write_text(contenu, encoding='utf-8', newline=''); Path(f"{cible}.tmp").replace(cible)` (`replace` est atomique cross-platform) |

### Pattern 2 — Hash check read-before-write (pour les fichiers partagés)

Les fichiers partagés (modifiables par plusieurs procédures ou par Obsidian en parallèle — typiquement `_index.md`, les `historique.md`, les `contexte.md`) exigent un hash check avant toute réécriture :

1. **Début d'opération** : lire le fichier, calculer son SHA-256, mémoriser (`hash_initial`).
2. **Juste avant l'écriture** : relire le fichier cible, recalculer son SHA-256 (`hash_avant`).
3. Si `hash_avant != hash_initial` → le fichier a été modifié entre-temps par un autre acteur. **Ne pas écraser**. Relire le contenu actuel, merger les modifs qu'on voulait apporter, puis reprendre à l'étape 2 (boucle jusqu'à 3 tentatives).
4. Si `hash_avant == hash_initial` → procéder au rename atomique (pattern 1).
5. Si après 3 tentatives le hash continue de diverger → stopper, afficher un avertissement à l'utilisateur : « Fichier `{cible}` modifié par un acteur externe pendant l'opération. Vérifie manuellement, puis relance la commande. »

Les fichiers **horodatés et nouveaux** (typiquement les archives sous `archives/` ou sous `{zone}/{...}/archives/`) sont exemptés du hash check : aucun conflit possible sur un nom unique. Mais ils doivent quand même utiliser le rename atomique (pattern 1).

### Limite connue

Ces patterns réduisent fortement la fenêtre de race mais ne l'éliminent pas complètement. Une race reste théoriquement possible entre le calcul de `hash_avant` et le rename. Pour une protection stricte, le MCP memory-kit (Phase 3) utilisera un verrou applicatif via `asyncio.Lock`.
