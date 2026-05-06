# Procedure: Check Update (v0.10.x)

Goal: report whether a newer SecondBrain release is available on GitHub. Read-only — never pulls, never installs anything. Surfaces version drift between the running `memory-kit-mcp` and the latest `SI-GMT/SecondBrain` release tag so the user can decide when to upgrade.

This procedure is **MCP-tool first**. The MCP tool `mem_check_update` is the canonical implementation; the steps below are the skills fallback for LLMs running without the MCP server (rare — usually the user just runs `gh release view` themselves).

## Trigger

The user types `/mem-check-update` or expresses the intent in natural language: "is the kit up to date?", "any new version?", "check for updates", "any newer release?".

Arguments:
- `--force-refresh`: bypass the 24h cache and re-hit the GitHub API immediately.

## Procedure

### 1. Resolve the running version

The MCP tool reads `memory_kit_mcp.__version__` (sourced dynamically from the installed package metadata via `importlib.metadata.version("memory-kit-mcp")`). In skills fallback, run `pipx list --short | grep memory-kit-mcp` and parse the version, or read `mcp-server/pyproject.toml` if working in the kit repo directly.

### 2. Resolve the latest release tag

Hit `https://api.github.com/repos/SI-GMT/SecondBrain/releases/latest` (no auth required, 60 req/h IP-rate-limited). Parse the JSON response and read the `tag_name` field (format: `vX.Y.Z`).

In skills fallback, equivalent invocations:
- `gh release view --repo SI-GMT/SecondBrain --json tagName -q .tagName`
- `curl -s https://api.github.com/repos/SI-GMT/SecondBrain/releases/latest | jq -r .tag_name`

### 3. Cache the result

The MCP tool persists the response at `~/.memory-kit/update-check.json` with a 24h TTL so the GitHub API is hit at most once per day per machine. The cached payload includes `current_version`, `latest_version`, `update_available`, `last_checked` (Unix timestamp) and `error` (null on success, `"opt-out"` if disabled, or a stringified exception on network failure).

`update_available` is **always re-evaluated against the running version** when the cache is read — so a successful upgrade clears the flag immediately on next start, without waiting for the cache to expire.

### 4. Compare versions

Strip the leading `v` from both strings, parse each dotted chunk as an integer prefix (so `0.10.1-rc1` → `(0, 10, 1)`), then compare tuples. `update_available = remote > local`.

### 5. Opt-out

If the env var `MEMORY_KIT_NO_UPDATE_CHECK=1` is set, return `{ update_available: False, error: "opt-out" }` immediately without touching the network or the cache. This lets users on locked-down networks (no outbound HTTPS to GitHub) silence the check without breaking the server start.

### 6. Failure modes

The check **never raises** to the caller. Any of `URLError`, `TimeoutError`, malformed JSON, missing `tag_name`, filesystem error on the cache file → return an `UpdateInfo` with `update_available=False`, `latest_version=None`, and `error="<ExceptionClass>: <message>"`. The cache is **not** written on failure (so the next call retries instead of latching a stale "unknown" state).

### 7. Reporting

Format a Markdown summary with: current version, latest version, last-checked timestamp (UTC ISO 8601), and one of three statuses:
- `up to date` — versions match or local ahead.
- `update available` — latest > current; suggest `git pull && deploy.ps1 -RepairMcp` (or `deploy.sh --repair-mcp`), or the combined `deploy.ps1 -AutoUpdate` / `deploy.sh --auto-update`.
- `check failed — <error>` — surface the error class so the user knows whether to retry or check connectivity.

## Side channel: passive startup check

The `memory-kit-mcp` server also calls `check_for_update()` at startup (server.py main()) and emits a single stderr WARNING if an update is available. Cache-driven so the cost is near-zero 99% of the time. Same opt-out env var. This is **not** part of `/mem-check-update` itself — it's an automatic behaviour the user sees in their CLI's MCP server logs.

## Active update via deploy scripts

`/mem-check-update` does **not** trigger an upgrade. To actually upgrade:
- Manual: `git pull && deploy.ps1 -RepairMcp` (or `deploy.sh --repair-mcp`).
- Combined: `deploy.ps1 -AutoUpdate` / `deploy.sh --auto-update` — fetches, refuses if working tree dirty / branch != main, pulls fast-forward only, then re-execs deploy from the updated source.
