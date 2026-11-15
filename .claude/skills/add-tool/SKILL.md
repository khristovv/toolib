---
name: add-tool
description: Add a website or tool to the Toolib library from its URL. Use when the user pastes a link and wants it added to tools_db.yml / the README, or runs /add-tool <url>.
argument-hint: <url> [<url> ...]
allowed-tools: Bash(python -m toolib:*), Read, WebFetch, WebSearch
---

# Add a tool to Toolib

Add each URL in `$ARGUMENTS` to the library. `python -m toolib` does the mechanical work (thumbnail download, YAML append, README regeneration); your job is to fill in the fields well.

## 1. Inspect

```bash
python -m toolib inspect <url>
```

If `duplicate_of` is set, tell the user it's already in the library and skip it. If `fetch_error` is set or the metadata is thin, use WebFetch on the URL to understand what the tool does.

## 2. Decide the fields

- **name** — the product's own name (`site_name` or a cleaned-up `title`), without taglines like "– Free Online Editor".
- **source** — the official source repo. Use `github_links` if one is clearly the project's own repo; otherwise do one quick search for "<name> github". Only use a repo you're confident is official. If none, omit `--source` (closed source).
- **category** — pick from `existing_categories`. Only if none fits, propose a new one and ask the user before using `--new-category`. New names should match the existing style: Title Case words joined by spaces or ` & `.
- **description** — 2–4 sentences, roughly 40–70 words, matching the existing entries in `tools_db.yml`: open with what it is ("A free, browser-based …", "The gold standard …"), then the notable features. Concrete and factual, no marketing fluff, no first person. Leave out anything that goes stale: counts (users, items, stars), prices, version numbers, "new"/"recently launched".

## 3. Add

```bash
python -m toolib add <url> --name "..." --category "..." --description "..." [--source "..."]
```

If it reports no usable thumbnail, retry with `--image <url>` pointing at a good image you found on the page (a hero image or large logo). If there isn't one, ask the user for an image.

## 4. Check the thumbnail

Read the saved image. It should clearly represent the tool at 600px wide. If it's blank, tiny, a generic placeholder, or unrelated, replace it, trying these in order:

1. A hero image or large logo from the page itself.
2. A screenshot of the site's header or hero section. Ask the user for one. It shows the product as people see it, which is what they prefer.

Don't build composites (collages of the site's content, logos placed on generated backgrounds) unless the user asks for one.

Overwrite the file at the same path (keep the same extension, or update `thumbnail` in `tools_db.yml`). Then round its corners again with `python -c "from pathlib import Path; from toolib.thumbnail import Thumbnail; Thumbnail(Path('<path>')).round_corners()"`, and run `python -m toolib generate`.

## 5. Report

For each tool, show the name, category, source, and description you used, and the thumbnail path. Don't commit — the user reviews the changes first.
