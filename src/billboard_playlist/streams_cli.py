"""List Billboard Year-End Hot 100 songs with at least N Spotify streams.

    billboard-streams all                         # every year, 500M+ (default)
    billboard-streams 2010-2019 --min 1B -o 2010s_1b.csv
    billboard-streams all --playlist              # also save the list as a playlist
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field

import requests

from . import chart, cli, spotify_client
from .streams import StreamLookup

PLAYLIST_NAME = "Billboard Year-End Hot 100: {label}+ Spotify Streams"


def parse_count(text: str) -> int:
    """'500M', '1.5B', '750k' or '500000000' -> int."""
    text = text.strip().upper().replace(",", "").replace("_", "")
    scale = {"K": 10**3, "M": 10**6, "B": 10**9}.get(text[-1:], 1)
    number = text[:-1] if scale > 1 else text
    try:
        return int(float(number) * scale)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a stream count: {text!r}") from None


def short_count(n: int) -> str:
    for scale, suffix in ((10**9, "B"), (10**6, "M"), (10**3, "K")):
        if n >= scale:
            return f"{n / scale:g}{suffix}"
    return str(n)


@dataclass
class Song:
    title: str
    artist: str
    track: dict
    streams: int
    years: list[int] = field(default_factory=list)
    best_rank: int = 999


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="List Billboard Year-End Hot 100 songs with at least N Spotify streams."
    )
    p.add_argument("years", nargs="+", help="Years or ranges, e.g. 2015 2010-2019, or 'all'")
    p.add_argument("--min", dest="min_streams", type=parse_count, default=parse_count("500M"),
                   help="Minimum Spotify streams, e.g. 500M, 1B, 250000000 (default 500M)")
    p.add_argument("-o", "--output", default="hot100_streams.csv", help="CSV to write (default hot100_streams.csv)")
    p.add_argument("--playlist", action="store_true", help="Also save the songs as a Spotify playlist, most streamed first")
    p.add_argument("--private", action="store_true", help="Make that playlist private")
    p.add_argument("--threshold", type=float, default=0.65, help="Minimum match score 0-1 (default 0.65)")
    p.add_argument("--market", default=None, help="ISO country code to restrict search, e.g. US")
    p.add_argument("--client-id", help="Spotify Client ID (default: $SPOTIPY_CLIENT_ID)")
    p.add_argument("--redirect-uri", help=f"default: {spotify_client.DEFAULT_REDIRECT_URI}")
    args = p.parse_args(argv)

    years = cli.parse_years(args.years)
    sp = spotify_client.connect(args.client_id, args.redirect_uri)
    http = requests.Session()
    lookup = StreamLookup(http)
    songs: dict[str, Song] = {}  # keyed by Spotify track ID, so repeat years merge
    unknown = 0

    try:
        for year in years:
            print(f"\nBillboard Year-End Hot 100 — {year}")
            try:
                entries = chart.get_chart(year, http)
            except (LookupError, ValueError, requests.RequestException) as exc:
                print(f"  Skipping {year}: {exc}", file=sys.stderr)
                continue

            for m in cli.match_year(sp, entries, args.threshold, args.market):
                if not m.track:
                    continue
                try:
                    streams = lookup.streams_for(m.track)
                except requests.RequestException as exc:
                    print(f"    streams lookup failed for {m.entry.title}: {exc}", file=sys.stderr)
                    streams = None
                if streams is None:
                    unknown += 1
                    continue
                if streams < args.min_streams:
                    continue
                song = songs.setdefault(
                    m.track["id"], Song(m.entry.title, m.entry.artist, m.track, streams)
                )
                song.streams = max(song.streams, streams)
                if year not in song.years:
                    song.years.append(year)
                song.best_rank = min(song.best_rank, m.entry.rank)
            lookup.save()  # keep progress if a long run is interrupted
    finally:
        lookup.save()

    ranked = sorted(songs.values(), key=lambda s: s.streams, reverse=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["streams", "title", "artist", "year_end_years", "best_year_end_rank", "spotify_url"])
        for s in ranked:
            w.writerow([
                s.streams, s.title, s.artist, " ".join(map(str, s.years)), s.best_rank,
                s.track.get("external_urls", {}).get("spotify", ""),
            ])

    label = short_count(args.min_streams)
    print(f"\n{len(ranked)} songs with {label}+ streams → {args.output}")
    if unknown:
        print(f"({unknown} matched songs had no stream count on kworb and were left out)")
    for s in ranked[:10]:
        print(f"  {s.streams:>14,}  {s.title} — {s.artist} ({', '.join(map(str, s.years))})")

    if args.playlist and ranked:
        playlist = spotify_client.upsert_playlist(
            sp,
            PLAYLIST_NAME.format(label=label),
            [s.track["uri"] for s in ranked],
            public=not args.private,
            description=f"Billboard Year-End Hot 100 songs with over {label} Spotify streams, most streamed first.",
        )
        print(f"Saved playlist → {playlist['external_urls']['spotify']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
