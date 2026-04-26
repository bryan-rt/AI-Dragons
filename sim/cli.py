"""CLI entry point for the PF2e Tactical Simulator.

Usage:
    python -m sim --scenario scenarios/checkpoint_1_strike_hard.scenario
    python -m sim --scenario path.scenario --seed 42 --debug-search
    python -m sim --scenario path.scenario --full-combat --seed 42
"""

from __future__ import annotations

import argparse
import logging
import sys

from sim.scenario import load_scenario
from sim.search import format_recommendation, run_simulation


def main(argv: list[str] | None = None) -> None:
    """Run the simulator from CLI arguments."""
    parser = argparse.ArgumentParser(description="PF2e Tactical Simulator")
    parser.add_argument(
        "--scenario", required=True, help="Path to .scenario file",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed (default: 42)",
    )
    parser.add_argument(
        "--full-combat", action="store_true",
        help="Run full combat to completion (default: single-round only)",
    )
    parser.add_argument(
        "--debug-search", action="store_true",
        help="Dump beam state per depth to stderr",
    )
    args = parser.parse_args(argv)

    if args.debug_search:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
        logging.getLogger("sim.search").setLevel(logging.DEBUG)

    scenario = load_scenario(args.scenario)

    if args.full_combat:
        from sim.solver import solve_combat, format_combat_solution
        solution = solve_combat(scenario, seed=args.seed)
        print(format_combat_solution(solution))
    else:
        recommendations = run_simulation(scenario, seed=args.seed)
        for rec in recommendations:
            print(format_recommendation(rec))


if __name__ == "__main__":
    main()
