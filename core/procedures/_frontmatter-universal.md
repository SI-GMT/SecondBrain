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
- **`99-meta/`**: no `scope`, `collective`, `modality` (meta is neutral, transverse). Minimal frontmatter: `date`, `zone: meta`, `type` (among `index|doctrine|taxonomy|rule`), `tags`.
- **`context.md` and `history.md`**: no `date` (mutable files). Inherit the scope of the project/domain declared once in `context.md`.
