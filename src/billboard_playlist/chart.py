"""Fetch and parse Billboard Year-End Hot 100 tables from Wikipedia.

Uses the MediaWiki parse API instead of scraping the rendered page: it returns
just the article HTML, is the access method Wikimedia asks bots to use, and is
far less likely to break when the site skin changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup, Tag

from . import __version__

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGE_TEMPLATE = "Billboard Year-End Hot 100 singles of {year}"
# Wikimedia requires a descriptive User-Agent; generic ones get throttled or blocked.
USER_AGENT = (
    f"spotify-billboard-playlist-generator/{__version__} "
    "(https://github.com/awcooper/spotify_billboard_playlist_generator)"
)
FIRST_YEAR = 1959  # first Year-End Hot 100 chart

_FOOTNOTE = re.compile(r"\[[^\]]*\]")
_QUOTES = "\"“”'‘’"


@dataclass(frozen=True)
class ChartEntry:
    rank: int
    title: str
    artist: str


def fetch_chart_html(year: int, session: requests.Session | None = None) -> str:
    http = session or requests.Session()
    resp = http.get(
        WIKI_API,
        params={
            "action": "parse",
            "page": PAGE_TEMPLATE.format(year=year),
            "prop": "text",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise LookupError(f"No Year-End Hot 100 page for {year}: {data['error'].get('info')}")
    return data["parse"]["text"]


def get_chart(year: int, session: requests.Session | None = None) -> list[ChartEntry]:
    return parse_chart(fetch_chart_html(year, session))


def _clean(text: str) -> str:
    text = _FOOTNOTE.sub("", text)
    text = " ".join(text.split())
    return text.strip()


def clean_title(raw: str) -> str:
    """'"Song A" / "Song B"[1]' -> 'Song A' (first side of a double A-side)."""
    text = _clean(raw)
    # Double A-sides are written as "A" / "B" (or with a backslash in old revisions).
    text = re.split(r'["”]\s*[/\\]\s*["“]', text)[0]
    return text.strip(_QUOTES + " ")


def _expand_rows(table: Tag) -> list[list[str]]:
    """Return the table body as a grid of cell texts, honouring rowspan.

    Wikipedia uses rowspan for an artist credited on consecutive songs and for
    ties, which made fixed-width parsing silently drop rows.
    """
    grid: list[list[str]] = []
    carry: dict[int, tuple[str, int]] = {}  # column -> (text, rows remaining)
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        row: list[str] = []
        col = 0
        queue = list(cells)
        while queue or col in carry:
            if col in carry:
                text, left = carry[col]
                row.append(text)
                if left <= 1:
                    del carry[col]
                else:
                    carry[col] = (text, left - 1)
            else:
                cell = queue.pop(0)
                text = cell.get_text(" ", strip=True)
                row.append(text)
                span = int(cell.get("rowspan", 1) or 1)
                if span > 1:
                    carry[col] = (text, span - 1)
            col += 1
        grid.append(row)
    return grid


def _find_chart_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table", class_="wikitable"):
        header = table.find("tr")
        if header and "title" in header.get_text(" ").lower():
            return table
    raise ValueError("Could not find the chart table on the page")


def parse_chart(html: str) -> list[ChartEntry]:
    soup = BeautifulSoup(html, "html.parser")
    rows = _expand_rows(_find_chart_table(soup))
    header = [h.lower() for h in rows[0]]
    title_col = next(i for i, h in enumerate(header) if "title" in h)
    artist_col = next(i for i, h in enumerate(header) if "artist" in h)

    entries: list[ChartEntry] = []
    for row in rows[1:]:
        if len(row) <= max(title_col, artist_col):
            continue
        rank_match = re.match(r"\d+", _clean(row[0]))
        if not rank_match:
            continue
        entries.append(
            ChartEntry(
                rank=int(rank_match.group()),
                title=clean_title(row[title_col]),
                artist=_clean(row[artist_col]),
            )
        )
    return entries
