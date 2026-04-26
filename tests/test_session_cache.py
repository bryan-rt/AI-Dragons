"""Tests for sim/catalog/session_cache.py."""

import json
import os

import pytest

from sim.catalog.session_cache import SessionCache


@pytest.fixture
def cache(tmp_path):
    path = str(tmp_path / "test_cache.sqlite")
    c = SessionCache(path)
    yield c
    c.close()


class TestSessionCacheCreation:
    def test_creates_db_file(self, tmp_path):
        path = str(tmp_path / "new_cache.sqlite")
        c = SessionCache(path)
        c.close()
        assert os.path.exists(path)

    def test_context_manager(self, tmp_path):
        path = str(tmp_path / "ctx_cache.sqlite")
        with SessionCache(path) as c:
            c.store_item("test", "feats", "feat", "Test", "{}", "[]", "local")
            assert c.is_cached("test")
        assert os.path.exists(path)


class TestSessionCacheStoreAndRetrieve:
    def test_store_and_get_item(self, cache):
        cache.store_item(
            "deceptive-tactics", "feats", "feat", "Deceptive Tactics",
            '{"name":"Deceptive Tactics"}', '[{"key":"FlatModifier"}]', "local",
        )
        item = cache.get_item("deceptive-tactics")
        assert item is not None
        assert item["name"] == "Deceptive Tactics"
        assert item["rule_count"] == 1
        assert item["source"] == "local"

    def test_is_cached_false_before_store(self, cache):
        assert cache.is_cached("nonexistent-slug") is False

    def test_is_cached_true_after_store(self, cache):
        cache.store_item("test-slug", "feats", "feat", "Test", "{}", "[]", "local")
        assert cache.is_cached("test-slug") is True

    def test_get_rule_elements_empty_for_missing(self, cache):
        assert cache.get_rule_elements("nonexistent") == []

    def test_get_rule_elements_returns_list(self, cache):
        rules = '[{"key":"FlatModifier","value":1}]'
        cache.store_item("test", "feats", "feat", "Test", "{}", rules, "local")
        result = cache.get_rule_elements("test")
        assert result == [{"key": "FlatModifier", "value": 1}]

    def test_list_items(self, cache):
        cache.store_item("slug-a", "feats", "feat", "A", "{}", "[]", "local")
        cache.store_item("slug-b", "spells", "spell", "B", "{}", "[]", "local")
        items = cache.list_items()
        assert len(items) == 2
        slugs = {i["slug"] for i in items}
        assert slugs == {"slug-a", "slug-b"}


class TestSessionCacheDuplicateHandling:
    def test_keeps_version_with_more_rules(self, cache):
        cache.store_item(
            "shield-block", "feats", "feat", "Shield Block",
            "{}", '[{"key":"Note"}]', "local",
        )
        cache.store_item(
            "shield-block", "feats", "feat", "Shield Block",
            "{}", "[]", "local",
        )
        item = cache.get_item("shield-block")
        assert item["rule_count"] == 1

    def test_no_overwrite_when_equal(self, cache):
        cache.store_item("test", "feats", "feat", "Original",
                         '{"original":true}', "[]", "local")
        cache.store_item("test", "feats", "feat", "Overwrite",
                         '{"original":false}', "[]", "local")
        item = cache.get_item("test")
        assert item["name"] == "Original"

    def test_replaces_with_more_rules(self, cache):
        cache.store_item("test", "feats", "feat", "Fewer",
                         "{}", "[]", "local")
        cache.store_item("test", "feats", "feat", "More",
                         "{}", '[{"key":"FlatModifier"}]', "local")
        item = cache.get_item("test")
        assert item["name"] == "More"
        assert item["rule_count"] == 1


class TestSessionCacheSourceField:
    def test_local_source(self, cache):
        cache.store_item("local-item", "feats", "feat", "Local", "{}", "[]", "local")
        assert cache.get_item("local-item")["source"] == "local"

    def test_github_source(self, cache):
        cache.store_item("github-item", "bestiary", "npc", "GitHub",
                         "{}", "[]", "github")
        assert cache.get_item("github-item")["source"] == "github"
