# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**Toolib** is a curated personal library of cool websites and tools. It is a static, data-driven site where all tool entries live in `tools_db.yml` and `README.md` is generated from a Jinja2 template.

> `README.md` is auto-generated — never edit it directly.

## Workflow

### Adding a tool

Use the `/add-tool <url>` skill (`.claude/skills/add-tool/SKILL.md`). It inspects the page, picks the name, category, source, and description, then calls `scripts/add_tool.py`.

`scripts/add_tool.py` can also be used directly:

```bash
python scripts/add_tool.py inspect <url>   # page metadata, image candidates, duplicate check, categories
python scripts/add_tool.py add <url> --name "..." --category "..." --description "..." [--source URL]
                           [--image URL_OR_PATH] [--screenshot] [--new-category] [--dry-run]
```

`add` downloads the thumbnail (`--image`, then og:image, then twitter:image, then a Playwright screenshot with `--screenshot`), appends the entry to `tools_db.yml` as text (existing entries are never reformatted), and regenerates `README.md`.

### Updating a tool

Edit `tools_db.yml`, then regenerate `README.md`:

```bash
python scripts/generate_readme.py
```

### Setup

```bash
pip install -r requirements.txt
# optional, for --screenshot:
pip install playwright && playwright install chromium
```

## Architecture

| File | Role |
|---|---|
| `tools_db.yml` | Source of truth — one YAML list entry per tool |
| `scripts/README.md.jinja` | Jinja2 template that defines the README layout |
| `scripts/generate_readme.py` | Reads the YAML (never writes it), groups tools by category, and renders the template |
| `scripts/add_tool.py` | Adds a tool from a URL: thumbnail download, YAML append, README regeneration |
| `.claude/skills/add-tool/` | Claude skill that fills in the fields and drives `add_tool.py` |
| `assets/thumbnails/` | Tool thumbnail images, stored locally (never hotlinked), named `<slug>.<ext>` |
| `README.md` | Generated output — do not edit manually |

### `tools_db.yml` entry schema

```yaml
- name: Tool Name
  url: https://example.com
  source: https://github.com/owner/repo  # or null for closed-source
  thumbnail: assets/thumbnails/toolname.png  # png, jpg, webp, gif, or svg
  category: Category Name
  description: >
    Multi-line description of the tool.
```

Entries are separated by a blank line. Descriptions use the `>` folded style.

Categories currently in use: `Design & Creative`, `Developer Tools`, `Productivity & Practice`, `Games & Tabletop`, `Music & Audio`, `Reference & Research`.

The Jinja2 template derives Contents anchor links by lowercasing the category name and replacing spaces with `-` and stripping `&`, so new category names must produce valid Markdown anchors.
