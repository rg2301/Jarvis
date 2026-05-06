"""Real-time web search via Google News RSS + Wikipedia (no API key)."""

from __future__ import annotations

import html as _html
import re as _re
import urllib.parse
import webbrowser

import requests

from .config import log


class WebBrain:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self) -> None:
        self.enabled = True
        log.info("Web brain ready. Using Google News RSS + Wikipedia + Google Search.")

    # ── News via Google News RSS ────────────────────────────────────────────
    def search_news(self, query: str, count: int = 5) -> list[dict]:
        try:
            encoded = urllib.parse.quote(query)
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
            )
            r = requests.get(rss_url, headers=self.HEADERS, timeout=10)
            if r.status_code != 200:
                log.warning(f"Google News RSS status: {r.status_code}")
                return self._wikipedia_search(query)

            xml = r.text
            results: list[dict] = []
            items = _re.findall(r"<item>(.*?)</item>", xml, _re.DOTALL)
            for item in items[:count]:
                title = _re.findall(
                    r"<title><!\[CDATA\[(.*?)\]\]></title>", item
                ) or _re.findall(r"<title>(.*?)</title>", item)
                desc = _re.findall(
                    r"<description><!\[CDATA\[(.*?)\]\]></description>", item
                ) or _re.findall(r"<description>(.*?)</description>", item)
                link = _re.findall(
                    r"<link/>(.*?)(?:<|$)", item
                ) or _re.findall(r"<link>(.*?)</link>", item)

                title_text = (
                    _html.unescape(_re.sub(r"<[^>]+>", "", title[0])).strip()
                    if title else ""
                )
                desc_text = (
                    _html.unescape(_re.sub(r"<[^>]+>", "", desc[0])).strip()[:200]
                    if desc else ""
                )
                link_text = link[0].strip() if link else ""
                # Strip trailing source like " - Times of India"
                title_text = _re.sub(r"\s*-\s*[^-]+$", "", title_text).strip()

                if title_text:
                    results.append({
                        "title":       title_text,
                        "url":         link_text,
                        "description": desc_text,
                    })

            log.info(f"Google News RSS returned {len(results)} results for '{query}'.")
            return results or self._wikipedia_search(query)
        except Exception as e:
            log.error(f"News search error: {e}")
            return self._wikipedia_search(query)

    # ── General search ──────────────────────────────────────────────────────
    def search(self, query: str, count: int = 5) -> list[dict]:
        try:
            from googlesearch import search as gsearch

            results = []
            for url in gsearch(query, num_results=count, lang="en"):
                try:
                    domain = url.split("/")[2].replace("www.", "")
                except IndexError:
                    domain = url
                results.append({
                    "title":       domain,
                    "url":         url,
                    "description": self._fetch_snippet(url),
                })
            if results:
                log.info(f"Google search '{query}' returned {len(results)} results.")
                return results
        except Exception as e:
            log.warning(f"googlesearch-python error: {e}")

        log.info(f"Falling back to Wikipedia for '{query}'.")
        return self._wikipedia_search(query)

    # ── Wikipedia fallback ──────────────────────────────────────────────────
    def _wikipedia_search(self, query: str) -> list[dict]:
        try:
            encoded = urllib.parse.quote(query)
            url = (
                f"https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={encoded}"
                f"&format=json&srlimit=3"
            )
            r = requests.get(url, headers=self.HEADERS, timeout=8)
            data = r.json()
            results = []
            for item in data.get("query", {}).get("search", []):
                snippet = _re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                title = item.get("title", "")
                results.append({
                    "title":       title,
                    "url":         f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "description": snippet,
                })
            log.info(f"Wikipedia returned {len(results)} results for '{query}'.")
            return results
        except Exception as e:
            log.error(f"Wikipedia error: {e}")
            return []

    def _fetch_snippet(self, url: str, max_chars: int = 300) -> str:
        try:
            import httpx

            r = httpx.get(
                url, headers=self.HEADERS, timeout=6, follow_redirects=True,
            )
            if r.status_code != 200:
                return ""
            html = _re.sub(
                r"<(script|style|nav|footer|header)[^>]*>.*?</\1>",
                "", r.text, flags=_re.DOTALL | _re.IGNORECASE,
            )
            text = _re.sub(r"<[^>]+>", " ", html)
            text = _re.sub(r"\s+", " ", text).strip()
            for s in _re.split(r"(?<=[.!?])\s+", text):
                if len(s.strip()) >= 60:
                    return s.strip()[:max_chars]
            return text[:max_chars]
        except Exception:
            return ""

    # ── Format for the model ────────────────────────────────────────────────
    def summarise_for_jarvis(self, query: str, results: list[dict]) -> str:
        if not results:
            return f"No web results found for: {query}"
        lines = [f"Real-time web results for '{query}':\n"]
        for i, r in enumerate(results[:4], 1):
            desc   = r["description"][:200] if r["description"] else "No description"
            source = r["url"][:60]          if r["url"]         else "Web"
            lines.append(
                f"{i}. {r['title']}\n   {desc}\n   Source: {source}"
            )
        return "\n".join(lines)

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def open_website(url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        log.info(f"Opened browser: {url}")
        return url
