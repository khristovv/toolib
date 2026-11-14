"""
Toolib command line. Run from the repository root.

Usage:
    python -m toolib generate
    python -m toolib inspect <url>
    python -m toolib add <url> --name NAME --category CATEGORY --description TEXT
                         [--source URL] [--image URL_OR_PATH] [--screenshot]
                         [--new-category] [--dry-run]

generate  Renders README.md from tools_db.yml.
inspect   Prints a page's metadata as JSON (title, description, image candidates,
          GitHub links), plus duplicate status and the existing categories.
add       Downloads the thumbnail, appends the entry to tools_db.yml, and
          regenerates README.md.

Thumbnail lookup order: --image, og:image, twitter:image, then a Playwright
screenshot (only with --screenshot; needs `pip install playwright` and
`playwright install chromium`).

Raster thumbnails with solid corners get rounded corners cut into them (JPEGs
become PNGs, since they can't be transparent).
"""

import argparse
import json
import sys

import requests

from .config import ROOT
from .database import ToolDatabase, ToolEntry
from .page import PageInspector
from .readme import ReadmeGenerator
from .thumbnail import ThumbnailFetcher


def cmd_generate(args: argparse.Namespace) -> None:
    ReadmeGenerator(database=ToolDatabase()).generate()


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
    parser = argparse.ArgumentParser(
        prog="python -m toolib", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Render README.md from tools_db.yml")
    generate_parser.set_defaults(func=cmd_generate)

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
