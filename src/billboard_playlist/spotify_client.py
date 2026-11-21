"""Thin wrapper around spotipy using the post-February-2026 Web API endpoints.

* Auth: Authorization Code with PKCE, so no client secret is needed on disk.
* Redirect URI: must be a loopback IP (127.0.0.1); "localhost" is rejected.
* Playlists: POST /me/playlists and /playlists/{id}/items (the /users/{id}/playlists
  and /playlists/{id}/tracks endpoints were removed for Development Mode apps).
* Search: max `limit` is now 10.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE

# The original app's Client ID (not a secret). Override with SPOTIPY_CLIENT_ID.
DEFAULT_CLIENT_ID = "c6f00c6cca38465bbeaa7dd05f6f6b9c"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SEARCH_LIMIT = 10  # Spotify's maximum since Feb 2026
ADD_BATCH = 100  # max items per add/replace request


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so the secret lives in a git-ignored file, not in code."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def connect(client_id: str | None = None, redirect_uri: str | None = None) -> spotipy.Spotify:
    _load_dotenv()
    client_id = client_id or os.environ.get("SPOTIPY_CLIENT_ID", DEFAULT_CLIENT_ID)
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    common = dict(
        client_id=client_id,
        redirect_uri=redirect_uri or os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=".spotify_token_cache"),
        open_browser=True,
    )
    if client_secret:
        auth = SpotifyOAuth(client_secret=client_secret, **common)
    else:
        auth = SpotifyPKCE(**common)  # no secret needed
    return spotipy.Spotify(auth_manager=auth, retries=5, status_retries=5, backoff_factor=0.5)


def own_playlist_names(sp: spotipy.Spotify) -> set[str]:
    me = sp.current_user()["id"]
    names: set[str] = set()
    page = sp.current_user_playlists(limit=50)
    while page:
        names.update(
            pl["name"] for pl in page.get("items", []) if pl and pl.get("owner", {}).get("id") == me
        )
        page = sp.next(page) if page.get("next") else None
    return names


def search_tracks(sp: spotipy.Spotify, query: str, market: str | None = None) -> list[dict]:
    result = sp.search(q=query, type="track", limit=SEARCH_LIMIT, market=market)
    return result.get("tracks", {}).get("items", []) or []


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def find_own_playlist(sp: spotipy.Spotify, name: str) -> dict | None:
    me = sp.current_user()["id"]
    page = sp.current_user_playlists(limit=50)
    while page:
        for pl in page.get("items", []):
            if pl and pl.get("name") == name and pl.get("owner", {}).get("id") == me:
                return pl
        page = sp.next(page) if page.get("next") else None
    return None


def upsert_playlist(
    sp: spotipy.Spotify,
    name: str,
    uris: Iterable[str],
    *,
    public: bool,
    description: str,
) -> dict:
    """Create the playlist, or replace the contents of an existing one with the same name."""
    uris = list(dict.fromkeys(uris))  # de-dupe, keep order
    playlist = find_own_playlist(sp, name)
    if playlist is None:
        playlist = sp.current_user_playlist_create(name, public=public, description=description)
        batches = list(_chunks(uris, ADD_BATCH))
    else:
        batches = list(_chunks(uris, ADD_BATCH)) or [[]]
        sp.playlist_replace_items(playlist["id"], batches[0])
        batches = batches[1:]
    for batch in batches:
        sp.playlist_add_items(playlist["id"], batch)
    return playlist
