import io
import json
import urllib.error
from unittest import mock

import pytest

from doppleganger import updater


def _fake_release(tag):
    body = json.dumps({"tag_name": tag, "body": "", "assets": [
        {"name": "Doppleganger.exe", "url": "API_URL", "browser_download_url": "PUBLIC_URL"}]}).encode()

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    return lambda req, timeout: Resp(body)


def test_version_ordering():
    assert updater.parse_version("v0.1.12") > updater.parse_version("0.1.9")
    assert updater.parse_version("0.2.1") > updater.parse_version("0.1.99")


def test_check_finds_newer_release():
    with mock.patch.object(updater, "current_version", return_value="0.1.5"), \
         mock.patch("urllib.request.urlopen", _fake_release("v0.1.7")):
        rel = updater.check("o/r")
    assert rel.version == "0.1.7" and rel.download_url == "PUBLIC_URL"


def test_check_up_to_date_and_token_url():
    with mock.patch.object(updater, "current_version", return_value="0.1.7"), \
         mock.patch("urllib.request.urlopen", _fake_release("v0.1.7")):
        assert updater.check("o/r") is None
    with mock.patch.object(updater, "current_version", return_value="0.1.1"), \
         mock.patch("urllib.request.urlopen", _fake_release("v0.1.7")):
        assert updater.check("o/r", token="t").download_url == "API_URL"


def test_private_repo_gives_helpful_error():
    def not_found(req, timeout):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)

    with mock.patch("urllib.request.urlopen", not_found):
        with pytest.raises(updater.UpdateError, match="update_token"):
            updater.check("o/r")
