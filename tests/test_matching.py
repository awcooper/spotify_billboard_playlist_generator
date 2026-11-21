from billboard_playlist.chart import ChartEntry
from billboard_playlist.matching import best_match, build_queries, split_artists, strip_version


def track(name, *artists, album="Album", uri=None):
    return {
        "name": name,
        "artists": [{"name": a} for a in artists],
        "album": {"name": album},
        "uri": uri or f"spotify:track:{name.replace(' ', '')}",
    }


def test_split_artists():
    assert split_artists("Mark Ronson featuring Bruno Mars") == ["Mark Ronson", "Bruno Mars"]
    assert split_artists("Lil Nas X featuring Billy Ray Cyrus") == ["Lil Nas X", "Billy Ray Cyrus"]
    assert split_artists("Beyoncé") == ["Beyoncé"]


def test_strip_version():
    assert strip_version("Hey Jude - Remastered 2015") == "Hey Jude"
    assert strip_version("Crazy for You (Single Version)") == "Crazy for You"


def test_build_queries_uses_field_filters_first():
    q = build_queries(ChartEntry(1, "Uptown Funk", "Mark Ronson featuring Bruno Mars"))
    assert q[0] == 'track:"Uptown Funk" artist:"Mark Ronson"'
    assert q[-1] == "Uptown Funk Mark Ronson"


def test_best_match_prefers_original_over_karaoke():
    entry = ChartEntry(1, "Uptown Funk", "Mark Ronson featuring Bruno Mars")
    results = [
        track("Uptown Funk (Karaoke Version)", "Karaoke Stars", uri="karaoke"),
        track("Uptown Funk (feat. Bruno Mars)", "Mark Ronson", "Bruno Mars", uri="real"),
    ]
    assert best_match(entry, results, 0.65).uri == "real"


def test_best_match_handles_band_names_with_ampersand():
    entry = ChartEntry(5, "September", "Earth, Wind & Fire")
    results = [track("September", "Earth, Wind & Fire", uri="ewf")]
    assert best_match(entry, results, 0.65).uri == "ewf"


def test_best_match_accepts_remaster_suffix_and_accents():
    entry = ChartEntry(1, "Hey Jude", "The Beatles")
    m = best_match(entry, [track("Hey Jude - Remastered 2015", "The Beatles", uri="hj")], 0.65)
    assert m.uri == "hj"
    entry = ChartEntry(2, "Crazy in Love", "Beyonce featuring Jay-Z")
    m = best_match(entry, [track("Crazy In Love (feat. Jay-Z)", "Beyoncé", "JAY-Z", uri="cil")], 0.65)
    assert m.uri == "cil"


def test_best_match_rejects_wrong_song():
    entry = ChartEntry(1, "Smooth", "Santana featuring Rob Thomas")
    m = best_match(entry, [track("Smooth Operator", "Sade")], 0.65)
    assert m.uri is None


def test_parse_years_all_and_ranges():
    import datetime as dt

    from billboard_playlist.cli import parse_years

    years = parse_years(["all"])
    assert years[0] == 1959 and years[-1] == dt.date.today().year
    assert parse_years(["1990-1992", "1991", "2001"]) == [1990, 1991, 1992, 2001]
