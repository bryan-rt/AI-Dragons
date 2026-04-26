"""Tests for sim/catalog/github_fetcher.py. All network calls mocked."""

import json
from unittest.mock import MagicMock, patch

import urllib.error

from sim.catalog.github_fetcher import (
    FOUNDRY_RAW_BASE,
    _fetch_url,
    fetch_bestiary_creature,
    fetch_rule_elements,
)


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode("utf-8")
    return mock


class TestFetchUrl:
    def test_returns_parsed_json(self):
        data = {"name": "Test", "system": {"rules": []}}
        with patch("urllib.request.urlopen", return_value=_mock_response(data)):
            result = _fetch_url("https://example.com/test.json")
        assert result == data

    def test_returns_none_on_404(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
            result = _fetch_url("https://example.com/missing.json")
        assert result is None

    def test_retries_on_network_error(self):
        call_count = 0

        def flaky_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise urllib.error.URLError("connection reset")
            return _mock_response({"name": "test"})

        with patch("urllib.request.urlopen", side_effect=flaky_urlopen):
            with patch("time.sleep"):
                result = _fetch_url("https://example.com/test.json")
        assert result is not None
        assert call_count == 3


class TestFetchRuleElements:
    def test_uses_hint_pack_first(self):
        data = {"name": "Test Feat", "system": {"rules": [{"key": "FlatModifier"}]}}
        urls_tried = []

        def mock_urlopen(req, **kwargs):
            urls_tried.append(req.full_url)
            if "class-features" in req.full_url:
                return _mock_response(data)
            raise urllib.error.HTTPError(None, 404, "Not Found", {}, None)

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep"):
                result = fetch_rule_elements("test-feat", hint_pack="class-features")

        assert result is not None
        assert urls_tried[0].endswith("class-features/test-feat.json")

    def test_returns_none_when_not_found(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
            with patch("time.sleep"):
                result = fetch_rule_elements("nonexistent-feat")
        assert result is None


class TestFetchBestiary:
    def test_returns_creature_data(self):
        data = {"name": "Bandit", "type": "npc", "system": {"rules": []}}

        def mock_urlopen(req, **kwargs):
            if "pathfinder-bestiary" in req.full_url:
                return _mock_response(data)
            raise urllib.error.HTTPError(None, 404, "Not Found", {}, None)

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep"):
                result = fetch_bestiary_creature("bandit")
        assert result is not None
        assert result["name"] == "Bandit"


class TestFoundryBaseUrl:
    def test_uses_v14_dev_branch(self):
        assert "v14-dev" in FOUNDRY_RAW_BASE
