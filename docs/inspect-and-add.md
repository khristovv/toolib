# How `inspect` and `add` work

How `python -m toolib inspect` and `python -m toolib add` read a tool's page and get its thumbnail. The code is in `toolib/page.py` (`PageInspector`) and `toolib/thumbnail.py` (`Thumbnail`, `ThumbnailFetcher`).

## Fetching a page

`PageInspector(url)` does one `GET` request when it's created:

- It sends the browser-like `User-Agent` from `config.HEADERS`, because some sites block the default `python-requests` agent.
- The timeout is 15 seconds. Non-2xx responses raise `requests.HTTPError`.
- The raw bytes (`resp.content`) go to BeautifulSoup's `html.parser`. Passing bytes instead of `resp.text` lets BeautifulSoup use the page's own `<meta charset>`. If the server sends no charset, `requests` guesses Latin-1, which garbles UTF-8 titles.
- No JavaScript runs. Single-page apps that fill in their `<head>` client-side return little metadata (for example, `https://web.archive.org` has no `og:` tags).

Any `requests.RequestException` goes to the caller. `inspect` reports it as `fetch_error`, and `add` treats the page as having no image candidates.

## What gets parsed

| Field | Where it comes from |
|---|---|
| `title` | The `<title>` text, stripped |
| `site_name` | `og:site_name` |
| `description` | The first one present of `og:description`, `description`, `twitter:description` |
| `image_candidates` | `og:image`, `og:image:url`, `twitter:image`, `twitter:image:src`, in that order |
| `github_links` | Links to GitHub repositories found in the page's `<a href>` tags |

`meta(*keys)` returns the first key that has non-empty `content`. It matches both `<meta property=…>` (Open Graph) and `<meta name=…>` (standard and Twitter tags), so it doesn't matter which attribute a site uses.

Image URLs are resolved against the page URL with `urljoin`, so relative paths like `/og.png` become absolute. Duplicates are dropped and the order is kept.

### GitHub links

Every `<a href>` is matched against `https?://github.com/<owner>/<repo>` and reduced to `https://github.com/<owner>/<repo>`. Deeper paths like `/issues` or `/blob/main/…` and a trailing `.git` are removed. Links are skipped when:

- the owner is `sponsors`, `orgs` or `features` (GitHub pages, not repositories), or
- the page itself is on `github.com`. There the page *is* the repository, and its links are mostly GitHub's own menus.

The list is only a set of candidates. Choosing the official repository (or none) is up to whoever runs `add`. The `/add-tool` skill does this.

## Duplicate check

Before fetching anything, `inspect` and `add` call `ToolDatabase.find_duplicate`. It compares URLs after lowercasing them and removing the scheme, a leading `www.` and a trailing `/`. So `https://www.Example.com/app/` matches `http://example.com/app`. Query strings and fragments are ignored.

## Getting the thumbnail

`ThumbnailFetcher(name=…, url=…)` saves the thumbnail as `assets/thumbnails/<slug>.<ext>`.

The slug is the tool name with accents removed, lowercased, and limited to ASCII letters and digits ("Café Tools" → `cafetools`). If the name has none of those, the slug comes from the domain instead. `add` stops if a file with that slug already exists, whatever its extension.

`fetch(image=…)` picks its sources:

1. `--image` if given (a URL or a local path). The page isn't fetched at all.
2. Otherwise, the page's `image_candidates`.

It tries the sources in order and keeps the first one that `save` accepts. If none is accepted, it raises `RuntimeError("No usable thumbnail found…")`.

### Saving and validating

`save(source)`:

- **Local file:** the extension must be `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` or `.svg`. The file is copied as it is.
- **URL:** downloaded with the same headers and timeout as the page. The extension comes from the response's `Content-Type` (`image/png` → `.png`, and so on), not from the URL. This matters because CDNs often serve images from URLs with no extension or the wrong one. Any other content type, such as an HTML error page, is rejected.

The saved file is then read back with `Thumbnail.size`. If it can't be read, it's deleted and the source is rejected:

- Raster images are opened with Pillow.
- SVGs are parsed as XML and must have a `viewBox`. That's where their aspect ratio comes from.

### Rounding corners

`add` then calls `Thumbnail.round_corners()`:

- SVGs and GIFs are skipped (the GIF so it keeps its animation).
- Images with any transparent corner pixel are skipped. They're logos or icons with their own shape.
- Otherwise a rounded-rectangle alpha mask is drawn at 4× size and scaled down with Lanczos for smooth edges. The radius is set so the corners measure `CORNER_RADIUS` (20px) at the size the README shows the image, whatever its real resolution.
- WebPs are saved again as lossless WebP. Everything else is saved as PNG, so JPEGs become `.png` because JPEG has no transparency, and the original file is deleted.

If anything fails after the thumbnail is saved but before the entry reaches `tools_db.yml`, `add` deletes the thumbnail. Otherwise a leftover file would block the next attempt.

### Display size

GitHub strips CSS from READMEs, so a thumbnail's size is controlled only by its `width` attribute. `Thumbnail.display_width` scales each image to fit a 600×300 box. Raster images are never scaled up, while SVGs can be. If an image's size can't be read, it falls back to the full 600px.

## Adding the entry

The checks in `add` run in this order, and any failure stops `add` before it changes anything:

1. The URL isn't already in the library (see [Duplicate check](#duplicate-check)).
2. `--category` is one that's already in use, unless `--new-category` is passed.
3. With `--dry-run`, the entry is printed and nothing else happens. No thumbnail is fetched, so the `thumbnail` path ends in a placeholder `<ext>`.
4. No thumbnail with the same slug exists yet.

Next the thumbnail is fetched, saved and rounded, and the entry is written by `ToolDatabase.add`.

### Writing `tools_db.yml`

`Tool.to_yaml()` writes the entry in the same format as the hand-written ones:

- The fields are always in the order `name`, `url`, `source`, `thumbnail`, `category`, `description`. A missing source is written as `null`.
- Each single value goes through `yaml.safe_dump`, so it's quoted only when YAML needs it (for example, a name with a `: ` in it).
- The description is collapsed to single spaces and wrapped at 80 columns under a folded (`>`) block. Lines break only at spaces, never at hyphens or inside long words. That's because the folded style turns each line break back into a space, so a break inside "tree-shaking" or a URL would add one.

The entry is added to the end of the file as text, after one blank line. The file is never loaded and dumped again, so existing entries keep their exact formatting and comments.

Before anything is written, the whole updated text is parsed again with `yaml.safe_load`, and every entry is built as a `Tool(**entry)`. If the YAML is invalid, or an entry has a missing or misspelled field, this raises and the file is left as it was. `add` then deletes the thumbnail it saved.

## Generating the README

`add` ends by running the same code as `python -m toolib generate` (`ReadmeGenerator` in `toolib/readme.py`), which renders `README.md` again from scratch.

- **Order:** categories, and the tools in each one, are sorted alphabetically, ignoring case. The order of entries in `tools_db.yml` doesn't matter.
- **Anchors:** `AnchorRegistry` makes the same heading anchors GitHub does, so the Contents links work. It lowercases the text, drops punctuation and emoji, and turns spaces into dashes. A repeated anchor gets `-1`, `-2` and so on added. Anchors are assigned in the order the headings appear, and the template's own headings (`Introduction`, `Contents`, `Library`, the title) are reserved first. That keeps the numbering the same as GitHub's, even when a tool has the same name as a category.
- **Thumbnail width:** each image gets its `display_width` (see [Display size](#display-size)).
- **Template:** `toolib/templates/README.md.jinja` gets the sections, the tool count, and an "updated" date (the current month in UTC). The date changes every time the README is generated, even when no tools changed.
