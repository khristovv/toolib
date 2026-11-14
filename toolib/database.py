"""The tool database (tools_db.yml) and the format of its entries."""

import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .config import TOOLS_FILE


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


@dataclass
class ToolEntry:
    """One tool, formatted the same way as the hand-written entries in tools_db.yml."""

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
