"""
generate_readme.py
Reads tools_db.yml and renders README.md from README.md.jinja.
Automatically fetches and caches og:image URLs for tools that don't have one yet.

Usage:
    python generate_readme.py
"""

import yaml
import requests
from bs4 import BeautifulSoup
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


def save_tools(*, tools: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(tools, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def fetch_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("meta", property="og:image")
        if tag:
            return tag.get("content")
    except Exception:
        pass
    return None


def populate_og_images(*, tools: list[dict], path: Path) -> None:
    """Fetch og:image for any tool missing it and save back to YAML."""
    updated = False
    for tool in tools:
        if "og_image" not in tool:
            print(f"  Fetching og:image for {tool['name']}...")
            tool["og_image"] = fetch_og_image(tool["url"])
            print(f"    → {tool['og_image'] or 'not found'}")
            updated = True

    if updated:
        save_tools(tools=tools, path=path)


def group_by_category(*, tools: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)

    for tool in tools:
        grouped[tool["category"]].append(tool)

    return dict(grouped)


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


def main():
    tools = load_tools(path=TOOLS_FILE)
    populate_og_images(tools=tools, path=TOOLS_FILE)
    tools_by_category = group_by_category(tools=tools)
    updated = datetime.now(timezone.utc).strftime("%B %Y")
    output = render(tools_by_category=tools_by_category, updated=updated)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ README.md generated with {len(tools)} tools across {len(tools_by_category)} categories.")


if __name__ == "__main__":
    main()
