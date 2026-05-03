"""Vault primitives — shared low-level operations on the Markdown vault.

Modules:
    paths       — zone path resolvers (10-episodes/projects/{slug}/, etc.)
    frontmatter — parse/serialize YAML frontmatter, invariants enforcement
    atomic_io   — UTF-8 LF write, atomic rename, hash check (concurrency)
    linking     — wikilink resolver, dangling-link scanner
    scanner     — walk vault, collect atoms, filter by tags
"""
