---
description: Rétro-archiver une arborescence de pages Confluence (page racine + descendance ou space complet) dans le vault mémoire, avec enrichissement automatique par les tickets Jira référencés depuis les pages. Prérequis MCP Atlassian côté client.
---

{{PROCEDURE}}

## Arguments utilisateur

Le premier token non-option est l'URL Confluence (page ou space root). Options : `--projet {nom}`, `--profondeur N`, `--skip-children`, `--depuis YYYY-MM-DD`, `--skip-jira`, `--dry-run`.

```text
$ARGUMENTS
```
