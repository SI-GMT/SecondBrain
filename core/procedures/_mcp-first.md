<!-- _mcp-first.md — bloc doctrinal partagé prepend en tête de chaque procédure mem-* résolue par deploy.ps1 -->

## Mode d'exécution — MCP-first ou skills fallback

Ce skill peut s'exécuter de **deux manières** selon la configuration de la CLI cliente :

### MCP-first (préféré quand disponible)

Si l'outil MCP **`mcp__memory-kit__{{TOOL_NAME}}`** est disponible dans tes outils (cas Claude Code / Codex / Copilot CLI quand le serveur `memory-kit` est configuré et démarré) :

1. **Invoque-le directement** avec les arguments dérivés du contexte utilisateur (cf. la procédure ci-dessous pour les conventions d'arguments).
2. Le serveur Python implémente la logique métier de manière déterministe (UTF-8 sans BOM, frontmatter universel, atomicité des renames, résolution wikilinks).
3. **Retourne le résultat tel quel** à l'utilisateur — le champ `summary_md` du retour est déjà rendu prêt à l'affichage.
4. **N'exécute PAS** les opérations filesystem décrites dans la procédure ci-dessous — elles seraient redondantes.

**Comment savoir si l'outil est disponible** : il apparaît dans la liste de tes outils sous le préfixe `mcp__memory-kit__` (ou équivalent selon le naming de ta CLI). Si tu ne le vois pas, c'est qu'il n'est pas configuré → bascule en skills mode.

### Skills fallback (CLI sans MCP, ou serveur indisponible)

Si l'outil MCP n'est pas disponible (Mistral Vibe à ce jour, Gemini CLI sans MCP, ou bien serveur `memory-kit` non installé / non démarré sur ce poste), **exécute la procédure complète ci-dessous** comme avant la v0.8.0. C'est le mode skills classique : tu lis et écris les fichiers du vault toi-même selon la spec.

### Pourquoi cette dualité

Cf. `docs/architecture/v0.8.0-mcp-server-cadrage.md` §9 (transition v0.8.0). MCP-first divise la consommation de tokens et garantit l'exécution déterministe ; skills fallback préserve la rétrocompatibilité avec toutes les CLI et les cas où le MCP server n'est pas opérationnel. Les deux voies pointent vers la même spec — `core/procedures/{nom-du-skill}.md` reste la source de vérité fonctionnelle.

---

