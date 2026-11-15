# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**Toolib** is a curated personal library of cool websites and tools. It is a static, data-driven site where all tool entries live in `tools_db.yml` and `README.md` is generated from a Jinja2 template.

> `README.md` is auto-generated — never edit it directly.

## Workflow

All commands run from the repository root. The `toolib` package needs no install step, only its dependencies.

### Adding a tool

Use the `/add-tool <url>` skill (`.claude/skills/add-tool/SKILL.md`). It inspects the page, picks the name, category, source, and description, then calls `python -m toolib add`.

The CLI can also be used directly:

```bash
python -m toolib inspect <url>   # page metadata, image candidates, duplicate check, categories
python -m toolib add <url> --name "..." --category "..." --description "..." [--source URL]
                     [--image URL_OR_PATH] [--new-category] [--dry-run]
```

`add` downloads the thumbnail (`--image` if given, otherwise the page's og:image or twitter:image), checks it's a readable image, rounds its corners, appends the entry to `tools_db.yml` as text (existing entries are never reformatted), and regenerates `README.md`.

### Updating a tool

Edit `tools_db.yml`, then regenerate `README.md`:

```bash
python -m toolib generate
```

### Setup

```bash
pip install -r requirements.txt
```

## Architecture

| File | Role |
|---|---|
| `tools_db.yml` | Source of truth — one YAML list entry per tool |
| `toolib/cli.py` | Command line (`generate`, `inspect`, `add`); `python -m toolib` runs it via `__main__.py` |
| `toolib/config.py` | Paths (repo root, `tools_db.yml`, thumbnails, template) and HTTP headers |
| `toolib/database.py` | `Tool` (one tool, and its YAML entry format) and `ToolDatabase` (loads, groups, sorts, and adds tools) |
| `toolib/page.py` | `PageInspector` — title, description, image candidates, and GitHub links from a tool's page |
| `toolib/thumbnail.py` | `Thumbnail` (size, README display width, rounded corners) and `ThumbnailFetcher` (download or copy, and check it's an image) |
| `toolib/readme.py` | `ReadmeGenerator` (builds the category and tool sections and renders the template) and `AnchorRegistry` (GitHub-style heading anchors) |
| `toolib/templates/README.md.jinja` | Jinja2 template that defines the README layout |
| `.claude/skills/add-tool/` | Claude skill that fills in the fields and drives `python -m toolib add` |
| `docs/inspect-and-add.md` | How `inspect` and `add` work: page parsing, GitHub links, duplicate check, thumbnail fetching and processing |
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

Categories currently in use: `Design & Creative`, `Developer Tools`, `Games & Tabletop`, `Hardware & Peripherals`, `Learning & Practice`, `Music & Audio`, `Reading & News`, `Reference & Research`.

The README sorts categories and tools alphabetically. Contents links use the same anchors GitHub generates for headings (`AnchorRegistry`), so any category or tool name works.
