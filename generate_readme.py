"""
generate_readme.py
Reads tools_db.yml and renders README.md from README.md.jinja.

Usage:
    python generate_readme.py
"""

import yaml
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
TOOLS_FILE = ROOT / "tools_db.yml"
TEMPLATE_FILE = "README.md.jinja"
OUTPUT_FILE = ROOT / "README.md"


def load_tools(*, path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def group_by_category(*, tools: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)

    for tool in tools:
        grouped[tool["category"]].append(tool)

    return {
        category: sorted(grouped[category], key=lambda tool: tool["name"].casefold())
        for category in sorted(grouped, key=str.casefold)
    }


def render(*, tools_by_category: dict, updated: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(ROOT)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    template = env.get_template(TEMPLATE_FILE)
    return template.render(
        tools_by_category=tools_by_category,
        updated=updated,
    )


def generate() -> None:
    tools = load_tools(path=TOOLS_FILE)
    tools_by_category = group_by_category(tools=tools)
    updated = datetime.now(timezone.utc).strftime("%B %Y")
    output = render(tools_by_category=tools_by_category, updated=updated)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ README.md generated with {len(tools)} tools across {len(tools_by_category)} categories.")


if __name__ == "__main__":
    generate()
