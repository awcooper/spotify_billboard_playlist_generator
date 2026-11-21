# spotify_billboard_playlist_generator

Creates Spotify playlists from the **Billboard Year-End Hot 100** for any year
from 1959 onward, in chart order.

Chart data comes from Wikipedia's *Billboard Year-End Hot 100 singles of YEAR*
pages, read through the MediaWiki API. Billboard has no official public API,
and its site changes too often to scrape reliably.

## Setup

1. **Spotify app.** In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard),
   open your app and under *Redirect URIs* add exactly:

   ```
   http://127.0.0.1:8888/callback
   ```

   Spotify no longer accepts `localhost` redirect URIs (use the loopback IP).
   Since February 2026, Development Mode apps also need the app owner to have
   **Spotify Premium**, and are limited to a small number of allow-listed users.

2. **Install** (Python 3.10+):

   ```bash
   pip install -e .
   ```

3. **Credentials.** Copy `.env.example` to `.env` and fill in
   `SPOTIPY_CLIENT_SECRET`. `.env` is git-ignored, so never put the secret in
   code. If you leave the secret empty, the app uses PKCE, which needs only the
   Client ID.

## Usage

```bash
billboard-playlist 1985                 # one year
billboard-playlist 1990-1994 2003       # ranges and lists
billboard-playlist all                  # every year that doesn't already have a playlist
billboard-playlist all --misses-csv misses.csv
billboard-playlist 1977 --dry-run       # show matches without creating anything
billboard-playlist 1985 --overwrite     # rebuild an existing playlist
```

The first run opens a browser so you can log in to Spotify. The token is then
cached in `.spotify_token_cache`.

Years whose playlist already exists, under the new name
`Billboard Year-End Hot 100: YEAR` or the old `Billboard Hot 100 YEAR`, are
skipped. The current year is skipped until its chart is published, usually in
late November or December.

A full `all` run makes several thousand search requests and can take a while.
Spotify rate limits are retried automatically.

## Songs with 500M+ streams

`billboard-streams` lists every Year-End Hot 100 song with at least a given
number of all-time Spotify streams, most streamed first:

```bash
billboard-streams all                          # every year, 500M+ (default) → hot100_streams.csv
billboard-streams 2010-2019 --min 1B -o 2010s_1b.csv
billboard-streams all --playlist               # also save them as a Spotify playlist
```

The CSV has the stream count, title, artist, the year-end charts the song was
on, its best year-end rank, and its Spotify link. A song on two year-end charts
is listed once.

Spotify's API doesn't give stream counts, so they come from
[kworb.net](https://kworb.net/spotify/), which publishes each artist's
per-track Spotify totals daily. A song released under several track IDs
(single, album, deluxe) counts as its most streamed version. Pages are cached
in `.kworb_cache.json` for 24 hours, and requests are spaced a second apart, so
a first `all` run takes a while. Songs kworb doesn't track are reported and
left out.

## How matching works

For each chart entry the tool:

1. searches `track:"<title>" artist:"<primary artist>"`, then the full artist
   credit, then a loose keyword query;
2. scores every result on title and artist similarity, ignoring suffixes like
   "- 2011 Remaster" and accents, and penalizing karaoke, tribute and cover
   versions;
3. adds the best result only if it scores ≥ 0.65 (`--threshold`). Anything
   lower is reported as a miss instead of adding the wrong song.

## Development

```bash
pip install -e '.[dev]'
pytest
```

## What changed from v1 (2026 API update)

| v1 | now |
|---|---|
| `spotipy.util.prompt_for_user_token` (deprecated) | `SpotifyOAuth` / `SpotifyPKCE` auth managers |
| `http://localhost:8888` redirect | `http://127.0.0.1:8888/callback` (required by Spotify) |
| `POST /users/{id}/playlists` (removed) | `POST /me/playlists` |
| `POST /playlists/{id}/tracks` (removed) | `POST /playlists/{id}/items`, batched by 100 |
| first search hit, default limit | field-filtered search, limit 10 (new max), scored matches |
| scraping the rendered Wikipedia page | MediaWiki parse API with a proper User-Agent; rowspan-aware parsing |
| one year per run, duplicates on re-run | ranges / `all`, skips existing playlists |
