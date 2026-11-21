from billboard_playlist.chart import clean_title, parse_chart

# Trimmed-down copy of the markup Wikipedia's parse API returns, including the
# quirks that broke the old parser: <th> rank cells, footnotes, double A-sides
# and an artist cell that spans two rows.
HTML = """
<div class="mw-parser-output">
<table class="wikitable sortable">
<tbody>
<tr><th>No.</th><th>Title</th><th>Artist(s)</th></tr>
<tr><th>1</th><td>"<a href="#">Careless Whisper</a>"</td><td><a href="#">Wham!</a> featuring George Michael</td></tr>
<tr><th>2</th><td>"<a href="#">Like a Virgin</a>"<sup>[a]</sup></td><td rowspan="2"><a href="#">Madonna</a></td></tr>
<tr><th>3</th><td>"<a href="#">Crazy for You</a>"</td></tr>
<tr><td>4</td><td>"<a href="#">Hey Jude</a>" / "<a href="#">Revolution</a>"</td><td>The Beatles</td></tr>
</tbody>
</table>
</div>
"""


def test_parse_chart_handles_rowspan_th_and_footnotes():
    entries = parse_chart(HTML)
    assert [(e.rank, e.title, e.artist) for e in entries] == [
        (1, "Careless Whisper", "Wham! featuring George Michael"),
        (2, "Like a Virgin", "Madonna"),
        (3, "Crazy for You", "Madonna"),
        (4, "Hey Jude", "The Beatles"),
    ]


def test_clean_title_variants():
    assert clean_title('"Smooth"[1]') == "Smooth"
    assert clean_title('“Yesterday”') == "Yesterday"
    assert clean_title('"A" \\ "B"') == "A"
