"""Tests for sim/cli.py — CLI smoke tests (CP5.1.3c Step 10)."""

import sys

import pytest


class TestCli:

    def test_cli_scenario_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """CLI runs without error and produces output."""
        from sim.cli import main
        main(["--scenario", "scenarios/checkpoint_1_strike_hard.scenario", "--seed", "42"])
        out = capsys.readouterr().out
        assert "Recommendation" in out

    def test_cli_debug_search_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--debug-search produces output without crashing."""
        from sim.cli import main
        main([
            "--scenario", "scenarios/checkpoint_1_strike_hard.scenario",
            "--seed", "42", "--debug-search",
        ])
        out = capsys.readouterr().out
        assert len(out) > 0
