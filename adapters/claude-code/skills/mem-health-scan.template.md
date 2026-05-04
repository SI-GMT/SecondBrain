---
name: mem-health-scan
description: "Audit the vault for hygiene defects without writing anything. Detects 7 categories: stray-zone-md (empty MDs at vault root named after a zone, created by Obsidian when a dangling wikilink is clicked), empty-md-at-root, missing-zone-index (zones lacking their {zone}/index.md hub), missing-display (frontmatter without the v0.7.2 display field where conventions require it), dangling-wikilinks, orphan-atoms (transverse atoms with no project/domain attachment and no incoming wikilinks), missing-archeo-hashes (atoms with source: archeo-* missing content_hash). Persists a structured report at 99-meta/health/scan-{ts}.md that mem-health-repair consumes. AUTO-TRIGGER when the user says — 'audit my vault', 'check vault health', 'scan memory for issues', 'find orphans in the vault', 'what's broken in memory?'. Read-only."
---

{{PROCEDURE}}
