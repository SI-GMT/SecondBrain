# memory-kit-mcp

> Serveur MCP (Model Context Protocol) qui expose les opérations de mémoire persistante du kit **SecondBrain** comme outils consommables par n'importe quelle CLI LLM compatible MCP (Claude Code, Codex, Copilot CLI, …).

## Vue d'ensemble

Ce serveur Python implémente les 24 skills `mem-*` du kit SecondBrain (`mem_recall`, `mem_archive`, `mem_doc`, `mem_archeo`, …) comme outils MCP. Les CLI LLM compatibles MCP appellent les outils directement (sans re-implémenter la logique côté agent), ce qui :

- Réduit la consommation de tokens (le contenu des procédures n'est plus injecté dans le system prompt).
- Garantit l'exécution déterministe (UTF-8 sans BOM, frontmatter universel, atomicité des renames, résolution wikilinks).
- Centralise la logique : un changement dans le serveur Python s'applique à toutes les CLI clientes simultanément.

Le serveur fonctionne en parallèle des **skills classiques** déployés dans chaque CLI (mode "fallback") — si le serveur MCP n'est pas disponible (ou que la CLI ne supporte pas MCP), les skills exécutent la procédure complète comme avant.

## Installation

### Pré-requis

- **Python ≥3.12**
- **pipx** (recommandé) ou pip — pour installer le binaire `memory-kit-mcp` sur le PATH

### Install standalone

```bash
pipx install ./mcp-server
```

Le binaire `memory-kit-mcp` est désormais disponible sur le PATH.

### Install via deploy.ps1 / deploy.sh

Le déploiement standard du kit SecondBrain installe automatiquement le serveur MCP si `pipx` est détecté :

```powershell
# depuis la racine du kit
.\deploy.ps1
```

Voir le [README principal](../README.md) pour les détails.

## Configuration

### Fichier de config dédié

`~/.memory-kit/config.json` (override via `$MEMORY_KIT_HOME`) :

```json
{
  "vault": "/absolute/path/to/your/vault",
  "default_scope": "work",
  "language": "en",
  "kit_repo": "/absolute/path/to/SecondBrain"
}
```

`deploy.ps1` génère ce fichier automatiquement à partir des configs CLI existantes.

### Déclaration MCP dans les CLI

**Claude Code** (`~/.claude.json`) :
```json
{
  "mcpServers": {
    "memory-kit": { "command": "memory-kit-mcp" }
  }
}
```

**Codex** (`~/.codex/config.toml`) :
```toml
[mcp_servers.memory-kit]
command = "memory-kit-mcp"
```

**GitHub Copilot CLI** (`~/.copilot/mcp-config.json`) :
```json
{
  "mcpServers": {
    "memory-kit": { "command": "memory-kit-mcp" }
  }
}
```

`deploy.ps1` injecte ces blocs idempotemment dans les configs existantes.

## Outils exposés

24 outils, miroir 1-pour-1 des skills du kit :

| Catégorie | Outils |
|---|---|
| Cycle session | `mem_recall`, `mem_archive` |
| Ingestion | `mem`, `mem_doc`, `mem_note`, `mem_principle`, `mem_goal`, `mem_person` |
| Inventaire | `mem_list`, `mem_search`, `mem_digest` |
| Vault management | `mem_rename`, `mem_merge`, `mem_reclass`, `mem_rollback_archive`, `mem_promote_domain`, `mem_historize` |
| Hygiene | `mem_health_scan`, `mem_health_repair` |
| Archeo | `mem_archeo`, `mem_archeo_context`, `mem_archeo_stack`, `mem_archeo_git`, `mem_archeo_atlassian` |

Voir `core/procedures/mem-*.md` dans le repo SecondBrain pour la spec complète de chaque outil.

## Développement

### Setup

```bash
cd mcp-server
uv venv
uv pip install -e ".[dev]"
```

### Tests

```bash
pytest
# ou avec coverage report HTML
pytest --cov-report=html
```

Cible : `--cov-fail-under=80` enforced.

### Architecture

Voir [`docs/architecture/v0.8.0-mcp-server-cadrage.md`](../docs/architecture/v0.8.0-mcp-server-cadrage.md) dans le repo principal.

## Licence

MIT. © SI Groupe Mondial Tissus.
