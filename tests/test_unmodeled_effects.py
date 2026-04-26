"""Tests for the unmodeled effects check (B+.2)."""

import pytest
from io import StringIO
from unittest.mock import patch

from sim.catalog.session_init import (
    _HANDLED_KINDS,
    _UNMODELED_BUT_KNOWN,
    _check_unmodeled_effects,
)


class TestCheckUnmodeledEffects:

    def test_no_crash_on_all_four_characters(self):
        """Scanning all 4 party JSONs must not raise."""
        paths = [
            "characters/fvtt-aetregan.json",
            "characters/fvtt-rook.json",
            "characters/fvtt-dalai.json",
            "characters/fvtt-erisen.json",
        ]
        results = _check_unmodeled_effects(paths, verbose=False)
        assert isinstance(results, list)

    def test_finds_substitute_roll(self):
        """Assurance's SubstituteRoll should be flagged as unmodeled."""
        results = _check_unmodeled_effects(
            ["characters/fvtt-aetregan.json"], verbose=False,
        )
        # desc format: "SubstituteRoll (Assurance — ...)"
        kinds_found = {desc.split(" (")[0] for _, _, desc in results}
        assert "SubstituteRoll" in kinds_found

    def test_skips_handled_kinds(self):
        """GrantItem, ChoiceSet, etc. should NOT appear in results."""
        results = _check_unmodeled_effects(
            ["characters/fvtt-aetregan.json",
             "characters/fvtt-rook.json",
             "characters/fvtt-dalai.json",
             "characters/fvtt-erisen.json"],
            verbose=False,
        )
        flagged_kinds = set()
        for _, _, desc in results:
            # desc format: "SubstituteRoll (Assurance — ...)"
            kind = desc.split(" (")[0]
            flagged_kinds.add(kind)
        for handled in _HANDLED_KINDS:
            assert handled not in flagged_kinds, (
                f"{handled} is in _HANDLED_KINDS but was flagged as unmodeled"
            )

    def test_suppresses_output_when_not_verbose(self, capsys):
        """verbose=False should produce no stdout output."""
        _check_unmodeled_effects(
            ["characters/fvtt-aetregan.json"], verbose=False,
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_prints_info_when_verbose(self, capsys):
        """verbose=True should print [INFO] lines for unmodeled effects."""
        _check_unmodeled_effects(
            ["characters/fvtt-aetregan.json"], verbose=True,
        )
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out

    def test_handles_missing_file_gracefully(self):
        """Missing character file should not crash."""
        results = _check_unmodeled_effects(
            ["nonexistent.json"], verbose=False,
        )
        assert results == []


class TestPf2eEffectsModuleImportable:
    def test_import_pf2e_effects(self):
        """The placeholder pf2e/effects package must be importable."""
        import pf2e.effects  # noqa: F401
