"""
generate_readme.py
Reads tools_db.yml and renders README.md from README.md.jinja.

Usage:
    python generate_readme.py
"""

import re
import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image
from xml.etree import ElementTree
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
TOOLS_FILE = ROOT / "tools_db.yml"
TEMPLATE_FILE = "README.md.jinja"
OUTPUT_FILE = ROOT / "README.md"

# Thumbnails are scaled to fit this box. GitHub strips CSS from READMEs, so the
# only way to cap the height is to pick the right width for each image.
THUMBNAIL_MAX_WIDTH = 600
THUMBNAIL_MAX_HEIGHT = 300


def load_tools(*, path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def svg_size(*, path: Path) -> tuple[float, float]:
    # SVGs scale freely, so only the viewBox aspect ratio matters.
    view_box = ElementTree.parse(path).getroot().get("viewBox")
    if not view_box:
        raise ValueError("SVG has no viewBox")

    _, _, width, height = (float(v) for v in view_box.replace(",", " ").split())
    return width, height


def image_size(*, path: Path) -> tuple[float, float]:
    # Pillow can't read SVGs.
    if path.suffix.lower() == ".svg":
        return svg_size(path=path)
    with Image.open(path) as image:
        return image.size


def thumbnail_width(*, path: Path) -> int:
    """Width that fits the image in the thumbnail box without upscaling raster images."""
    try:
        width, height = image_size(path=path)
    except (OSError, ValueError, ElementTree.ParseError) as e:
        print(f"  ⚠️  Couldn't read the size of {path.relative_to(ROOT)} ({e}), using full width")
        return THUMBNAIL_MAX_WIDTH

    scale = min(THUMBNAIL_MAX_WIDTH / width, THUMBNAIL_MAX_HEIGHT / height)
    if path.suffix.lower() != ".svg":
        scale = min(scale, 1)

    return round(width * scale)


def group_by_category(*, tools: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)

    for tool in tools:
        grouped[tool["category"]].append(tool)

    return {
        category: sorted(grouped[category], key=lambda tool: tool["name"].casefold())
        for category in sorted(grouped, key=str.casefold)
    }


def github_anchor(text: str, *, used: set[str]) -> str:
    """Anchor GitHub generates for a heading: lowercase, punctuation and emoji
    dropped, spaces turned into dashes, and -1, -2, ... appended to repeats."""
    base = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
    anchor, n = base, 0

    while anchor in used:
        n += 1
        anchor = f"{base}-{n}"

    used.add(anchor)
    return anchor


def add_anchors(*, tools_by_category: dict[str, list[dict]]) -> dict[str, str]:
    """Set each tool's anchor and return each category's, in README heading order."""
    # Headings that come before the library in the template.
    used = {"toolib-", "introduction", "contents", "library"}
    category_anchors = {}

    for category, tools in tools_by_category.items():
        category_anchors[category] = github_anchor(category, used=used)

        for tool in tools:
            tool["anchor"] = github_anchor(tool["name"], used=used)

    return category_anchors


def render(*, tools_by_category: dict, category_anchors: dict, updated: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(ROOT)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    template = env.get_template(TEMPLATE_FILE)
    return template.render(
        tools_by_category=tools_by_category,
        category_anchors=category_anchors,
        updated=updated,
    )


def generate() -> None:
    tools = load_tools(path=TOOLS_FILE)
    for tool in tools:
        tool["thumbnail_width"] = thumbnail_width(path=ROOT / tool["thumbnail"])

    tools_by_category = group_by_category(tools=tools)
    category_anchors = add_anchors(tools_by_category=tools_by_category)
    updated = datetime.now(timezone.utc).strftime("%B %Y")
    output = render(tools_by_category=tools_by_category, category_anchors=category_anchors, updated=updated)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ README.md generated with {len(tools)} tools across {len(tools_by_category)} categories.")


if __name__ == "__main__":
    generate()
