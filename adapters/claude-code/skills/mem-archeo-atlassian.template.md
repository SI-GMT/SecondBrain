---
name: mem-archeo-atlassian
description: Rétro-archiver une arborescence de pages Confluence (page racine + descendance ou space complet) dans le vault mémoire, avec enrichissement automatique par les tickets Jira référencés depuis les pages. DÉCLENCHEMENT AUTOMATIQUE (sans attendre que l'utilisateur tape /mem-archeo-atlassian) quand il exprime en langage naturel — « archive la documentation Confluence de ce projet », « fais une rétro sur cet espace Atlassian », « ingère cette page et ses enfants », « remonte tout l'arbre Confluence », « archive cette doc et les tickets liés ». Également invocable explicitement via /mem-archeo-atlassian {url} avec options --profondeur, --skip-children, --depuis, --skip-jira, --projet, --dry-run. Prérequis : MCP Atlassian disponible côté client (outils getConfluencePage, getConfluencePageDescendants, getPagesInConfluenceSpace, getJiraIssue). 1 archive par page Confluence, avec le contenu converti en Markdown + résumé de chaque ticket Jira mentionné. Idempotent (skip les pages déjà archivées à jour via confluence_page_id + confluence_updated). Frontmatter source=archeo-atlassian.
---

{{PROCEDURE}}
