"""Look up all-time Spotify stream counts for tracks.

Spotify's Web API does not expose play counts (the official API only has the
0-100 `popularity` score, and Development Mode apps no longer get even that).
kworb.net publishes each artist's tracks with their total Spotify streams, keyed
by Spotify track ID, and refreshes them daily, so that is what we read here.

A song often exists under several track IDs (single, album, deluxe, compilation).
Spotify counts each ID separately, so for a matched track we take the highest
count among that artist's tracks with the same title. That is the version most
people actually streamed.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .chart import USER_AGENT
from .matching import normalize, strip_version

KWORB_ARTIST_URL = "https://kworb.net/spotify/artist/{artist_id}_songs.html"
_TRACK_HREF = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]{22})")


@dataclass(frozen=True)
class ArtistTrack:
    track_id: str
    title: str
    streams: int


def parse_artist_page(html: str) -> list[ArtistTrack]:
    """Parse a kworb artist songs page into (track id, title, streams) rows."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ArtistTrack] = []
    for link in soup.find_all("a", href=_TRACK_HREF):
        tr = link.find_parent("tr")
        if tr is None:
            continue
        cells = tr.find_all("td")
        numbers = [c.get_text(strip=True).replace(",", "") for c in cells]
        numbers = [n for n in numbers if n.isdigit()]
        if not numbers:
            continue
        track_id = _TRACK_HREF.search(link["href"]).group(1)
        # The first numeric column is total streams; the second is daily.
        rows.append(ArtistTrack(track_id, link.get_text(strip=True), int(numbers[0])))
    return rows


class StreamLookup:
    """Fetches kworb artist pages on demand, with an on-disk cache."""

    def __init__(
        self,
        session: requests.Session | None = None,
        cache_path: str | None = ".kworb_cache.json",
        max_age_hours: float = 24,
        delay: float = 1.0,
    ):
        self.http = session or requests.Session()
        self.cache_path = cache_path
        self.max_age = max_age_hours * 3600
        self.delay = delay
        self._pages: dict[str, dict] = {}
        self._last_request = 0.0
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self._pages = json.load(f)

    def save(self) -> None:
        if self.cache_path:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._pages, f)

    def artist_tracks(self, artist_id: str) -> list[ArtistTrack]:
        cached = self._pages.get(artist_id)
        if cached and time.time() - cached["fetched"] < self.max_age:
            return [ArtistTrack(*row) for row in cached["rows"]]

        wait = self.delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)  # be polite: kworb is a one-person site
        self._last_request = time.time()
        resp = self.http.get(
            KWORB_ARTIST_URL.format(artist_id=artist_id),
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if resp.status_code == 404:
            rows: list[ArtistTrack] = []  # artist not tracked by kworb
        else:
            resp.raise_for_status()
            resp.encoding = "utf-8"
            rows = parse_artist_page(resp.text)
        self._pages[artist_id] = {
            "fetched": time.time(),
            "rows": [[r.track_id, r.title, r.streams] for r in rows],
        }
        return rows

    def streams_for(self, track: dict) -> int | None:
        """Best stream count for a Spotify track object, or None if unknown."""
        want = normalize(strip_version(track.get("name", "")))
        best: int | None = None
        for artist in track.get("artists", [])[:2]:  # lead artist, then first feature
            if not artist.get("id"):
                continue
            for row in self.artist_tracks(artist["id"]):
                same_id = row.track_id == track.get("id")
                same_title = normalize(strip_version(row.title.lstrip("* "))) == want
                if (same_id or same_title) and (best is None or row.streams > best):
                    best = row.streams
            if best is not None:
                break
        return best
