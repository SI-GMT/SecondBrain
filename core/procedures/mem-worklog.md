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

- **brief** — one line per active project. For a quick scan / chat reply. No table, no sections.
- **digest** — condensed **email** version: the daily hours table + a short FAIT MARQUANT + one line per category. Self-contained and short — this is what the user pastes into a weekly status email.
- **detailed** — the full **meeting** report (LISTE DES TACHES, EN COURS/FAIT per session, FAIT MARQUANT, SEMAINE PROCHAINE with P0/P1). Follows the vault template when present. This is the version to lean on during a meeting.

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

## Report structure

TASK LIST / IN PROGRESS-DONE / HIGHLIGHTS / NEXT WEEK (P0|P1), grouped by
`[CATEGORY]` then `[SUBPROJECT]`.

## Rules

- Daily hours table first (rows = weekdays, columns = projects, totals + %).
- `[CATEGORY]` = project slug upper-cased by default; broader grouping only when
  the week's content justifies it — never from a hardcoded mapping.
- Proration is an estimate from archive density/timestamps, not real tracking.
- P0 (blocking) / P1 (important, non-blocking) on the next-week section.
```

Produce the outputs in the user's conversational language. Start with the **daily hours table** (rows = days Mon–Fri, or Mon–Sun with `--weekend`, columns = projects, totals + percentages — the timesheet input), then render the three verbosity levels described above. The **digest** and **detailed** share this table; **brief** does not.

The **detailed** activity report — generic structure when no template:

```
LISTE DES TACHES
- [CATEGORY] / [SUBPROJECT] — one line per active work item

EN COURS / FAIT
- per project, nested: what advanced, what is done, what is in progress
  (drawn from the head excerpts of the week's archives)

FAIT MARQUANT
- the 1–3 biggest deliverables/unlocks of the week (or "RAS")

SEMAINE PROCHAINE À FAIRE
- per project, with P0/P1 priorities — drawn from the next-steps blocks
  of the most recent archives
```

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
