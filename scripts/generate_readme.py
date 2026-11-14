"""
generate_readme.py
Reads tools_db.yml and renders README.md from README.md.jinja.

Usage:
    python scripts/generate_readme.py
"""

import re
import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageChops, ImageDraw
from xml.etree import ElementTree
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
TOOLS_FILE = ROOT / "tools_db.yml"
TEMPLATE_FILE = "README.md.jinja"
OUTPUT_FILE = ROOT / "README.md"


class ToolDatabase:
    """The tools listed in tools_db.yml."""

    def __init__(self, *, path: Path = TOOLS_FILE):
        self.path = path
        with open(path, "r", encoding="utf-8") as f:
            self.tools: list[dict] = yaml.safe_load(f)

    @property
    def categories(self) -> set[str]:
        return {tool["category"] for tool in self.tools}

    def find_duplicate(self, url: str) -> dict | None:
        target = self._normalize_url(url)
        return next((tool for tool in self.tools if self._normalize_url(tool["url"]) == target), None)

    def grouped_by_category(self) -> dict[str, list[dict]]:
        """Tools grouped by category, with categories and tools sorted alphabetically."""
        grouped = defaultdict(list)

        for tool in self.tools:
            grouped[tool["category"]].append(tool)

        return {
            category: sorted(grouped[category], key=lambda tool: tool["name"].casefold())
            for category in sorted(grouped, key=str.casefold)
        }

    def append(self, entry: str) -> None:
        """Append an already formatted YAML entry as text, so existing entries keep their formatting."""
        updated = self.path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + entry
        self.tools = yaml.safe_load(updated)  # Raises before writing if the result isn't valid YAML.
        self.path.write_text(updated, encoding="utf-8")

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url.lower())
        host = parsed.netloc.removeprefix("www.")
        return f"{host}{parsed.path.rstrip('/')}"


class Thumbnail:
    """A thumbnail image and how it's displayed in the README."""

    # Thumbnails are scaled to fit this box. GitHub strips CSS from READMEs, so the
    # only way to cap the height is to pick the right width for each image.
    MAX_WIDTH = 600
    MAX_HEIGHT = 300
    # Corner radius as it appears in the README, so every thumbnail looks the same
    # regardless of its real size.
    CORNER_RADIUS = 20

    def __init__(self, path: Path):
        self.path = path

    @property
    def is_svg(self) -> bool:
        return self.path.suffix.lower() == ".svg"

    @property
    def size(self) -> tuple[float, float]:
        # Pillow can't read SVGs, and they scale freely, so only their viewBox aspect ratio matters.
        if self.is_svg:
            view_box = ElementTree.parse(self.path).getroot().get("viewBox")
            if not view_box:
                raise ValueError("SVG has no viewBox")

            _, _, width, height = (float(v) for v in view_box.replace(",", " ").split())
            return width, height

        with Image.open(self.path) as image:
            return image.size

    @property
    def display_width(self) -> int:
        """Width that fits the image in the thumbnail box without upscaling raster images."""
        try:
            width, height = self.size
        except (OSError, ValueError, ElementTree.ParseError) as e:
            print(f"  ⚠️  Couldn't read the size of {self.path.relative_to(ROOT)} ({e}), using full width")
            return self.MAX_WIDTH

        scale = min(self.MAX_WIDTH / width, self.MAX_HEIGHT / height)
        if not self.is_svg:
            scale = min(scale, 1)

        return round(width * scale)

    def round_corners(self) -> "Thumbnail":
        """Cut rounded corners into a raster thumbnail and return it (JPEGs become PNGs).

        SVGs and GIFs are left alone, as are images whose corners are already
        transparent (icons and logos that have their own shape).
        """
        if self.path.suffix.lower() in (".svg", ".gif"):
            return self

        with Image.open(self.path) as image:
            image = image.convert("RGBA")

        width, height = image.size
        corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
        if any(image.getpixel(corner)[3] < 255 for corner in corners):
            return self

        # Draw the mask at 4x and scale it down for smooth, anti-aliased edges.
        radius = self.CORNER_RADIUS * width / self.display_width
        scale = 4
        mask = Image.new("L", (width * scale, height * scale), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width * scale - 1, height * scale - 1), radius=round(radius * scale), fill=255
        )
        mask = mask.resize((width, height), Image.LANCZOS)
        image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))

        if self.path.suffix.lower() == ".webp":
            image.save(self.path, lossless=True)
            return self

        dest = self.path.with_suffix(".png")
        image.save(dest, optimize=True)
        if dest != self.path:
            self.path.unlink()

        return Thumbnail(dest)


class AnchorRegistry:
    """Hands out the anchors GitHub generates for headings, in document order."""

    def __init__(self, *, reserved: set[str] = frozenset()):
        self.used = set(reserved)

    def anchor(self, text: str) -> str:
        """Lowercase, punctuation and emoji dropped, spaces turned into dashes,
        and -1, -2, ... appended to repeats."""
        base = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        anchor, n = base, 0

        while anchor in self.used:
            n += 1
            anchor = f"{base}-{n}"

        self.used.add(anchor)
        return anchor


class ReadmeGenerator:
    """Renders README.md from the tool database and the Jinja2 template."""

    # Headings that come before the library in the template.
    RESERVED_ANCHORS = {"toolib-", "introduction", "contents", "library"}

    def __init__(self, *, database: ToolDatabase, template_dir: Path = SCRIPTS_DIR, output: Path = OUTPUT_FILE):
        self.database = database
        self.template_dir = template_dir
        self.output = output

    def render(self) -> str:
        tools_by_category = self.database.grouped_by_category()
        anchors = AnchorRegistry(reserved=self.RESERVED_ANCHORS)
        category_anchors = {}

        for category, tools in tools_by_category.items():
            category_anchors[category] = anchors.anchor(category)

            for tool in tools:
                tool["anchor"] = anchors.anchor(tool["name"])
                tool["thumbnail_width"] = Thumbnail(ROOT / tool["thumbnail"]).display_width

        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        return env.get_template(TEMPLATE_FILE).render(
            tools_by_category=tools_by_category,
            category_anchors=category_anchors,
            updated=datetime.now(timezone.utc).strftime("%B %Y"),
        )

    def generate(self) -> None:
        with open(self.output, "w", encoding="utf-8") as f:
            f.write(self.render())

        print(
            f"✅ README.md generated with {len(self.database.tools)} tools "
            f"across {len(self.database.categories)} categories."
        )


if __name__ == "__main__":
    ReadmeGenerator(database=ToolDatabase()).generate()
