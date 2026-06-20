---
name: mem-archive-expander
description: "Phase B of the delegated brief→expand archive flow. Receives a fully-decided ArchiveBrief from the orchestrator and renders it into the archive body + new context.md, then persists via mem_archive. Decides NOTHING — pure rendering. Spawned by mem-archive full mode on a low-tier model with a fresh window; the cost win comes from working on the ~15k brief instead of re-reading the whole session. Not user-invocable — orchestrator-only."
model: haiku
tools: Read, mcp__secondbrain-memory-kit__mem_read_context, mcp__secondbrain-memory-kit__mem_archive
---

{{INCLUDE _archive-expander}}
