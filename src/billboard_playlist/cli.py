"""Command-line entry point.

    billboard-playlist 1985
    billboard-playlist 1990-1994 2003 --private
    billboard-playlist 1977 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys

import requests

from . import chart, matching, spotify_client


def playlist_name(year: int) -> str:
    return f"Billboard Year-End Hot 100: {year}"


def legacy_name(year: int) -> str:
    return f"Billboard Hot 100 {year}"  # name used by the v1 script


def parse_years(specs: list[str]) -> list[int]:
    # The current year's chart appears once Billboard publishes it (usually Nov/Dec);
    # until then its Wikipedia page is missing and the year is skipped.
    last = dt.date.today().year
    years: list[int] = []
    for spec in specs:
        if spec.lower() == "all":
            years.extend(range(chart.FIRST_YEAR, last + 1))
        elif "-" in spec:
            start, end = (int(x) for x in spec.split("-", 1))
            years.extend(range(start, end + 1))
        else:
            years.append(int(spec))
    bad = [y for y in years if not chart.FIRST_YEAR <= y <= last]
    if bad:
        raise SystemExit(f"Years must be between {chart.FIRST_YEAR} and {last}: {bad}")
    return list(dict.fromkeys(years))


def match_year(sp, entries, threshold: float, market: str | None) -> list[matching.Match]:
    matches = []
    for entry in entries:
        best = matching.Match(entry, None, 0.0)
        for query in matching.build_queries(entry):
            candidate = matching.best_match(
                entry, spotify_client.search_tracks(sp, query, market), threshold
            )
            if candidate.score > best.score:
                best = candidate
            if best.track and best.score >= 0.9:
                break  # confident enough; skip the fallback queries
        matches.append(best)
        status = f"{best.score:.2f} ✓" if best.track else f"{best.score:.2f} ✗"
        found = (
            f"{best.track['name']} — {', '.join(a['name'] for a in best.track['artists'])}"
            if best.track
            else "no confident match"
        )
        print(f"  {entry.rank:>3}. {entry.title} — {entry.artist}  →  {found}  [{status}]")
    return matches


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Create Spotify playlists from Billboard Year-End Hot 100 charts.")
    p.add_argument("years", nargs="+", help="Years or ranges, e.g. 1985 1990-1994, or 'all'")
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Rebuild years that already have a playlist (default: skip them)",
    )
    p.add_argument("--private", action="store_true", help="Make the playlist private")
    p.add_argument("--dry-run", action="store_true", help="Match songs but don't create playlists")
    p.add_argument("--threshold", type=float, default=0.65, help="Minimum match score 0-1 (default 0.65)")
    p.add_argument("--market", default=None, help="ISO country code to restrict search, e.g. US")
    p.add_argument("--misses-csv", help="Write unmatched songs to this CSV file")
    p.add_argument("--client-id", help="Spotify Client ID (default: $SPOTIPY_CLIENT_ID)")
    p.add_argument("--redirect-uri", help=f"default: {spotify_client.DEFAULT_REDIRECT_URI}")
    args = p.parse_args(argv)

    years = parse_years(args.years)
    sp = spotify_client.connect(args.client_id, args.redirect_uri)
    http = requests.Session()
    misses: list[tuple[int, matching.Match]] = []
    existing = set() if args.overwrite else spotify_client.own_playlist_names(sp)

    for year in years:
        if playlist_name(year) in existing or legacy_name(year) in existing:
            print(f"{year}: playlist already exists, skipping (use --overwrite to rebuild)")
            continue
        print(f"\nBillboard Year-End Hot 100 — {year}")
        try:
            entries = chart.get_chart(year, http)
        except (LookupError, ValueError, requests.RequestException) as exc:
            print(f"  Skipping {year}: {exc}", file=sys.stderr)
            continue

        matches = match_year(sp, entries, args.threshold, args.market)
        uris = [m.uri for m in matches if m.uri]
        misses.extend((year, m) for m in matches if not m.uri)
        print(f"  Matched {len(uris)}/{len(entries)}")

        if not args.dry_run and uris:
            playlist = spotify_client.upsert_playlist(
                sp,
                playlist_name(year),
                uris,
                public=not args.private,
                description=f"The Billboard Year-End Hot 100 singles of {year}, in chart order.",
            )
            print(f"  Saved → {playlist['external_urls']['spotify']}")

    if args.misses_csv and misses:
        with open(args.misses_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["year", "rank", "title", "artist", "best_score"])
            for year, m in misses:
                w.writerow([year, m.entry.rank, m.entry.title, m.entry.artist, f"{m.score:.2f}"])
        print(f"\nWrote {len(misses)} misses to {args.misses_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
