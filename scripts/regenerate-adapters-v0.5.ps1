#Requires -Version 7.0

<#
.SYNOPSIS
    Regenerates adapter templates for v0.5: renames + new skills.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Write-Ok([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }

# YAML double-quoted scalar — robust against ':' in descriptions and embedded
# quotes. Backslash and double-quote are escaped per YAML spec.
function Format-YamlDouble([string]$s) {
    $escaped = $s -replace '\\', '\\' -replace '"', '\"'
    return "`"$escaped`""
}

# v0.5 skill definitions
$skillsV05 = [ordered]@{
    'mem-archive' = @{
        Description = "Archive the current work session into the memory vault so it can be resumed later via /mem-recall. Use this skill in TWO distinct situations. (1) FULL MODE, end of session — trigger when the user says 'we're stopping', 'I'm leaving', 'we're done', types /clear or /mem-archive, or explicitly asks to archive. Then execute the full procedure (timestamped archive file + rewrite of context.md + update of history.md + update of index.md). (2) SILENT INCREMENTAL MODE, during the session — as soon as a fact, decision, or important next step emerges AND is not already in context.md, update ONLY context.md without creating an archive or announcing the action to the user. Never create a full archive in silent mode: it would pollute the history."
        ArgsText = "No required argument. Detection of the current project from CWD or git origin. Options: --project {slug} (force the target project), --message ""{summary}"" (override the auto-summary), --no-confirm, --dry-run."
    }
    'mem-recall' = @{
        Description = "Load a project's context from the memory vault to resume a previous session without re-briefing. AUTO-TRIGGER (without waiting for the user to type /mem-recall) as soon as the user expresses, in natural language — a resumption intent ('let's resume', 'let's continue', 'where were we on X', 'back to it') OR a need to query memory ('do you remember…', 'what did we decide about…', 'what did we do again?', 'remind me'). Also explicitly invocable via /mem-recall with an optional project name. If the target project is ambiguous, ask for confirmation before executing."
        ArgsText = "Optional argument: project or domain slug. If omitted, the skill tries to detect from CWD; if multiple matches, asks the user to choose."
    }
    'mem-doc' = @{
        Description = "Ingest a local document (PDF, Markdown, text, image, docx…) into the memory vault as a single-shot archive. AUTO-TRIGGER (without waiting for the user to type /mem-doc) when they express, in natural language — 'ingest this document', 'archive this file', 'save this PDF to memory', 'absorb this document', 'index this spec'. Also explicitly invocable via /mem-doc {path} with options --project {slug}, --title ""{text}"". The target project is auto-resolved (priority: explicit arg → path match → CWD match → inbox fallback)."
        ArgsText = "Required: path to the document. Options: --project {slug}, --title ""{text}"", --zone X (force target zone), --no-confirm, --dry-run."
    }
    'mem-archeo' = @{
        Description = "Triphasic archeo orchestrator. Runs Phase 1 (organizational/decisional/functional context — mem-archeo-context), Phase 2 (technical stack — mem-archeo-stack), Phase 3 (Git history — mem-archeo-git) in sequence on a Git repo, sharing a single Phase 0 topology scan across them. v0.7.1 BRANCH-FIRST MODE — flag --branch-first {branch} focuses the orchestration on a feature branch (commits since divergence with --branch-base, modified manifests, touched files); the global ambient context is captured in light mode. Cross-workspace awareness (monorepo packages touched by the branch are linked to their vault projects). Granularity --by-author by default (one archive per author per window) for deep author-level analysis, --by-merge or --by-window override. AUTO-TRIGGER when the user says — 'do a full archeo of this project', 'reconstruct project context, stack and history', 'archeo on this repo', 'archeo this feature branch', 'analyze what was done on branch X by author'. Persists topologies in 99-meta/repo-topology/{slug}.md (main) and 99-meta/repo-topology/{slug}-branches/{branch-san}.md (per branch when --branch-first)."
        ArgsText = "Optional: path to the Git repo (default: CWD). Options: --project {slug}, --skip-phase context|stack|git, --only-phase context|stack|git, --level tags|releases|merges|commits, --since YYYY-MM-DD, --until YYYY-MM-DD, --window day|week|month, --depth N, --rescan, --dry-run, --no-confirm. Branch-first: --branch-first {branch}, --branch-base {ref}, --by-author|--by-merge|--by-window, --no-main-topology."
    }
    'mem-archeo-context' = @{
        Description = "Phase 1 of the triphasic archeo: extract from a repo's organizational, decisional and functional documents (CLAUDE.md, AGENTS.md, README, docs/, cadrage/, adr/, rfc/, CHANGELOG) the principles, goals, recorded ADRs and methodological conventions that frame the project. Source archeo-context. v0.7.1 BRANCH-FIRST MODE — flag --branch-first {branch} scopes deep extraction to documents modified or created on the branch since divergence; other documents are surveyed in light mode (filename + first heading) without per-category extraction. AUTO-TRIGGER when the user says — 'ingest the project context', 'archeo the docs of this repo', 'extract principles and goals from project docs', 'extract context of this branch'. Idempotent via (project, source_doc, extracted_category) standard, (project, branch, source_doc, extracted_category) in branch-first."
        ArgsText = "Optional: path to the Git repo (default: CWD). Options: --project {slug}, --depth N, --only-categories workflow,sync,multi-tenant,security,adr,goal,other, --rescan, --dry-run, --no-confirm. Branch-first: --branch-first {branch}, --branch-base {ref}."
    }
    'mem-archeo-stack' = @{
        Description = "Phase 2 of the triphasic archeo: resolve the technical stack from manifests (package.json, pyproject.toml, Cargo.toml, go.mod, etc.), containerization (Dockerfile, docker-compose), CI/CD config, test frameworks and tooling. Source archeo-stack. v0.7.1 BRANCH-FIRST MODE — flag --branch-first {branch} resolves only the layers whose manifests were modified on the branch; produces an additional 'ambient' atom that links to the main topology and to the touched workspaces' vault projects (cross-workspace awareness). AUTO-TRIGGER when the user says — 'ingest the stack of this project', 'extract the technical context', 'archeo the deps and infra', 'analyze the stack changes on this branch'. Idempotent via (project, source_manifest, detected_layer) standard, (project, branch, source_manifest, detected_layer) in branch-first."
        ArgsText = "Optional: path to the Git repo (default: CWD). Options: --project {slug}, --depth N, --only-layers frontend,backend,db,ci,infra,tests,tooling,other, --rescan, --dry-run, --no-confirm. Branch-first: --branch-first {branch}, --branch-base {ref}."
    }
    'mem-archeo-git' = @{
        Description = "Phase 3 of the triphasic archeo: reconstruct the Git history of an existing repo as dated archives, enriched by the topology and stack from Phases 0/1/2. Surfaces friction sequences (>=3 successive commits on the same theme) and cross-links derived atoms. v0.7.1 BRANCH-FIRST MODE — flag --branch-first {branch} reconstructs commits on the branch since divergence with --branch-base. Granularity --by-author (default — one archive per author per time-window for author-level pattern analysis), --by-merge (per merge in the long-lived branch), or --by-window (classic time grouping). Co-Authored-By trailers captured as metadata only (useful to distinguish human vs LLM contributions). Source archeo-git. AUTO-TRIGGER when the user says — 'do a Git retro of this project', 'reconstruct the history', 'archeo the commits', 'analyze who did what on this branch'. Idempotent via (project, source_milestone, type, subject) standard, with branch added in branch-first."
        ArgsText = "Optional: path to the Git repo (default: CWD). Options: --level tags|releases|merges|commits, --project {slug}, --since YYYY-MM-DD, --until YYYY-MM-DD, --window day|week|month, --depth N, --rescan, --dry-run, --no-confirm. Branch-first: --branch-first {branch}, --branch-base {ref}, --by-author|--by-merge|--by-window."
    }
    'mem-archeo-atlassian' = @{
        Description = "Retro-archive a Confluence page tree (root page + descendants, or a full space) into the memory vault, with automatic enrichment from the Jira tickets referenced in the pages. AUTO-TRIGGER (without waiting for /mem-archeo-atlassian) when the user says — 'archive the Confluence documentation of this project', 'do a retro on this Atlassian space', 'ingest this page and its children', 'archive this doc and the linked tickets'. Also invocable via /mem-archeo-atlassian {url} with options --depth, --skip-children, --since, --skip-jira, --project, --dry-run. Requires the Atlassian MCP on the client side. 1 archive per Confluence page, with content converted to Markdown + summary of each Jira ticket mentioned. Idempotent (skips pages already archived up-to-date via confluence_page_id + confluence_updated). Frontmatter source=archeo-atlassian."
        ArgsText = "Required: Confluence URL (page or space). Options: --depth N, --skip-children, --since YYYY-MM-DD, --skip-jira, --project {slug}, --dry-run, --no-confirm."
    }
    'mem-search' = @{
        Description = "Full-text search in the memory vault (archives, contexts, histories, index). Returns matches with 2 lines of context, grouped by file, sorted recent-archives-first. TRIGGER via /mem-search {query} or natural language — 'search memory for X', 'find archives that mention Y', 'where did we talk about Z?'. Excludes .obsidian/, *.canvas, *.excalidraw.md, *.base. Read-only. v0.7.2 EXTENDED FILTERS — --source archeo-context|archeo-stack|archeo-git|lived|doc|manual|archeo-* (wildcard), --branch {name}, --extracted-category {value}, --detected-layer {value}, --author {email-or-name} for fine-grained queries on the archeo-enriched vault."
        ArgsText = "Required: search query. Options: --zone X, --scope personal|work|all, --kind project|domain, --modality left|right, --project {slug}, --domain {slug}, --type {value}, --source {value-or-archeo-*}, --branch {name}, --extracted-category {value}, --detected-layer {value}, --author {string}, --limit N, --case-sensitive."
    }
    'mem-digest' = @{
        Description = "Synthesize the last N archives of a project — major arcs, structural decisions, drift of next steps, current state. Useful when a project has many sessions and you want the through-line without rereading everything. Read-only, writes nothing to the vault. TRIGGER via /mem-digest {project} [N] or natural language — 'summarize the last N sessions of X', 'do a digest of X', 'give me the through-line of X'. Default N=5. v0.7.2 — separates FOUNDATIONS (stable stature: stack, archeo-context principles, archeo-stack architecture) from SESSIONS (lived archives + archeo-git) so the project's frame and its trajectory are surfaced distinctly instead of being collapsed into a single timeline."
        ArgsText = "Required: project slug. Optional second argument: N (number of archives to include, default 5). Options: --zone X, --scope personal|work|all, --since YYYY-MM-DD."
    }
    'mem-rollback-archive' = @{
        Description = "Cancel the last archive of a project (or of the global vault if no project specified). Deletes the archive file, removes the corresponding line from history.md and from index.md. DOES NOT RESTORE context.md — warn the user and suggest /mem-recall to regenerate a context from the remaining archives. TRIGGER via /mem-rollback-archive [project] or natural language — 'cancel the last archive', 'forget the last session', 'rollback the archive of X'."
        ArgsText = "Optional: project slug. If omitted, rolls back the most recent archive globally. Options: --with-derived (also remove derived atoms), --dry-run, --no-confirm."
    }
    'mem' = @{
        Description = "Universal ingestion router. Receives free-form content, segments it into atoms, and classifies each atom into the right vault zone via a heuristic cascade. Zero-friction default path. Trigger when the user says 'note this', 'save', 'capture this', 'add to memory' without specifying a zone."
        ArgsText = "Content to ingest. The router decides where it goes. Options: --scope personal|work, --zone X (force the zone), --project/--domain {slug} (force attachment), --no-confirm, --dry-run."
    }
    'mem-list' = @{
        Description = "List vault projects and domains with their synthetic state. Renamed from mem-list-projects in v0.5 (now handles BOTH projects and domains). Can also list a zone's contents via --zone X. v0.7.2 — each project line is enriched with archeo coverage glyphs: T (main topology present), B{N} (N branch topologies known), [{C}c {S}s {G}g] (counts of archeo-context/stack/git atoms). With --detail, expands to a full per-project breakdown including repo_path, workspace_member, and per-source atom counts."
        ArgsText = "No required argument. Options: --kind project|domain|all, --scope personal|work|all, --zone X, --detail."
    }
    'mem-rename' = @{
        Description = "Rename a project or domain completely: physical folder, frontmatter, tags, Obsidian links, index.md, history.md. Renamed from mem-rename-project in v0.5 (operates on BOTH projects and domains)."
        ArgsText = "Two required arguments: old-slug new-slug. Options: --dry-run, --no-confirm."
    }
    'mem-merge' = @{
        Description = "Merge two projects OR two domains in the vault. Reattributes archives + cross-cutting atoms. Restriction: no project <-> domain mixing. Renamed from mem-merge-projects in v0.5."
        ArgsText = "Two required arguments: source-slug target-slug. Options: --dry-run, --no-confirm."
    }
    'mem-note' = @{
        Description = "Quickly ingest a knowledge note into 20-knowledge/. Explicit shortcut when the user knows what they're capturing is a fact, concept, card, or stable synthesis."
        ArgsText = "Note content. Options: --scope personal|work, --family business|tech|life|methods, --type concept|card|glossary|synthesis|reference, --no-confirm, --dry-run."
    }
    'mem-principle' = @{
        Description = "Ingest a principle (heuristic, red line, value, action rule) into 40-principles/. Explicit shortcut. The router infers the constraint level from the tone."
        ArgsText = "Principle content. Options: --scope personal|work, --force red-line|heuristic|preference, --domain X, --project {slug}, --no-confirm, --dry-run."
    }
    'mem-goal' = @{
        Description = "Ingest a goal (future intention, desired state, aim) into 50-goals/. Explicit shortcut. Detects horizon (short/medium/long) from the deadline."
        ArgsText = "Goal content. Options: --scope personal|work, --horizon short|medium|long, --deadline YYYY-MM-DD, --project {slug}, --no-confirm, --dry-run."
    }
    'mem-person' = @{
        Description = "Ingest a person card (colleague, client, friend, family) into 60-people/. Explicit shortcut. Always sensitive=true by default (forbids promotion to CollectiveBrain)."
        ArgsText = "Person content/description. Options: --scope personal|work, --category colleagues|clients|partners|family|friends|acquaintances, --no-confirm, --dry-run."
    }
    'mem-reclass' = @{
        Description = "Change the scope or zone of an existing item. Updates frontmatter + tags + moves the file + rewrites cross-references. Confirmed by decision D3.4 of the v0.5 design doc."
        ArgsText = "File path required + at least one change option. Options: --zone X, --scope personal|work, --type X, --project/--domain {slug}, --dry-run, --no-confirm."
    }
    'mem-promote-domain' = @{
        Description = "Promote a coherent set of items from the inbox into a new permanent domain in 10-episodes/domains/{slug}/. Enforces the anti-drift rule (>=3 items on the same thread)."
        ArgsText = "New domain slug + optional items. Options: --scope personal|work, --from-inbox {keyword}, --dry-run, --no-confirm."
    }
    'mem-health-scan' = @{
        Description = "Audit the vault for hygiene defects without writing anything. Detects 7 categories: stray-zone-md (empty MDs at vault root named after a zone, created by Obsidian when a dangling wikilink is clicked), empty-md-at-root, missing-zone-index (zones lacking their {zone}/index.md hub), missing-display (frontmatter without the v0.7.2 display field where conventions require it), dangling-wikilinks, orphan-atoms (transverse atoms with no project/domain attachment and no incoming wikilinks), missing-archeo-hashes (atoms with source: archeo-* missing content_hash). Persists a structured report at 99-meta/health/scan-{ts}.md that mem-health-repair consumes. AUTO-TRIGGER when the user says — 'audit my vault', 'check vault health', 'scan memory for issues', 'find orphans in the vault', 'what's broken in memory?'. Read-only."
        ArgsText = "No required argument. Options: --zones {list}, --only {category}, --quiet, --no-write."
    }
    'mem-health-repair' = @{
        Description = "Apply safe idempotent fixes to the issues detected by mem-health-scan. Dry-run by default — only writes when --apply is passed. Repairs: stray-zone-md and empty-md-at-root (delete after re-stat pre-flight), missing-zone-index (delegates to rebuild-vault-index.py), missing-display (delegates to inject-display-frontmatter.py --apply), missing-archeo-hashes (delegates to inject-archeo-hashes.py --apply). Orphan-atoms is semi-automated with per-orphan prompt (reclassify to 00-inbox with tag unlinked-atom, attach to a project, or skip). Dangling-wikilinks is manual-review only and skipped. Persists a repair report at 99-meta/health/repair-{ts}.md. AUTO-TRIGGER when the user says — 'fix the vault', 'repair memory health', 'clean up the vault', 'apply health fixes'."
        ArgsText = "No required argument. Options: --apply (without it, dry-run only), --from-report {path}, --only {category}, --no-orphans, --no-confirm."
    }
    'mem-historize' = @{
        Description = "Move a finished project into the archived zone (10-episodes/archived/{slug}/) so it stays in the vault for long-term reference but is excluded by default from the access skills (mem-recall, mem-list, mem-search, mem-digest). Reduces token consumption of the briefing at session start. Reverse via --revive. Delegates to scripts/mem-historize.py (versioned, idempotent, dry-run by default per the when-to-script doctrine). Patches context.md frontmatter (phase: archived, archived_at: {date}, display suffixed [archived]) and moves the folder atomically. AUTO-TRIGGER when the user says — 'archive le projet X, c'est fini', 'mets ce projet de côté', 'archive ce projet terminé', 'historise ce projet', 'ressuscite X', 'remets X en actif'. The associated rule matrix in core/procedures/_archived.md governs how every other skill (recall, list, search, digest, archive, archeo*, doc) treats archived projects (default: refuse / skip / collapse) with explicit override flags (--include-archived, --from-archived, --allow-archived) when retrospective is wanted."
        ArgsText = "Required: --slug {project-slug}. Options: --revive (reverse the archive), --apply (without it, dry-run only), --no-confirm, --json."
    }
}

# Renamed skills (old -> new mapping for deletion)
$renamings = @('mem-list-projects', 'mem-rename-project', 'mem-merge-projects')

# Delete obsolete templates
Write-Step "> Deleting renamed templates"
foreach ($old in $renamings) {
    $paths = @(
        "adapters\claude-code\skills\$old.template.md",
        "adapters\claude-code\commands\$old.md",
        "adapters\gemini-cli\commands\$old.template.toml",
        "adapters\codex\prompts\$old.template.md",
        "adapters\codex\skills\$old",
        "adapters\mistral-vibe\skills\$old"
    )
    foreach ($rel in $paths) {
        $full = Join-Path $root $rel
        if (Test-Path $full) {
            Remove-Item -Path $full -Recurse -Force
            Write-Ok "Deleted: $rel"
        }
    }
}

# Generate new templates
Write-Host ''
Write-Step "> Generating v0.5 templates"

foreach ($name in $skillsV05.Keys) {
    Write-Host ''
    Write-Step "  $name"
    $desc = $skillsV05[$name].Description
    $argsTxt = $skillsV05[$name].ArgsText
    $descShort = $desc.Split('.')[0]
    $descYaml = Format-YamlDouble $desc

    # Claude Code skill
    $p1 = Join-Path $root "adapters\claude-code\skills\$name.template.md"
    $c1 = "---`nname: $name`ndescription: $descYaml`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p1 -Value $c1 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Claude skill   : $name.template.md"

    # Claude Code command
    $p2 = Join-Path $root "adapters\claude-code\commands\$name.md"
    $c2 = "$descShort.`n`n$argsTxt`n`n`$ARGUMENTS`n"
    Set-Content -Path $p2 -Value $c2 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Claude command : $name.md"

    # Gemini CLI command (literal multi-line strings)
    $p3 = Join-Path $root "adapters\gemini-cli\commands\$name.template.toml"
    $descEsc = $desc -replace '"', '\"'
    $c3 = "description = `"$descEsc`"`nprompt = '''`n{{PROCEDURE}}`n`n---`n$argsTxt`n'''`n"
    Set-Content -Path $p3 -Value $c3 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Gemini cmd     : $name.template.toml"

    # Codex prompt
    $p4 = Join-Path $root "adapters\codex\prompts\$name.template.md"
    $c4 = "---`ndescription: $descYaml`n---`n`n{{PROCEDURE}}`n`n## User input`n`n``````text`n`$ARGUMENTS`n```````n"
    Set-Content -Path $p4 -Value $c4 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Codex prompt   : $name.template.md"

    # Codex skill
    $d5 = Join-Path $root "adapters\codex\skills\$name"
    if (-not (Test-Path $d5)) { New-Item -ItemType Directory -Path $d5 -Force | Out-Null }
    $p5 = Join-Path $d5 "SKILL.md.template"
    $c5 = "---`nname: $name`ndescription: $descYaml`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p5 -Value $c5 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Codex skill    : $name/SKILL.md.template"

    # Vibe skill
    $d6 = Join-Path $root "adapters\mistral-vibe\skills\$name"
    if (-not (Test-Path $d6)) { New-Item -ItemType Directory -Path $d6 -Force | Out-Null }
    $p6 = Join-Path $d6 "SKILL.md.template"
    $c6 = "---`nname: $name`ndescription: $descYaml`nuser-invocable: true`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p6 -Value $c6 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Vibe skill     : $name/SKILL.md.template"
}

Write-Host ''
Write-Step "=== Adapter regeneration complete ==="
Write-Host "Skills regenerated : $($skillsV05.Count)"
Write-Host "Skills deleted     : $($renamings.Count)"
Write-Host "Run .\deploy.ps1 to propagate to the CLIs."
