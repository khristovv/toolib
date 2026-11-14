"""The tool database (tools_db.yml) and the tools in it."""

import textwrap
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

import yaml

from .config import TOOLS_FILE


@dataclass
class Tool:
    """One tool in tools_db.yml."""

    name: str
    url: str
    source: str | None
    thumbnail: str
    category: str
    description: str

    def to_yaml(self) -> str:
        """The tool as a tools_db.yml entry, formatted the same way as the hand-written ones."""
        # Only break at spaces: the folded (>) style turns each line break back into a
        # space, so a break inside "tree-shaking" or a URL would add one.
        wrapped = textwrap.fill(
            " ".join(self.description.split()),
            width=80,
            initial_indent="    ",
            subsequent_indent="    ",
            break_on_hyphens=False,
            break_long_words=False,
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


class ToolDatabase:
    """The tools listed in tools_db.yml."""

    def __init__(self):
        self.path = TOOLS_FILE
        self.tools = self._parse(self.path.read_text(encoding="utf-8"))

    @property
    def categories(self) -> set[str]:
        return {tool.category for tool in self.tools}

    def find_duplicate(self, url: str) -> Tool | None:
        target = self._normalize_url(url)
        return next((tool for tool in self.tools if self._normalize_url(tool.url) == target), None)

    def grouped_by_category(self) -> dict[str, list[Tool]]:
        """Tools grouped by category, with categories and tools sorted alphabetically."""
        grouped = defaultdict(list)

        for tool in self.tools:
            grouped[tool.category].append(tool)

        return {
            category: sorted(grouped[category], key=lambda tool: tool.name.casefold())
            for category in sorted(grouped, key=str.casefold)
        }

    def add(self, tool: Tool) -> None:
        """Append the tool to tools_db.yml as text, so existing entries keep their formatting."""
        updated = self.path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + tool.to_yaml()
        self.tools = self._parse(updated)  # Raises before writing if the result isn't valid.
        self.path.write_text(updated, encoding="utf-8")

    @staticmethod
    def _parse(text: str) -> list[Tool]:
        # Tool(**entry) also catches entries with missing or misspelled fields.
        return [Tool(**entry) for entry in yaml.safe_load(text)]

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url.lower())
        host = parsed.netloc.removeprefix("www.")
        return f"{host}{parsed.path.rstrip('/')}"
