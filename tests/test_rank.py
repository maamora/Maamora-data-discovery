from rank import slug, sort_key


def test_slug_lowercases_and_underscores():
    assert slug("Office Supplies") == "office_supplies"


def test_slug_strips_punctuation():
    assert slug("Machinery & Industrial Supplies") == "machinery_industrial_supplies"


def test_slug_falls_back_when_empty():
    assert slug("!!!") == "uncategorised"


def test_sort_key_orders_desc_by_score():
    rows = [{"score": "3.5"}, {"score": "4.8"}, {"score": ""}, {"score": "4.1"}]
    rows.sort(key=sort_key)
    assert [r["score"] for r in rows] == ["4.8", "4.1", "3.5", ""]


def test_sort_key_handles_bad_score():
    assert sort_key({"score": "n/a"}) == 0.0
    assert sort_key({"score": None}) == 0.0
    assert sort_key({}) == 0.0
