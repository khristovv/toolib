"""Thumbnail images: finding and saving them, sizing them for the README, and rounding their corners."""

import re
import shutil
from pathlib import Path
from xml.etree import ElementTree

import requests
from PIL import Image, ImageChops, ImageDraw

from .config import HEADERS, ROOT, THUMBNAILS_DIR
from .page import PageInspector


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


class ThumbnailFetcher:
    """Finds and saves a tool's thumbnail as assets/thumbnails/<slug>.<ext>."""

    IMAGE_EXTENSIONS = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }

    def __init__(self, *, name: str, directory: Path = THUMBNAILS_DIR):
        self.slug = re.sub(r"[^a-z0-9]+", "", name.lower())
        self.directory = directory

    def existing(self) -> Path | None:
        return next(iter(self.directory.glob(f"{self.slug}.*")), None)

    def fetch(self, *, url: str, image: str | None, screenshot: bool) -> Thumbnail:
        """Try --image, then the page's image meta tags, then (optionally) a screenshot."""
        sources = [image] if image else []
        if not image:
            try:
                sources += PageInspector(url).image_candidates
            except requests.RequestException as e:
                print(f"  ⚠️  Could not fetch {url}: {e}")

        for source in sources:
            try:
                print(f"  Downloading {source}...")
                return Thumbnail(self.download(source))
            except (requests.RequestException, ValueError) as e:
                print(f"  ⚠️  {e}")

        if screenshot:
            print(f"  Taking screenshot of {url}...")
            return Thumbnail(self.screenshot(url))

        raise RuntimeError("No usable thumbnail found. Pass --image <url-or-path> or --screenshot.")

    def download(self, source: str) -> Path:
        """Download (or copy, for a local path) an image."""
        local = Path(source).expanduser()
        if local.is_file():
            dest = self.directory / f"{self.slug}{local.suffix.lower()}"
            shutil.copyfile(local, dest)
            return dest

        resp = requests.get(source, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        extension = self.IMAGE_EXTENSIONS.get(content_type)
        if not extension:
            raise ValueError(f"{source} returned {content_type or 'no content type'}, not an image")

        dest = self.directory / f"{self.slug}{extension}"
        dest.write_bytes(resp.content)

        return dest

    def screenshot(self, url: str) -> Path:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright is not installed: pip install playwright && playwright install chromium")

        dest = self.directory / f"{self.slug}.png"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 630})
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=str(dest))
            browser.close()

        return dest
