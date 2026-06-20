# Procedure: Worklog (weekly activity report)

Goal: turn a week of session archives into a worklog — a daily hours table prorated over a fixed daily amplitude, plus a structured activity report at **three verbosity levels** (brief / digest / detailed), and persist all three in one chronodated weekly archive under the `worklogs` domain so the user can retrieve them week after week. The collection step is read-only; the persistence step writes a single weekly archive (and nothing else of the user's projects).

## Trigger

The user types `/mem-worklog [week_of] [--amplitude H] [--weekend]` or expresses the intent in natural language: "do my worklog", "fais mon worklog", "weekly activity report", "rapport d'activité de la semaine", "estime mon temps passé cette semaine", "remplis mon relevé d'heures".

Recognized options:
- `week_of`: any date `YYYY-MM-DD` inside the target week. Default = today. The tool resolves the Monday→Sunday ISO week containing it.
- `--amplitude H`: worked hours per day used for proration. Default `7`.
- `--weekend`: include Saturday/Sunday in the daily breakdown. Default off (Mon–Fri).

## Verbosity levels

The report is produced at three levels, all from the same collected corpus:

- **brief** — one line per active project / perimeter. For a quick scan / chat reply. No table, no sections, **no time figures**.
- **digest** — the **email copy-paste** version: the four blocks below in **big-picture form** — aggregate the operational figures ("2 runs, 80→91%" rather than each run), no granular detail. It carries **no temporality** — no hours, no days, no percentages (time is tracked elsewhere, e.g. a Jira worklog). Rendered as a nested Markdown list: **bold block titles**, **bold `[project or perimeter]`**, detail bullets **indented** one level. Short and digestible — exactly what the user pastes into a status email.
- **detailed** — the **meeting / archive** version: the same four blocks with the granular detail, **plus** the hours statistics (daily table + per-project totals). The stats and the fine-grained figures live here and in the archive frontmatter (`hours_by_project`), never in the digest.

The four blocks (digest = aggregated, detailed = granular):

```
**LISTE DES TACHES**

- **[<project or perimeter>]**
    - headline 1 … headline N

**EN COURS / RÉALISÉ**

- **[<project or perimeter>]**
    - headline (aggregated figures)

**FAITS MARQUANTS**

- **[<project or perimeter>]**
    - major deliverable / unlock

**SEMAINE PROCHAINE**

- **[<project or perimeter>]**
    - next objective
```

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` field. In what follows, `{VAULT}` denotes this value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Collect the week's archives

Resolve the Monday→Sunday week of `week_of` (default today). Then, for **every** project under `{VAULT}/10-episodes/projects/*/archives/` and every domain under `{VAULT}/10-episodes/domains/*/archives/`, select the archives whose **filename date prefix** (`YYYY-MM-DD-HHhMM-{slug}-…`) falls inside that week.

For each selected archive, parse:
- date, time, slug, human-readable subject (from the filename);
- a **head excerpt** of the body (the summary signal — first meaningful lines, skipping headings/blockquotes);
- a **next-steps block** — the body of the first section titled like *Reste à faire / Prochaines étapes / Next steps / Reprise / Semaine prochaine* (feeds the "next week" section of the report).

> A session is often archived the **next morning** (e.g. a Monday session archived Tuesday 08h3x). Trust the **filename date**, not the wall clock. When reconstructing, attribute the work to the day it describes.

### 2. Prorate over the daily amplitude

For each day with ≥1 session, the **naive** baseline = split `amplitude` equally across the **distinct projects** active that day (rounded to 0.25h). Sum across the week → naive total per project.

Then **refine with density judgment** — the naive equal split is only a starting point. Re-weight each day using the visible effort in the excerpts: a long, multi-deliverable session outweighs a quick check; two sessions on the same project in one day concentrate that day's hours there. Keep each day's total equal to `amplitude` (don't invent hours beyond the amplitude). State that the result is an estimate from archive density, not real time-tracking.

### 3. Render the report

Read `{VAULT}/99-meta/worklog-template.md`. This file defines **only the report format** — the section structure, the wording, the level of grouping, and optionally a default amplitude. **Follow its format.**

**First use — seed the default.** If the file does not exist, deploy the default format-only template below into `{VAULT}/99-meta/worklog-template.md` before rendering (UTF-8 without BOM, LF), then follow it. The MCP tool does this automatically in `phase="collect"` (a one-time, idempotent config bootstrap — the only write the collect phase ever performs); in skills-fallback mode, write it by hand.

The template is a **format**, never a **referential**: it must not hardcode a fixed list of project codes, category labels, or perimeters. A worklog must render correctly for any project active that week, including projects that did not exist when the template was written. Category labels are therefore **derived at render time**, not looked up from a frozen table (see below).

Default template to seed (the shipped default is in English — the report itself is still rendered in the user's language):

```markdown
---
title: Worklog template
kind: reference
amplitude_default: 7
---

# Worklog template

Render format for `/mem-worklog` — the report STRUCTURE, not a referential.
Categories are derived at render time from the projects active that week
(default: the project slug, upper-cased). Edit this file to fit your own format.

## Email copy-paste section

Big picture only (aggregate operational figures, no granular detail), NO
temporality (no hours, days or percentages — time is tracked elsewhere). Nested
Markdown list: bold block titles, bold `[project or perimeter]`, detail bullets
indented one level.

    **LISTE DES TACHES**

    - **[<project or perimeter>]**
        - headline 1 … headline N

    **EN COURS / RÉALISÉ**

    - **[<project or perimeter>]**
        - headline (aggregated figures)

    **FAITS MARQUANTS**

    - **[<project or perimeter>]**
        - major deliverable / unlock

    **SEMAINE PROCHAINE**

    - **[<project or perimeter>]**
        - next objective

## Statistics (archive only)

Per-project / per-day hours may still be generated and kept in the archive
(frontmatter `hours_by_project` + a table in the detailed view), but never in
the email section above.

## Rules

- `[project or perimeter]` = project slug upper-cased by default; broader grouping
  only when the week's content justifies it — never from a hardcoded mapping.
- The user states the number of worked days per request (4-day week, day off…).
- Proration is an estimate from archive density/timestamps, not real tracking.
```

Produce the outputs in the user's conversational language, following the four-block skeleton (see the Verbosity levels section for the canonical bold/indented form). The **digest** is the aggregated, big-picture version of these blocks; the **detailed** view repeats them with granular figures plus the hours table.

**Temporality rule.** The **digest** (email copy-paste) carries the four blocks **only**, in big-picture form with aggregated figures — no hours, no days, no percentages, no daily table. The hours statistics (daily table + per-project totals) and the granular figures belong to the **detailed** view and the archive frontmatter (`hours_by_project`) — never the digest. The number of worked days is a per-request input (a 4-day week, a day off…): it adjusts the stats in the detailed/archive view, but the digest is unaffected (it has no time figures anyway).

**Deriving the `[CATEGORY]` label** — derive it at render time, never from a frozen lookup table:
- Default: the project slug, upper-cased (e.g. `ecosav → [ECOSAV]`). Always works, zero config, no dependence on a project existing in advance.
- Optionally group several slugs under a broader label when the work obviously belongs to one functional area — but infer that grouping from the archives' own content/tags that week, not from a hardcoded mapping. `[SUBPROJECT]` (when used) is likewise the slug or an obvious sub-area, not a registry entry.

If the user wants stable category labels across weeks, that preference is a per-user convention they state in conversation — it does not belong in the template as a project→category table.

### 4. Persist the weekly worklog

After rendering the three levels, persist them in one chronodated weekly archive so the user can retrieve them week after week. With the MCP tool, call `mem_worklog` again with `phase="persist"`, passing `week_of`, `brief_md`, `digest_md`, `detailed_md` (the three renderings), the density-refined `hours_by_project`, and `amplitude_hours`.

This writes a single file `{VAULT}/10-episodes/domains/worklogs/archives/{monday}-worklog-S{week}.md` containing the three renderings as H2 sections (`## Brief`, `## Digest (courriel)`, `## Détaillé (réunion)`), with frontmatter carrying `week_start`, `week_end`, `week_number`, `amplitude_hours` and `hours_by_project`. The `worklogs` domain is auto-created on first run; its `history.md` and `context.md` are updated. **Idempotent per ISO week** — re-running for the same week overwrites the archive instead of duplicating it.

In skills-fallback mode (no MCP server), write the same file by hand: UTF-8 without BOM, LF line endings, the frontmatter and three-section body above; create the `worklogs` domain skeleton (`context.md` + `history.md` + `archives/`) if absent, and prepend the week's line to `history.md` only if not already present.

Persistence is the point of the three levels: the digest is ready to email, the detailed is ready for the meeting, and both stay side by side in a single dated archive.

### 5. Caveat

Always close with a one-line reserve: the proration is estimated from the **density and timestamps of the archives**, not from real time-tracking. Days with no archive are reconstructed best-effort. Invite the user to adjust for meetings/interruptions not captured in the vault.

## Notes

- **Collection is read-only except for the first-use template seed; persistence writes one weekly archive.** The collect phase reads archives and, on the very first use only, seeds the default `99-meta/worklog-template.md` if absent (idempotent config bootstrap). All report writes happen in the persist phase, scoped to the `worklogs` domain — the user's project archives are never touched.
- The MCP tool `mem_worklog` performs steps 1–2 deterministically (week resolution, collection, naive split) in `phase="collect"`, and step 4 deterministically (frontmatter, encoding, idempotent file + history/context) in `phase="persist"`. Steps 2-refine and 3 (the three renderings) are the LLM's semantic work on top of that corpus.
- The persisted worklog archives are **excluded from collection** — the `worklogs` domain is skipped when gathering sessions, so a weekly worklog is never re-counted as work in a later week.
- The worklog template is per-user and **format-only**: the default is seeded on first use, then each SecondBrain user edits their own `99-meta/worklog-template.md`. It is a format (structure), never a project→category referential — categories are derived at render time from the active project slugs. It governs the **detailed** level; brief and digest are derived generically.
