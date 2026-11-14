"""Metadata scraped from a tool's web page."""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import HEADERS


class PageInspector:
    """Metadata from a tool's web page. Raises requests.RequestException if the page can't be fetched."""

    IMAGE_META_KEYS = ("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    # github.com/<first>/<second> links that aren't repositories.
    NON_REPO_OWNERS = ("sponsors", "orgs", "features")

    def __init__(self, url: str):
        self.url = url
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        self.soup = BeautifulSoup(resp.text, "html.parser")

    def meta(self, *keys: str) -> str | None:
        """Content of the first of the given meta tags that's present."""
        for key in keys:
            tag = self.soup.find("meta", property=key) or self.soup.find("meta", attrs={"name": key})
            if tag and tag.get("content"):
                return tag["content"].strip()

        return None

    @property
    def title(self) -> str | None:
        title = self.soup.title
        return title.string.strip() if title and title.string else None

    @property
    def image_candidates(self) -> list[str]:
        candidates = []

        for key in self.IMAGE_META_KEYS:
            content = self.meta(key)
            if content:
                absolute = urljoin(self.url, content)
                if absolute not in candidates:
                    candidates.append(absolute)

        return candidates

    @property
    def github_links(self) -> list[str]:
        links = []

        for a in self.soup.find_all("a", href=True):
            match = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+)", a["href"])
            if match and match.group(1) not in self.NON_REPO_OWNERS:
                link = f"https://github.com/{match.group(1)}/{match.group(2).removesuffix('.git')}"
                if link not in links:
                    links.append(link)

        return links

    def summary(self) -> dict:
        return {
            "title": self.title,
            "site_name": self.meta("og:site_name"),
            "description": self.meta("og:description", "description", "twitter:description"),
            "image_candidates": self.image_candidates,
            "github_links": self.github_links,
        }
