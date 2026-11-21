from unittest.mock import MagicMock

import pytest

from billboard_playlist import chart, spotify_client, streams_cli
from billboard_playlist.streams import StreamLookup, parse_artist_page

PAGE = """
<table><tr><th>Song Title</th><th>Streams</th><th>Daily</th></tr>
<tr><td><a href="https://open.spotify.com/track/AAAAAAAAAAAAAAAAAAAAAA">Uptown Funk (feat. Bruno Mars)</a></td>
    <td>2,900,000,000</td><td>800,000</td></tr>
<tr><td><a href="https://open.spotify.com/track/BBBBBBBBBBBBBBBBBBBBBB">Uptown Funk (feat. Bruno Mars)</a></td>
    <td>40,000,000</td><td>5,000</td></tr>
<tr><td>* <a href="https://open.spotify.com/track/CCCCCCCCCCCCCCCCCCCCCC">Small Song</a></td>
    <td>120,000</td><td>10</td></tr>
</table>
"""


def lookup_with(page):
    http = MagicMock()
    http.get.return_value = MagicMock(status_code=200, text=page)
    return StreamLookup(http, cache_path=None, delay=0), http


def test_parse_artist_page():
    rows = parse_artist_page(PAGE)
    assert [(r.track_id[0], r.streams) for r in rows] == [("A", 2_900_000_000), ("B", 40_000_000), ("C", 120_000)]


def test_streams_uses_most_streamed_version_of_same_title():
    lookup, http = lookup_with(PAGE)
    # Matched the compilation copy (B); the single (A) is the one people streamed.
    track = {"id": "B" * 22, "name": "Uptown Funk (feat. Bruno Mars)", "artists": [{"id": "ronson"}]}
    assert lookup.streams_for(track) == 2_900_000_000
    lookup.streams_for(track)
    assert http.get.call_count == 1  # artist page is cached


def test_streams_unknown_track():
    lookup, _ = lookup_with(PAGE)
    assert lookup.streams_for({"id": "Z" * 22, "name": "Other", "artists": [{"id": "x"}]}) is None


@pytest.mark.parametrize("text,value", [("500M", 500_000_000), ("1.5B", 1_500_000_000),
                                        ("750k", 750_000), ("500,000,000", 500_000_000)])
def test_parse_count(text, value):
    assert streams_cli.parse_count(text) == value


def test_cli_filters_dedupes_and_sorts(monkeypatch, tmp_path):
    entries = {
        2015: [chart.ChartEntry(1, "Uptown Funk", "Mark Ronson featuring Bruno Mars"),
               chart.ChartEntry(2, "Small Song", "Someone")],
        2016: [chart.ChartEntry(40, "Uptown Funk", "Mark Ronson featuring Bruno Mars")],
    }
    tracks = {
        "Uptown Funk": {"id": "A" * 22, "uri": "spotify:track:A", "name": "Uptown Funk (feat. Bruno Mars)",
                        "artists": [{"id": "ronson", "name": "Mark Ronson"}, {"id": "bm", "name": "Bruno Mars"}],
                        "album": {"name": "Uptown Special"}, "external_urls": {"spotify": "url-a"}},
        "Small Song": {"id": "C" * 22, "uri": "spotify:track:C", "name": "Small Song",
                       "artists": [{"id": "someone", "name": "Someone"}], "album": {"name": "x"}},
    }
    sp = MagicMock()
    sp.search.side_effect = lambda q, **kw: {"tracks": {"items": [t for k, t in tracks.items() if k in q]}}
    monkeypatch.setattr(spotify_client, "connect", lambda *a: sp)
    monkeypatch.setattr(chart, "get_chart", lambda y, s=None: entries[y])
    monkeypatch.setattr(streams_cli, "StreamLookup", lambda http: lookup_with(PAGE)[0])

    out = tmp_path / "out.csv"
    streams_cli.main(["2015-2016", "--min", "500M", "-o", str(out)])
    lines = out.read_text().splitlines()
    assert lines[0].startswith("streams,title")
    assert lines[1:] == ["2900000000,Uptown Funk,Mark Ronson featuring Bruno Mars,2015 2016,1,url-a"]
    sp.current_user_playlist_create.assert_not_called()
