"""Tests for sim/catalog/session_init.py."""

import pytest
from pathlib import Path

from sim.catalog.session_init import (
    _extract_enemy_slugs_from_scenario,
    _get_slug,
    initialize_session,
)


class TestGetSlug:
    def test_from_system_slug(self):
        item = {"system": {"slug": "deceptive-tactics"}, "name": "Deceptive Tactics"}
        assert _get_slug(item) == "deceptive-tactics"

    def test_derives_from_name_apostrophe(self):
        item = {"system": {}, "name": "Commander's Banner"}
        assert _get_slug(item) == "commanders-banner"

    def test_derives_from_name_exclamation(self):
        item = {"system": {}, "name": "Strike Hard!"}
        assert _get_slug(item) == "strike-hard"

    def test_derives_from_name_parenthetical(self):
        item = {"system": {}, "name": "Assurance (Thievery)"}
        assert _get_slug(item) == "assurance-thievery"

    def test_prefers_system_slug(self):
        item = {"system": {"slug": "assurance"}, "name": "Assurance (Thievery)"}
        assert _get_slug(item) == "assurance"

    def test_returns_none_for_empty(self):
        assert _get_slug({"system": {}, "name": ""}) is None


class TestExtractEnemySlugs:
    def test_parses_enemy_names(self, tmp_path):
        scenario = tmp_path / "test.scenario"
        scenario.write_text(
            "[meta]\nname = test\n\n[enemies]\n"
            "m1 name=Bandit1 ac=15 ref=5 fort=3 will=2\n"
            "m2 name=Bandit2 ac=16 ref=4 fort=5 will=3\n",
            encoding="utf-8",
        )
        slugs = _extract_enemy_slugs_from_scenario(str(scenario))
        assert "bandit1" in slugs
        assert "bandit2" in slugs

    def test_returns_empty_for_missing_file(self):
        slugs = _extract_enemy_slugs_from_scenario("nonexistent.scenario")
        assert slugs == []

    def test_returns_empty_for_no_enemies_section(self, tmp_path):
        scenario = tmp_path / "test.scenario"
        scenario.write_text("[meta]\nname = test\n", encoding="utf-8")
        slugs = _extract_enemy_slugs_from_scenario(str(scenario))
        assert slugs == []


class TestInitializeSession:
    def test_populates_from_local(self, tmp_path):
        cache_path = str(tmp_path / "test_cache.sqlite")
        cache = initialize_session(
            character_paths=["characters/fvtt-aetregan.json"],
            cache_path=cache_path,
            verbose=False,
        )
        items = cache.list_items()
        slugs = {i["slug"] for i in items}
        assert "deceptive-tactics" in slugs
        assert "commanders-banner" in slugs
        assert "shield-block" in slugs
        cache.close()

    def test_skips_cached_items(self, tmp_path):
        cache_path = str(tmp_path / "test_cache.sqlite")
        c1 = initialize_session(
            character_paths=["characters/fvtt-aetregan.json"],
            cache_path=cache_path,
            verbose=False,
        )
        count1 = len(c1.list_items())
        c1.close()

        c2 = initialize_session(
            character_paths=["characters/fvtt-aetregan.json"],
            cache_path=cache_path,
            verbose=False,
        )
        count2 = len(c2.list_items())
        c2.close()
        assert count1 == count2

    def test_handles_duplicate_slugs_across_characters(self, tmp_path):
        cache_path = str(tmp_path / "test_cache.sqlite")
        cache = initialize_session(
            character_paths=[
                "characters/fvtt-aetregan.json",
                "characters/fvtt-rook.json",
            ],
            cache_path=cache_path,
            verbose=False,
        )
        # Shield Block appears in both — dedup should keep version with rules
        item = cache.get_item("shield-block")
        assert item is not None
        assert item["rule_count"] >= 1
        cache.close()

    def test_handles_missing_scenario(self, tmp_path):
        cache_path = str(tmp_path / "test_cache.sqlite")
        cache = initialize_session(
            character_paths=["characters/fvtt-aetregan.json"],
            scenario_path="nonexistent.scenario",
            cache_path=cache_path,
            verbose=False,
        )
        assert cache is not None
        cache.close()

    def test_all_four_characters(self, tmp_path):
        cache_path = str(tmp_path / "test_cache.sqlite")
        cache = initialize_session(
            character_paths=[
                "characters/fvtt-aetregan.json",
                "characters/fvtt-rook.json",
                "characters/fvtt-dalai.json",
                "characters/fvtt-erisen.json",
            ],
            cache_path=cache_path,
            verbose=False,
        )
        items = cache.list_items()
        with_rules = sum(1 for i in items if i["rule_count"] > 0)
        assert len(items) >= 40  # ~70+ unique items across 4 characters
        assert with_rules >= 20  # many items have rules
        cache.close()
