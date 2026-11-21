"""Turn chart entries into Spotify search queries and pick the best result.

The old script took the first search hit for "<artist> <title>", which often
returned karaoke versions, covers, or the wrong song. Here we use Spotify's
field filters, score every candidate on title + artist similarity, and reject
anything below a threshold so misses are reported instead of silently wrong.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from .chart import ChartEntry

# Split a credit like "Mark Ronson featuring Bruno Mars" into individual artists.
_ARTIST_SPLIT = re.compile(
    r"\s+(?:featuring|feat\.?|ft\.?|with|duet with|vs\.?|and|&)\s+|\s*,\s*|\s*/\s*",
    re.IGNORECASE,
)
# Version suffixes Spotify appends: "Song - 2011 Remaster", "Song (Single Version)".
_VERSION_SUFFIX = re.compile(r"\s+-\s+.*$|\s*[(\[][^)\]]*[)\]]")
_BAD_VERSIONS = ("karaoke", "tribute", "instrumental", "cover", "made famous", "originally performed")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def split_artists(credit: str) -> list[str]:
    parts = [p.strip() for p in _ARTIST_SPLIT.split(credit) if p and p.strip()]
    return parts or [credit]


def strip_version(name: str) -> str:
    return _VERSION_SUFFIX.sub("", name).strip() or name


def _similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def build_queries(entry: ChartEntry) -> list[str]:
    title = entry.title.replace('"', "")
    primary = split_artists(entry.artist)[0].replace('"', "")
    queries = [f'track:"{title}" artist:"{primary}"']
    if primary != entry.artist:
        queries.append(f'track:"{title}" artist:"{entry.artist.replace(chr(34), "")}"')
    queries.append(f"{title} {primary}")  # loose fallback for punctuation mismatches
    return queries


def score(entry: ChartEntry, track: dict) -> float:
    """0..1 confidence that `track` (a Spotify track object) is this chart entry."""
    name = track.get("name", "")
    title_score = max(_similarity(entry.title, name), _similarity(entry.title, strip_version(name)))

    credited = [entry.artist, *split_artists(entry.artist)]
    track_artists = [a.get("name", "") for a in track.get("artists", [])]
    joined = " ".join(track_artists)
    artist_score = max(
        [_similarity(c, t) for c in credited for t in [*track_artists, joined]] or [0.0]
    )

    result = 0.6 * title_score + 0.4 * artist_score
    lowered = f"{name} {track.get('album', {}).get('name', '')}".lower()
    if any(bad in lowered and bad not in entry.title.lower() for bad in _BAD_VERSIONS):
        result -= 0.3
    return result


@dataclass
class Match:
    entry: ChartEntry
    track: dict | None
    score: float

    @property
    def uri(self) -> str | None:
        return self.track["uri"] if self.track else None


def best_match(entry: ChartEntry, candidates: list[dict], threshold: float) -> Match:
    best: Match = Match(entry, None, 0.0)
    for position, track in enumerate(candidates):
        if not track:
            continue
        # Spotify already ranks by relevance/popularity (the popularity field itself
        # is no longer returned to Development Mode apps), so nudge earlier hits.
        s = score(entry, track) - 0.01 * position
        if s > best.score:
            best = Match(entry, track, s)
    if best.score < threshold:
        return Match(entry, None, best.score)
    return best
