from unittest.mock import patch

from contact_info_collect import fetch_contact_info, parse_contact_info

TABLE_HTML = """
<html><body>
<table>
  <tr><td>Company Name:</td><td>PimaAfrica Distribution Sarl AU</td></tr>
  <tr><td>Contact Person:</td><td>Mr. PimaAfrica (Automation Engineer)</td></tr>
  <tr><td>Phone:</td><td>+212669111222</td></tr>
  <tr><td>Whatsapp:</td><td>+212669111222</td></tr>
  <tr><td>Address:</td><td>293, Boulevard abdelmoumen, Casablanca</td></tr>
  <tr><td>Zip Code:</td><td>20340</td></tr>
  <tr><td>State</td><td>Casablanca</td></tr>
  <tr><td>City:</td><td>ad-Dar-al-Bayda</td></tr>
  <tr><td>Country:</td><td>Morocco</td></tr>
</table>
</body></html>
"""

DL_HTML = """
<html><body>
<dl>
  <dt>Contact Person:</dt><dd>Ms. Beta</dd>
  <dt>Phone:</dt><dd>+212611000000</dd>
</dl>
</body></html>
"""


class FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


def test_parse_contact_info_from_table():
    data = parse_contact_info(TABLE_HTML)
    assert data["contact_person"] == "Mr. PimaAfrica (Automation Engineer)"
    assert data["phone"] == "+212669111222"
    assert data["whatsapp"] == "+212669111222"
    assert data["address"] == "293, Boulevard abdelmoumen, Casablanca"
    assert data["zip_code"] == "20340"
    assert data["state"] == "Casablanca"
    assert data["city"] == "ad-Dar-al-Bayda"
    assert data["country"] == "Morocco"


def test_parse_contact_info_from_dl_layout():
    data = parse_contact_info(DL_HTML)
    assert data["contact_person"] == "Ms. Beta"
    assert data["phone"] == "+212611000000"


def test_fetch_contact_info_uses_requests_and_parses():
    with patch("contact_info_collect.requests.get", return_value=FakeResp(TABLE_HTML)):
        data = fetch_contact_info("https://b2bmap.com/pimaafrica-distribution")
    assert data["phone"] == "+212669111222"


def test_fetch_contact_info_returns_empty_when_url_missing():
    assert fetch_contact_info("") == {}


def test_fetch_contact_info_returns_empty_on_http_error():
    import requests as _r
    with patch("contact_info_collect.requests.get", side_effect=_r.RequestException("boom")):
        assert fetch_contact_info("https://b2bmap.com/x") == {}
