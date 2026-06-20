## Repo-relative path sigil (`<repo>/...`)

When you write a path that lives **under the project's source tree** into an
archive body, `context.md`, or `history.md`, express it as a **`<repo>/...`
sigil** instead of an absolute path:

- `C:\_PROJETS\DEVOPS\Foo\src\main.py` → `<repo>/src/main.py`
- `/home/me/proj/foo/tests/x.py` → `<repo>/tests/x.py`

The absolute root is resolved from the project's `context.md` frontmatter
field `repo_path:`. Storing the sigil (not the absolute path) means the archive
stays valid after the source tree moves on disk — relocating a project becomes
a one-field edit (`/mem-relocate-project`), and old archives never go stale.

Rules:
- Only paths **under** the project's `repo_path` become sigils. Paths to other
  repos, system files, or another machine's tree stay absolute (they are not
  anchored to this project).
- If the project has no `repo_path` set yet (legacy), leave paths as-is — the
  sigil cannot be resolved. A later `/mem-relocate-project` + (optionally)
  `/mem-archive-rewrite-paths` will migrate them.
- MCP mode applies this automatically at write time. In skills-fallback mode,
  apply the rule yourself before writing the body.
- To recover the absolute path when reading, expand the sigil against the
  current `repo_path`.
