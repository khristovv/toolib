"""
add_tool.py
Adds a tool to tools_db.yml, downloads its thumbnail, and regenerates README.md.

Usage:
    python scripts/add_tool.py inspect <url>
    python scripts/add_tool.py add <url> --name NAME --category CATEGORY --description TEXT
                               [--source URL] [--image URL_OR_PATH] [--screenshot]
                               [--new-category] [--dry-run]

Thumbnail lookup order: --image, og:image, twitter:image, then a Playwright
screenshot (only with --screenshot; needs `pip install playwright` and
`playwright install chromium`).

Raster thumbnails with solid corners get rounded corners cut into them (JPEGs
become PNGs, since they can't be transparent).
"""

import argparse
import json
import re
import shutil
import sys
import textwrap
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageDraw

from generate_readme import ROOT, TOOLS_FILE, generate, load_tools, thumbnail_width

THUMBNAILS_DIR = ROOT / "assets" / "thumbnails"
# Corner radius as it appears in the README, so every thumbnail looks the same
# regardless of its real size.
CORNER_RADIUS = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.lower())
    host = parsed.netloc.removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_duplicate(*, url: str, tools: list[dict]) -> dict | None:
    target = normalize_url(url)
    for tool in tools:
        if normalize_url(tool["url"]) == target:
            return tool
    return None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def meta_content(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def image_candidates(*, soup: BeautifulSoup, url: str) -> list[str]:
    candidates = []
    for key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        content = meta_content(soup, key)
        if content:
            absolute = urljoin(url, content)
            if absolute not in candidates:
                candidates.append(absolute)
    return candidates


def github_links(*, soup: BeautifulSoup) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        match = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+)", a["href"])
        if match and match.group(1) not in ("sponsors", "orgs", "features"):
            link = f"https://github.com/{match.group(1)}/{match.group(2).removesuffix('.git')}"
            if link not in links:
                links.append(link)
    return links


def download_image(*, source: str, slug: str) -> Path:
    """Download (or copy) an image into assets/thumbnails/<slug>.<ext>."""
    local = Path(source).expanduser()
    if local.is_file():
        dest = THUMBNAILS_DIR / f"{slug}{local.suffix.lower()}"
        shutil.copyfile(local, dest)
        return dest

    resp = requests.get(source, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    extension = IMAGE_EXTENSIONS.get(content_type)
    if not extension:
        raise ValueError(f"{source} returned {content_type or 'no content type'}, not an image")

    dest = THUMBNAILS_DIR / f"{slug}{extension}"
    dest.write_bytes(resp.content)
    return dest


def take_screenshot(*, url: str, slug: str) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright is not installed: pip install playwright && playwright install chromium")

    dest = THUMBNAILS_DIR / f"{slug}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.screenshot(path=str(dest))
        browser.close()
    return dest


def fetch_thumbnail(*, url: str, slug: str, image: str | None, screenshot: bool) -> Path:
    sources = [image] if image else []
    if not image:
        try:
            sources += image_candidates(soup=fetch_page(url), url=url)
        except requests.RequestException as e:
            print(f"  ⚠️  Could not fetch {url}: {e}")

    for source in sources:
        try:
            print(f"  Downloading {source}...")
            return download_image(source=source, slug=slug)
        except (requests.RequestException, ValueError) as e:
            print(f"  ⚠️  {e}")

    if screenshot:
        print(f"  Taking screenshot of {url}...")
        return take_screenshot(url=url, slug=slug)

    raise RuntimeError("No usable thumbnail found. Pass --image <url-or-path> or --screenshot.")


def round_corners(*, path: Path) -> Path:
    """Cut rounded corners into a raster thumbnail and return its (possibly new) path.

    SVGs and GIFs are left alone, as are images whose corners are already
    transparent (icons and logos that have their own shape).
    """
    if path.suffix.lower() in (".svg", ".gif"):
        return path

    with Image.open(path) as image:
        image = image.convert("RGBA")
    width, height = image.size
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    if any(image.getpixel(corner)[3] < 255 for corner in corners):
        return path

    # Draw the mask at 4x and scale it down for smooth, anti-aliased edges.
    radius = CORNER_RADIUS * width / thumbnail_width(path=path)
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1), radius=round(radius * scale), fill=255
    )
    mask = mask.resize((width, height), Image.LANCZOS)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))

    if path.suffix.lower() == ".webp":
        image.save(path, lossless=True)
        return path

    dest = path.with_suffix(".png")
    image.save(dest, optimize=True)
    if dest != path:
        path.unlink()
    return dest


def yaml_scalar(value: str | None) -> str:
    """Render a single value as YAML, quoting only when needed."""
    if value is None:
        return "null"
    return yaml.safe_dump(value, allow_unicode=True, width=1000).removesuffix("\n...\n").strip()


def format_entry(*, name: str, url: str, source: str | None, thumbnail: str, category: str, description: str) -> str:
    wrapped = textwrap.fill(" ".join(description.split()), width=80, initial_indent="    ", subsequent_indent="    ")
    return (
        f"- name: {yaml_scalar(name)}\n"
        f"  url: {yaml_scalar(url)}\n"
        f"  source: {yaml_scalar(source)}\n"
        f"  thumbnail: {yaml_scalar(thumbnail)}\n"
        f"  category: {yaml_scalar(category)}\n"
        f"  description: >\n"
        f"{wrapped}\n"
    )


def append_entry(*, entry: str, path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    updated = original.rstrip("\n") + "\n\n" + entry
    path.write_text(updated, encoding="utf-8")

    try:
        yaml.safe_load(updated)
    except yaml.YAMLError:
        path.write_text(original, encoding="utf-8")
        raise


def cmd_inspect(args: argparse.Namespace) -> None:
    tools = load_tools(path=TOOLS_FILE)
    duplicate = find_duplicate(url=args.url, tools=tools)
    info = {
        "url": args.url,
        "duplicate_of": duplicate["name"] if duplicate else None,
        "existing_categories": sorted({tool["category"] for tool in tools}),
    }
    try:
        soup = fetch_page(args.url)
        info |= {
            "title": soup.title.string.strip() if soup.title and soup.title.string else None,
            "site_name": meta_content(soup, "og:site_name"),
            "description": meta_content(soup, "og:description", "description", "twitter:description"),
            "image_candidates": image_candidates(soup=soup, url=args.url),
            "github_links": github_links(soup=soup),
        }
    except requests.RequestException as e:
        info["fetch_error"] = str(e)

    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_add(args: argparse.Namespace) -> None:
    tools = load_tools(path=TOOLS_FILE)

    duplicate = find_duplicate(url=args.url, tools=tools)
    if duplicate:
        sys.exit(f"❌ {args.url} is already in the library as '{duplicate['name']}'.")

    categories = {tool["category"] for tool in tools}
    if args.category not in categories and not args.new_category:
        sys.exit(
            f"❌ Unknown category '{args.category}'. Existing: {', '.join(sorted(categories))}.\n"
            "   Pass --new-category to create it."
        )

    slug = slugify(args.name)
    existing = list(THUMBNAILS_DIR.glob(f"{slug}.*"))
    if existing and not args.dry_run:
        sys.exit(f"❌ Thumbnail {existing[0].relative_to(ROOT)} already exists.")

    if args.dry_run:
        thumbnail = f"assets/thumbnails/{slug}.<ext>"
    else:
        try:
            thumbnail = fetch_thumbnail(url=args.url, slug=slug, image=args.image, screenshot=args.screenshot)
        except RuntimeError as e:
            sys.exit(f"❌ {e}")
        thumbnail = round_corners(path=thumbnail).relative_to(ROOT).as_posix()
        print(f"  🖼️  Saved {thumbnail}")

    entry = format_entry(
        name=args.name,
        url=args.url,
        source=args.source,
        thumbnail=thumbnail,
        category=args.category,
        description=args.description,
    )

    if args.dry_run:
        print(entry)
        return

    append_entry(entry=entry, path=TOOLS_FILE)
    print(f"  📝 Added '{args.name}' to {TOOLS_FILE.name}")
    generate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Print page metadata as JSON")
    inspect_parser.add_argument("url")
    inspect_parser.set_defaults(func=cmd_inspect)

    add_parser = subparsers.add_parser("add", help="Add a tool and regenerate README.md")
    add_parser.add_argument("url")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--category", required=True)
    add_parser.add_argument("--description", required=True)
    add_parser.add_argument("--source", default=None, help="Source code URL (omit for closed source)")
    add_parser.add_argument("--image", default=None, help="Thumbnail URL or local path, skips og:image lookup")
    add_parser.add_argument("--screenshot", action="store_true", help="Fall back to a Playwright screenshot")
    add_parser.add_argument("--new-category", action="store_true", help="Allow a category not used yet")
    add_parser.add_argument("--dry-run", action="store_true", help="Print the entry without writing anything")
    add_parser.set_defaults(func=cmd_add)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
