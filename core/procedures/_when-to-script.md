# Doctrinal block: when does a skill delegate to a versioned script vs run LLM-orchestrated?

This block is shared (`{{INCLUDE _when-to-script}}`) by procedures that need to declare their execution mode explicitly. The rule below is binding — deviations require a doctrinal note.

## The rule

A skill **MUST delegate to a versioned Python script in `scripts/`** when its execution involves any of the following:

1. **Systematic vault traversal** — opening more than ~10 files in a single invocation, or recursively scanning a zone (e.g. `40-principles/**/*.md`).
2. **Structured parsing** of YAML frontmatter, Markdown body, JSON manifests, TOML configs, etc. across many files. (Parsing 1-2 files inline is fine.)
3. **Cross-file aggregation** — building an incoming-link graph, computing hashes, deduplicating, computing statistics across the vault.
4. **Idempotence and dry-run as first-class concerns** — when "did this run change anything?" must be answerable deterministically, the logic must be in a script that has unit-testable behaviour.

A skill **MAY run LLM-orchestrated (no dedicated script)** when:

1. It targets a small, named set of files (1-3) known a priori.
2. Its logic is short, conversational, or interactive (prompting the user, summarising, deciding which fix to apply on the user's behalf).
3. It's a thin orchestrator that chains *other* scripts and adds value purely via conversation glue (e.g. `mem-health-repair` invokes injectors + asks the user about orphans + writes a small report — none of those individually cross the threshold above).

## Why

The kit's promise is **deterministic, reproducible behaviour across LLMs and across sessions**. An ad-hoc script written inline by the LLM during a session has none of that:

- Not auditable: its source is in the conversation log, not the repo.
- Not reproducible: a different LLM (or the same LLM on a different day) would write a slightly different script with subtly different behaviour.
- Not testable: no place to add unit tests, no place to fix a bug once and have it stay fixed.
- Not versioned: behaviour drift over time, no semver discipline.

A versioned script in `scripts/` has all four properties. The cost of authoring it once is amortised over every future invocation. The skill's procedure shrinks to "invoke the script and surface the result" — which is the LLM's actual comparative advantage.

## What "do not fall back to inline" means

When the script is missing or unavailable, **do not silently re-implement it** in tool calls. Surface a clear error to the user:

```
✗ {skill-name} failed to invoke its scanner/processor.

  Reason : {short reason}

  Expected: python {kit_repo}/scripts/{script-name}.py [args]
  Action  : ensure Python and required deps are installed, and that
            kit_repo in {{CONFIG_FILE}} points to a valid kit checkout.
            Re-run `deploy.ps1` from the kit root if in doubt.
```

The "no fallback" stance is intentional: silent fallback means future calls of the same skill silently produce different (likely degraded) results depending on environment quirks, which defeats the entire reproducibility promise.

## Where this rule applies (catalogue)

Skills currently bound by this rule:

| Skill | Versioned script(s) | Notes |
|---|---|---|
| `mem-doc` | `scripts/doc-readers/read_*.py` | Per-format reader; PEP 723 metadata, `uv run`. |
| `mem-health-scan` | `scripts/mem-health-scan.py` | Promoted from ad-hoc in v0.7.3.1 — see incident note below. |
| `mem-health-repair` | `scripts/inject-display-frontmatter.py`, `scripts/inject-archeo-hashes.py`, `scripts/rebuild-vault-index.py` | Orchestrator skill: LLM-driven on top of versioned injectors. |

Skills explicitly LLM-orchestrated (and that's correct):

- `mem-archive`, `mem-recall`, `mem-list`, `mem-rename`, `mem-merge`, `mem-digest`, `mem-rollback-archive`, `mem-search`, `mem-reclass`, `mem-promote-domain`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`, `mem` (router) — all operate on a small named set of files or are pure conversation+IO orchestration.
- `mem-archeo*` — the orchestration is LLM-driven, but the heavy parsing of manifests/Git logs is delegated to native tools (`git log`, manifest readers), which is the equivalent of "delegate to a script".

## Incident note (v0.7.3 → v0.7.3.1)

The first iteration of `mem-health-scan` (v0.7.3) was specified as an LLM-orchestrated procedure. In practice, when invoked, the LLM created an ad-hoc Python script in `$TEMP/mem_health_scan.py` to actually execute the scan, ran it, then deleted it. The output was correct, but the logic was lost between sessions and not auditable.

This is precisely the failure mode the rule above prevents. v0.7.3.1 promotes the script to `scripts/mem-health-scan.py`, rewrites the procedure to delegate explicitly, and adds this doctrinal block to make the rule referenceable from any future skill that faces the same choice.
