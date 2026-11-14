"""Rendering README.md from the tool database and the Jinja2 template."""

import re
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from .config import OUTPUT_FILE, ROOT, TEMPLATE_FILE, TEMPLATES_DIR
from .database import ToolDatabase
from .thumbnail import Thumbnail


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

    def __init__(self, *, database: ToolDatabase):
        self.database = database

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
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
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
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(self.render())

        print(
            f"✅ README.md generated with {len(self.database.tools)} tools "
            f"across {len(self.database.categories)} categories."
        )
