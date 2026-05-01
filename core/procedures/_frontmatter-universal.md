## Universal frontmatter (all zones except inbox/meta)

Every file in the vault outside `00-inbox/` and `99-meta/` carries the **6 universal fields** below. Other fields are specific to each zone (see spec section 7 of the cadrage document).

| Field | Type | Required | Description |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | yes | File creation date. Updates tolerated on `context.md` and long notes. |
| `zone` | enum | yes | `inbox`, `episodes`, `knowledge`, `procedures`, `principles`, `goals`, `people`, `cognition`, `meta`. |
| `scope` | enum | yes | `personal` or `work`. |
| `collective` | bool | yes (default `false`) | Promotion flag toward CollectiveBrain. Not read by SecondBrain v0.5.0. |
| `modality` | enum | yes | `left` or `right`. Default `left`. `right` for schemas, Excalidraw, metaphors, moodboards. |
| `tags` | list | yes | Obsidian tags. Must **redundantly mirror the frontmatter fields** to enable the graph view (Obsidian indexes tags, not fields). |
| `display` | string | recommended (v0.7.2) | Label shown in Obsidian's graph and file-explorer when the **Front Matter Title** community plugin is active. Disambiguates homonymous nodes (every project has its `context.md`, every project has its `history.md` — without `display`, the graph view shows N nodes labelled `context` and N labelled `history`, undistinguishable). Conventions per kind below. |

### `display` — recommended conventions per kind

| File kind | Convention | Example |
|---|---|---|
| `context.md` | `"{slug} — context"` | `"secondbrain — context"` |
| `history.md` | `"{slug} — history"` | `"secondbrain — history"` |
| Archives `archives/{date}-*.md` | `"{slug} — {date} {short-subject}"` | `"secondbrain — 2026-05-01 v0.7.1 livré"` |
| Topology main `99-meta/repo-topology/{slug}.md` | `"{slug} — topology"` | `"secondbrain — topology"` |
| Topology branch `99-meta/repo-topology/{slug}-branches/{branch-san}.md` | `"{slug} — topology ({branch})"` | `"acme-web — topology (feature/oauth)"` |
| Transverse atoms (`40-principles/`, `20-knowledge/`, `50-goals/`, `60-people/`) | `"{kind-suffix}: {short-title}"` where `kind-suffix` is `principle` / `knowledge` / `goal` / `person` | `"principle: source-of-truth-derived-aggregates"` |
| `index.md` (vault root) | `"vault index"` | `"vault index"` |
| `{zone}/index.md` (zone hub, v0.7.3) | `"{zone} — index"` | `"20-knowledge — index"` |

The `display` value is a string that will be picked up by Obsidian's Front Matter Title plugin. If the plugin is not installed, the field is silently ignored and Obsidian falls back to filename-based labels — so `display` is **never harmful** even when the plugin is absent. This makes it safe to add unconditionally.

For atoms produced by skills that already know the structure (router, mem-archive, mem-archeo*), `display` should be set at write time. For pre-v0.7.2 vaults, `scripts/inject-display-frontmatter.py` retroactively injects it.

### Invariants to check at write time

The router and `mem-reclass` enforce the cross-field invariants below. Any violation is blocked at write time and reported to the user:

1. **Scope personal => collectif false.** Always. `collective: true` on `scope: personal` = blocking error.
2. **Sensitive true => collectif false.** If the frontmatter carries `sensitive: true` (default on `60-people/` cards), `collective: true` is forbidden.
3. **Zone episodes => `kind` present.** Never an archive without `kind: project` or `kind: domain`.
4. **Kind project => `project: {slug}` present and slug exists** in `10-episodes/projects/`. Same for `kind: domain` and `domain: {slug}` in `10-episodes/domains/`.
5. **Tags reflect frontmatter.** `zone: episodes` => tag `zone/episodes` mandatory, and conversely. Same for `scope/*`, `kind/*`, `modality/*`.
6. **Modality absent => default `left`.** Applied silently at write time.
7. **Date mandatory outside inbox/meta + context.md/history.md.** Contexts and histories are mutable, undated.

### Special cases

- **`00-inbox/`**: no required field except `zone: inbox` and `tags: [zone/inbox]`. Other fields (scope, modality, etc.) are set at the moment of reclassification by `mem-reclass`.
- **`99-meta/`**: no `scope`, `collective`, `modality` (meta is neutral, transverse). Minimal frontmatter: `date`, `zone: meta`, `type` (among `index|zone-index|doctrine|taxonomy|rule|repo-topology`), `tags`.
- **`context.md` and `history.md`**: no `date` (mutable files). Inherit the scope of the project/domain declared once in `context.md`.
- **`{zone}/index.md` (v0.7.3)**: zone hubs sitting at the root of each numbered zone. They turn what used to be ghost wiki-link targets (the vault root `index.md` linking to `(20-knowledge/)` etc.) into real, contextualised graph nodes. Frontmatter: `zone: meta`, `type: zone-index`, `display: "{zone} — index"`, `tags: [zone/meta, type/zone-index, target-zone/{zone}]`. Body: title + one-line intro reusing the i18n `zone_labels` description + back-link to the vault root `[[index|vault index]]`. Created at scaffold time and re-asserted by `rebuild-vault-index.py`.
