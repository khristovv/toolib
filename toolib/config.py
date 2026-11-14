"""Paths and settings shared across the package."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent

TOOLS_FILE = ROOT / "tools_db.yml"
OUTPUT_FILE = ROOT / "README.md"
THUMBNAILS_DIR = ROOT / "assets" / "thumbnails"
TEMPLATES_DIR = PACKAGE_DIR / "templates"
TEMPLATE_FILE = "README.md.jinja"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
