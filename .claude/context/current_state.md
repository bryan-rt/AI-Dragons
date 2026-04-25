# Current State

**Last updated:** CP5.1.3c complete (Steps 1-14).

## Latest Test Count

**361 passing** (315 existing + 46 new).

## Active Work

**CP5.1.3c — Action Evaluators** (Pass 3 complete).

### Completed (this checkpoint)
1. Added `map_count: int = 0` and `conditions: frozenset[str]` to `CombatantSnapshot`
2. Added `conditions: frozenset[str]` to `EnemySnapshot`
3. Updated `apply_outcome_to_state` in `sim/search.py` to union non-hardcoded conditions
4. Ever Ready initialization comment in `sim/initiative.py`
5. 14 action evaluators in `pf2e/actions.py`
6. `evaluate_action()` dispatcher (14 types, EVER_READY excluded)
7. `generate_candidates()` in `sim/candidates.py`
8. Wired real callables into `simulate_round()` via `run_simulation()`
9. Action economy tracking (MAP + actions_remaining) in beam search loop
10. EV-collapse path extended to apply non-HP state changes
11. `sim/cli.py` + `sim/__main__.py` (CLI entry point)
12. `RoundRecommendation` + `format_recommendation()` in `sim/search.py`
13. 46 new tests: `tests/test_evaluators.py`, `tests/test_cli.py`
14. Full regression: 361 passing, Strike Hard EV 8.55 (8th verification)

### Modules added/modified
- `pf2e/actions.py` — 14 evaluators + dispatcher + geometry helpers
- `sim/candidates.py` — candidate action generation (new)
- `sim/search.py` — RoundRecommendation, format_recommendation, run_simulation, action economy tracking
- `sim/cli.py` — CLI entry point (new)
- `sim/__main__.py` — python -m sim support (new)
- `tests/test_evaluators.py` — 46 evaluator + integration tests (new)
- `tests/test_cli.py` — 2 CLI smoke tests (new)

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 8 times through CP5.1.3c.
- **55% prone** — Tactical Takedown.
- **EV 5.95** — Mortar.
- **Aetregan HP 15**
- **Lore +7**

## Known Simplifications (CP6 calibration targets)

- RAISE_SHIELD danger estimation: `Σ enemy_damage × P(targets_actor) × 0.10`
- STRIDE flanking: no LoS check
- CREATE_A_DIVERSION: next-turn off-guard carry-over not scored
- DISARM crit success: approximated as -2 penalty (item drop not modeled)
- SHIELD_BLOCK: shield breakage not modeled
- Enemy MAP not tracked per snapshot (overestimates enemy damage)
- EV-collapse applies non-HP changes from most-probable outcome (heuristic)

## Next Checkpoint

CP5.2 — Class features (Dalai Anthem, Erisen Mortar, Rook Taunt)

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
