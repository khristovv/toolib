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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

from generate_readme import ROOT, ReadmeGenerator, Thumbnail, ToolDatabase

THUMBNAILS_DIR = ROOT / "assets" / "thumbnails"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


class PageInspector:
    """Metadata from a tool's web page. Raises requests.RequestException if the page can't be fetched."""

    IMAGE_META_KEYS = ("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    # github.com/<first>/<second> links that aren't repositories.
    NON_REPO_OWNERS = ("sponsors", "orgs", "features")

    def __init__(self, url: str):
        self.url = url
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        self.soup = BeautifulSoup(resp.text, "html.parser")

    def meta(self, *keys: str) -> str | None:
        """Content of the first of the given meta tags that's present."""
        for key in keys:
            tag = self.soup.find("meta", property=key) or self.soup.find("meta", attrs={"name": key})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    @property
    def title(self) -> str | None:
        title = self.soup.title
        return title.string.strip() if title and title.string else None

    @property
    def image_candidates(self) -> list[str]:
        candidates = []
        for key in self.IMAGE_META_KEYS:
            content = self.meta(key)
            if content:
                absolute = urljoin(self.url, content)
                if absolute not in candidates:
                    candidates.append(absolute)
        return candidates

    @property
    def github_links(self) -> list[str]:
        links = []
        for a in self.soup.find_all("a", href=True):
            match = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+)", a["href"])
            if match and match.group(1) not in self.NON_REPO_OWNERS:
                link = f"https://github.com/{match.group(1)}/{match.group(2).removesuffix('.git')}"
                if link not in links:
                    links.append(link)
        return links

    def summary(self) -> dict:
        return {
            "title": self.title,
            "site_name": self.meta("og:site_name"),
            "description": self.meta("og:description", "description", "twitter:description"),
            "image_candidates": self.image_candidates,
            "github_links": self.github_links,
        }


class ThumbnailFetcher:
    """Finds and saves a tool's thumbnail as assets/thumbnails/<slug>.<ext>."""

    IMAGE_EXTENSIONS = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }

    def __init__(self, *, name: str, directory: Path = THUMBNAILS_DIR):
        self.slug = re.sub(r"[^a-z0-9]+", "", name.lower())
        self.directory = directory

    def existing(self) -> Path | None:
        return next(iter(self.directory.glob(f"{self.slug}.*")), None)

    def fetch(self, *, url: str, image: str | None, screenshot: bool) -> Thumbnail:
        """Try --image, then the page's image meta tags, then (optionally) a screenshot."""
        sources = [image] if image else []
        if not image:
            try:
                sources += PageInspector(url).image_candidates
            except requests.RequestException as e:
                print(f"  ⚠️  Could not fetch {url}: {e}")

        for source in sources:
            try:
                print(f"  Downloading {source}...")
                return Thumbnail(self.download(source))
            except (requests.RequestException, ValueError) as e:
                print(f"  ⚠️  {e}")

        if screenshot:
            print(f"  Taking screenshot of {url}...")
            return Thumbnail(self.screenshot(url))

        raise RuntimeError("No usable thumbnail found. Pass --image <url-or-path> or --screenshot.")

    def download(self, source: str) -> Path:
        """Download (or copy, for a local path) an image."""
        local = Path(source).expanduser()
        if local.is_file():
            dest = self.directory / f"{self.slug}{local.suffix.lower()}"
            shutil.copyfile(local, dest)
            return dest

        resp = requests.get(source, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        extension = self.IMAGE_EXTENSIONS.get(content_type)
        if not extension:
            raise ValueError(f"{source} returned {content_type or 'no content type'}, not an image")

        dest = self.directory / f"{self.slug}{extension}"
        dest.write_bytes(resp.content)
        return dest

    def screenshot(self, url: str) -> Path:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright is not installed: pip install playwright && playwright install chromium")

        dest = self.directory / f"{self.slug}.png"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 630})
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=str(dest))
            browser.close()
        return dest


@dataclass
class ToolEntry:
    name: str
    url: str
    source: str | None
    thumbnail: str
    category: str
    description: str

    def to_yaml(self) -> str:
        wrapped = textwrap.fill(
            " ".join(self.description.split()), width=80, initial_indent="    ", subsequent_indent="    "
        )
        return (
            f"- name: {self._scalar(self.name)}\n"
            f"  url: {self._scalar(self.url)}\n"
            f"  source: {self._scalar(self.source)}\n"
            f"  thumbnail: {self._scalar(self.thumbnail)}\n"
            f"  category: {self._scalar(self.category)}\n"
            f"  description: >\n"
            f"{wrapped}\n"
        )

    @staticmethod
    def _scalar(value: str | None) -> str:
        """Render a single value as YAML, quoting only when needed."""
        if value is None:
            return "null"
        return yaml.safe_dump(value, allow_unicode=True, width=1000).removesuffix("\n...\n").strip()


def cmd_inspect(args: argparse.Namespace) -> None:
    database = ToolDatabase()
    duplicate = database.find_duplicate(args.url)
    info = {
        "url": args.url,
        "duplicate_of": duplicate["name"] if duplicate else None,
        "existing_categories": sorted(database.categories),
    }
    try:
        info |= PageInspector(args.url).summary()
    except requests.RequestException as e:
        info["fetch_error"] = str(e)

    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_add(args: argparse.Namespace) -> None:
    database = ToolDatabase()

    duplicate = database.find_duplicate(args.url)
    if duplicate:
        sys.exit(f"❌ {args.url} is already in the library as '{duplicate['name']}'.")

    if args.category not in database.categories and not args.new_category:
        sys.exit(
            f"❌ Unknown category '{args.category}'. Existing: {', '.join(sorted(database.categories))}.\n"
            "   Pass --new-category to create it."
        )

    fetcher = ThumbnailFetcher(name=args.name)
    existing = fetcher.existing()
    if existing and not args.dry_run:
        sys.exit(f"❌ Thumbnail {existing.relative_to(ROOT)} already exists.")

    if args.dry_run:
        thumbnail = f"assets/thumbnails/{fetcher.slug}.<ext>"
    else:
        try:
            saved = fetcher.fetch(url=args.url, image=args.image, screenshot=args.screenshot)
        except RuntimeError as e:
            sys.exit(f"❌ {e}")
        thumbnail = saved.round_corners().path.relative_to(ROOT).as_posix()
        print(f"  🖼️  Saved {thumbnail}")

    entry = ToolEntry(
        name=args.name,
        url=args.url,
        source=args.source,
        thumbnail=thumbnail,
        category=args.category,
        description=args.description,
    )

    if args.dry_run:
        print(entry.to_yaml())
        return

    database.append(entry.to_yaml())
    print(f"  📝 Added '{args.name}' to {database.path.name}")
    ReadmeGenerator(database=database).generate()


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
