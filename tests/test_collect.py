from collect import parse, FIELDS

SAMPLE_HTML = """
<ul>
  <li class="member-item">
    <a class="directory-link" href="/x"><span>Acme Sarl</span></a>
    <div class="mb-1">Business Category: <a>Office Supplies</a></div>
    <div class="mb-1 text-muted">Casablanca, Grand Casablanca</div>
  </li>
  <li class="member-item">
    <a class="directory-link" href="/y"><span>Beta LLC</span></a>
    <div class="mb-1">Business Category: <a>Machinery</a></div>
  </li>
  <li class="member-item">
    <!-- no name, should be skipped -->
    <div class="mb-1">Business Category: <a>Ghost</a></div>
  </li>
</ul>
"""


def test_parse_extracts_expected_rows():
    rows = list(parse(SAMPLE_HTML))
    assert len(rows) == 2
    assert rows[0]["name"] == "Acme Sarl"
    assert rows[0]["category"] == "Office Supplies"
    assert rows[0]["location"] == "Casablanca, Grand Casablanca"
    assert rows[1]["name"] == "Beta LLC"
    assert rows[1]["category"] == "Machinery"


def test_parse_defaults_location_to_morocco_when_missing():
    rows = list(parse(SAMPLE_HTML))
    assert rows[1]["location"] == "Morocco"


def test_parse_rows_match_full_schema():
    rows = list(parse(SAMPLE_HTML))
    for r in rows:
        assert set(r.keys()) == set(FIELDS)
        assert r["source"] == "b2bmap.com"
        assert r["website"] == ""
        assert r["contact"] == ""


def test_parse_captures_profile_url_absolute():
    rows = list(parse(SAMPLE_HTML))
    assert rows[0]["b2bmap_url"] == "https://b2bmap.com/x"
    assert rows[1]["b2bmap_url"] == "https://b2bmap.com/y"
