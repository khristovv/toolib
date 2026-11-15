"""Thumbnail images: finding and saving them, sizing them for the README, and rounding their corners."""

import re
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from PIL import Image, ImageChops, ImageDraw

from .config import HEADERS, THUMBNAILS_DIR
from .page import PageInspector

# Image types a thumbnail can be, by the Content-Type a server sends for them.
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
IMAGE_SUFFIXES = {*IMAGE_TYPES.values(), ".jpeg"}


class Thumbnail:
    """A thumbnail image and how it's displayed in the README."""

    # Thumbnails are scaled to fit this box. GitHub strips CSS from READMEs, so the
    # only way to cap the height is to pick the right width for each image.
    MAX_WIDTH = 600
    MAX_HEIGHT = 300
    # Corner radius as it appears in the README, so every thumbnail looks the same
    # regardless of its real size.
    CORNER_RADIUS = 20
    # Twice MAX_WIDTH, so thumbnails stay sharp on high-DPI screens without keeping
    # multi-megabyte screenshots in the repo.
    MAX_STORED_WIDTH = 1200

    def __init__(self, path: Path):
        self.path = path

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    @property
    def size(self) -> tuple[float, float]:
        """Raises OSError, ValueError, or ElementTree.ParseError if the file isn't a readable image."""
        # Pillow can't read SVGs, and they scale freely, so only their viewBox aspect ratio matters.
        if self.suffix == ".svg":
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
            print(f"  ⚠️  Couldn't read the size of {self.path.name} ({e}), using full width")
            return self.MAX_WIDTH

        scale = min(self.MAX_WIDTH / width, self.MAX_HEIGHT / height)
        if self.suffix != ".svg":
            scale = min(scale, 1)

        return round(width * scale)

    def shrink(self) -> "Thumbnail":
        """Scale a raster thumbnail down to MAX_STORED_WIDTH if it's wider, keeping its format.

        SVGs scale freely and GIFs may be animated, so both are left alone.
        """
        if self.suffix in (".svg", ".gif"):
            return self

        with Image.open(self.path) as image:
            if image.width <= self.MAX_STORED_WIDTH:
                return self

            # Palette images can only be resized with nearest-neighbour, which looks jagged.
            if image.mode in ("P", "1"):
                image = image.convert("RGBA")

            height = round(image.height * self.MAX_STORED_WIDTH / image.width)
            image = image.resize((self.MAX_STORED_WIDTH, height), Image.LANCZOS)

        if self.suffix in (".jpg", ".jpeg"):
            image.convert("RGB").save(self.path, quality=90, optimize=True)
        elif self.suffix == ".webp":
            image.save(self.path, quality=90)
        else:
            image.save(self.path, optimize=True)

        return self

    def round_corners(self) -> "Thumbnail":
        """Cut rounded corners into a raster thumbnail and return it (JPEGs become PNGs).

        SVGs and GIFs are left alone, as are images whose corners are already
        transparent (icons and logos that have their own shape).
        """
        if self.suffix in (".svg", ".gif"):
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

        if self.suffix == ".webp":
            image.save(self.path, lossless=True)
            return self

        dest = self.path.with_suffix(".png")
        image.save(dest, optimize=True)
        if dest != self.path:
            self.path.unlink()

        return Thumbnail(dest)


class ThumbnailFetcher:
    """Finds and saves a tool's thumbnail as assets/thumbnails/<slug>.<ext>."""

    def __init__(self, *, name: str, url: str):
        self.url = url
        # Fall back to the domain for names with no Latin letters or digits at all.
        self.slug = self._slugify(name) or self._slugify(urlparse(url).netloc.removeprefix("www."))

    def existing(self) -> Path | None:
        return next(iter(THUMBNAILS_DIR.glob(f"{self.slug}.*")), None)

    def fetch(self, *, image: str | None) -> Thumbnail:
        """Save --image if given, otherwise the first usable image from the page's meta tags."""
        if image:
            sources = [image]
        else:
            try:
                sources = PageInspector(self.url).image_candidates
            except requests.RequestException as e:
                print(f"  ⚠️  Could not fetch {self.url}: {e}")
                sources = []

        for source in sources:
            try:
                print(f"  Downloading {source}...")
                return self.save(source)
            except (requests.RequestException, ValueError) as e:
                print(f"  ⚠️  {e}")

        raise RuntimeError("No usable thumbnail found. Pass --image <url-or-path>.")

    def save(self, source: str) -> Thumbnail:
        """Download (or copy, for a local path) an image. Raises ValueError if it isn't one."""
        local = Path(source).expanduser()
        if local.is_file():
            suffix = local.suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                raise ValueError(f"{source} isn't a supported image ({', '.join(sorted(IMAGE_SUFFIXES))})")

            dest = THUMBNAILS_DIR / f"{self.slug}{suffix}"
            shutil.copyfile(local, dest)
        else:
            resp = requests.get(source, timeout=15, headers=HEADERS)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type not in IMAGE_TYPES:
                raise ValueError(f"{source} returned {content_type or 'no content type'}, not an image")

            dest = THUMBNAILS_DIR / f"{self.slug}{IMAGE_TYPES[content_type]}"
            dest.write_bytes(resp.content)

        # Make sure the file really is an image before anything else relies on it.
        thumbnail = Thumbnail(dest)
        try:
            thumbnail.size
        except (OSError, ValueError, ElementTree.ParseError) as e:
            dest.unlink()
            raise ValueError(f"{source} isn't a readable image ({e})")

        return thumbnail

    @staticmethod
    def _slugify(text: str) -> str:
        """Lowercase ASCII letters and digits only, with accents stripped ("Café" -> "cafe")."""
        ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())
