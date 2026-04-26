# Current State

**Last updated:** CP6 complete.

## Latest Test Count

**444 passing** (420 prior + 24 new).

## Active Work

**CP6 — Full Combat Solver** (Pass 3 complete).

### Completed
- sim/solver.py: solve_combat(), _run_single_combat(), 5-plan seed variation
- CombatSolution, RoundLog, TurnLog dataclasses
- _reset_turn_state(): map_count=0, actions_remaining=3, shield/anthem/taunt clear
- _end_of_turn_cleanup(): frightened decrement per turn
- STAND evaluator (clears prone, 1 action)
- condition_durations field on both snapshot types
- Difficulty rating + cumulative EV scoring
- format_combat_solution() round-by-round output
- --full-combat CLI flag (single-round mode preserved)
- Strike Hard EV 8.55 (11th consecutive verification)

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 11 times through CP6.
- **Scenario 1** — Victory in 1 round (trivial)
- **Scenario 2** — Victory in 2 rounds (trivial)

## Known Simplifications (CP7 calibration targets)

- Top 5 plans via seed variation — true branching deferred
- Difficulty rating thresholds — needs calibration
- Cumulative EV weights — round bonus x10, survival x0.5
- STAND score delta — rough approximation
- condition_durations field added but not fully used yet

## Next Checkpoint

CP7 — Validation sweep, scenario tuning, scoring calibration

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
