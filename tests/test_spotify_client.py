from unittest.mock import MagicMock

from billboard_playlist import spotify_client


def fake_sp(existing=None):
    sp = MagicMock()
    sp.current_user.return_value = {"id": "me"}
    sp.current_user_playlists.return_value = {"items": existing or [], "next": None}
    sp.current_user_playlist_create.return_value = {"id": "new", "external_urls": {"spotify": "u"}}
    return sp


def test_creates_playlist_and_batches_items():
    sp = fake_sp()
    uris = [f"spotify:track:{i}" for i in range(150)]
    spotify_client.upsert_playlist(sp, "X", uris, public=True, description="d")
    sp.current_user_playlist_create.assert_called_once_with("X", public=True, description="d")
    sizes = [len(c.args[1]) for c in sp.playlist_add_items.call_args_list]
    assert sizes == [100, 50]
    sp.playlist_replace_items.assert_not_called()


def test_reuses_existing_playlist_instead_of_duplicating():
    existing = [{"id": "old", "name": "X", "owner": {"id": "me"}}]
    sp = fake_sp(existing)
    spotify_client.upsert_playlist(sp, "X", ["a", "b", "a"], public=True, description="d")
    sp.current_user_playlist_create.assert_not_called()
    sp.playlist_replace_items.assert_called_once_with("old", ["a", "b"])


def test_search_uses_new_limit():
    sp = MagicMock()
    sp.search.return_value = {"tracks": {"items": [{"uri": "x"}]}}
    assert spotify_client.search_tracks(sp, "q") == [{"uri": "x"}]
    assert sp.search.call_args.kwargs["limit"] == 10


def test_cli_skips_years_that_already_have_playlists(monkeypatch, capsys):
    from billboard_playlist import chart, cli

    sp = fake_sp([
        {"id": "a", "name": "Billboard Year-End Hot 100: 1985", "owner": {"id": "me"}},
        {"id": "b", "name": "Billboard Hot 100 1986", "owner": {"id": "me"}},  # v1 name
    ])
    monkeypatch.setattr(spotify_client, "connect", lambda *a: sp)
    fetched = []
    monkeypatch.setattr(chart, "get_chart", lambda y, s=None: fetched.append(y) or [])
    cli.main(["1985-1987"])
    assert fetched == [1987]
