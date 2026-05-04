# Procedure: Goal (new in v0.5)

Goal: ingest a goal (future intent, desired state, target) into `50-goals/`. Explicit shortcut when the user formulates a goal.

## Trigger

The user types `/mem-goal {content}` or expresses intent in natural language: "add this goal", "note this target", "I'd like to reach X by Y".

Recognized options:
- `--scope personal|work`: forces the scope.
- `--horizon short|medium|long`: forces the time horizon. Short = weeks, medium = months, long = years.
- `--deadline YYYY-MM-DD`: explicit target date.
- `--project {slug}`: project attachment (typically for `work/projects/` goals).
- `--no-confirm`, `--dry-run`: passed through to the router.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Pre-format

The goal title is extracted from the first significant words. The body includes the "why" (motivation), any milestones, success indicators.

### 2. Invoke the router with forced zone hint

Call the router with:
- `Content`: the goal content.
- `Hint zone`: `goals`.
- `Hint source`: `manual` (unless derived by `mem-archive`).
- `Metadata`: horizon, deadline, project if provided.

{{INCLUDE _router}}

The router:
- Determines `horizon` if not forced (heuristic: deadline < 1 month = short, < 6 months = medium, >= long).
- Determines the sub-category based on scope and project (`personal/{life|health|family|finance}` or `work/{career|projects/{slug}}`).
- Writes into `{VAULT}/50-goals/...`.
- Frontmatter with `type: goal`, `horizon`, `deadline`, `status: open` (default), `project`.

### 3. Confirm

Router report.
