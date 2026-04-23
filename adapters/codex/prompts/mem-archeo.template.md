---
description: Reconstituer l'historique d'un dépôt Git en plusieurs archives datées dans le vault mémoire (1 archive par tag, release, merge ou fenêtre de commits). Détection automatique du niveau de granularité, confirmation interactive, idempotence par identifiant de jalon.
---

{{PROCEDURE}}

## Arguments utilisateur

Le premier token non-option est le chemin du dépôt (défaut : cwd). Options reconnues : `--niveau {tags|releases|merges|commits}`, `--projet {nom}`, `--depuis YYYY-MM-DD`, `--jusqu-a YYYY-MM-DD`, `--fenetre {jour|semaine|mois}`, `--dry-run`.

```text
$ARGUMENTS
```
