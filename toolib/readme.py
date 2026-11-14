"""Rendering README.md from the tool database and the Jinja2 template."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from .config import OUTPUT_FILE, ROOT, TEMPLATE_FILE, TEMPLATES_DIR
from .database import Tool, ToolDatabase
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


@dataclass
class ToolSection:
    """A tool as the README shows it: the tool plus its heading anchor and thumbnail width."""

    tool: Tool
    anchor: str
    thumbnail_width: int


@dataclass
class CategorySection:
    name: str
    anchor: str
    tools: list[ToolSection]


class ReadmeGenerator:
    """Renders README.md from the tool database and the Jinja2 template."""

    # Headings that come before the library in the template.
    RESERVED_ANCHORS = {"toolib-", "introduction", "contents", "library"}

    def __init__(self, *, database: ToolDatabase):
        self.database = database

    def sections(self) -> list[CategorySection]:
        """The README's category sections, in order. Anchors are handed out in the
        same order as the headings appear, so repeats match GitHub's numbering."""
        anchors = AnchorRegistry(reserved=self.RESERVED_ANCHORS)
        sections = []

        for category, tools in self.database.grouped_by_category().items():
            category_anchor = anchors.anchor(category)
            tool_sections = [
                ToolSection(
                    tool=tool,
                    anchor=anchors.anchor(tool.name),
                    thumbnail_width=Thumbnail(ROOT / tool.thumbnail).display_width,
                )
                for tool in tools
            ]
            sections.append(CategorySection(name=category, anchor=category_anchor, tools=tool_sections))

        return sections

    def render(self) -> str:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        return env.get_template(TEMPLATE_FILE).render(
            sections=self.sections(),
            tool_count=len(self.database.tools),
            updated=datetime.now(timezone.utc).strftime("%B %Y"),
        )

    def generate(self) -> None:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(self.render())

        print(
            f"✅ README.md generated with {len(self.database.tools)} tools "
            f"across {len(self.database.categories)} categories."
        )
