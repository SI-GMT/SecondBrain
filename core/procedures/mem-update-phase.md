# Procedure: `mem-update-phase` (v0.9.3)

Goal: update the `phase` frontmatter field of a project's `context.md` without rewriting the entire body. Lightweight alternative to `mem-archive(mode='incremental')` when the LLM only needs to bump the phase string (e.g. "v0.9.3 in progress" → "v0.9.3 livré").

## When to invoke

- The user says "passe la phase de `{slug}` à `{new-phase}`" or equivalent.
- A workflow / orchestrator transitions a project across phases (e.g. cap acté → en cours → livré → suivant) and only the phase changes.
- An automated job (BrainyAgent couche 4 future) wants to reflect a state transition without disturbing the cumulative decisions / next steps blocks.

## Arguments

- `slug` (required) — project or domain slug.
- `phase` (required) — new phase string. Pass empty string `""` to clear the phase.

## Behaviour

1. Resolve `slug` via `paths.resolve_slug`.
2. **Refuse archived projects** per `_archived.md` doctrine — raise `PermissionError` pointing to `mem-historize` with revive=True as remediation.
3. Read `{folder}/context.md`. If missing, raise `FileNotFoundError` pointing to `mem-init-project`.
4. Update `frontmatter['phase']` with the new value, bump `frontmatter['last-session']` to today's date.
5. Write back via `vault.frontmatter.write` — body preserved verbatim.
6. Return a `ChangeReport` showing the old → new phase transition and the file modified.

## Doctrinal notes

- **Body preservation is non-negotiable** — the cumulative decisions / next steps / assets blocks are not touched. Only the frontmatter changes.
- **`last-session` bump is automatic** — reflects that an authoritative event happened on the project today.
- **Refuses archived** — same defensive behaviour as `mem-archive`. To revive, use `mem-historize --revive` first.
- **Use `mem-archive(incremental)` for full context rewrites** — `mem-update-phase` is intentionally narrow; if the body changes too, go through `mem-archive`.

## Encoding

UTF-8 without BOM, LF — same as every vault write.
