"""
web_utils.py — Web research for OmniClaw.

Provides search and scrape so the agent can gather info
before performing phone actions (e.g. draft an email about X).
Uses DuckDuckGo HTML search (no API key needed).
"""

import re

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


def search_web(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return top results as text.

    Returns a string like:
        1. Title — snippet  (url)
        2. Title — snippet  (url)
    """
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for i, item in enumerate(soup.select(".result"), 1):
            if i > max_results:
                break
            title_el = item.select_one(".result__a")
            snippet_el = item.select_one(".result__snippet")
            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            url = title_el.get("href", "") if title_el else ""
            if title:
                results.append(f"{i}. {title} — {snippet}  ({url})")
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search error: {e}"


def scrape_page(url: str, max_chars: int = 2000) -> str:
    """Fetch a URL and extract main text content."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text[:max_chars] if text else "No content extracted."
    except Exception as e:
        return f"Scrape error: {e}"
