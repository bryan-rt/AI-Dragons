# Current State

**Last updated:** CP5.1.3c Steps 1-3 complete (blocker fields + conditions wiring).

## Latest Test Count

**315 passing** (unchanged — Steps 1-3 are structural additions, no new tests yet).

## Active Work

**CP5.1.3c — Action Evaluators** (Pass 3 in progress, Steps 1-3 of 14 complete).

### Completed steps (this session)
1. Added `map_count: int = 0` and `conditions: frozenset[str]` to `CombatantSnapshot`
2. Added `conditions: frozenset[str]` to `EnemySnapshot`
3. Updated `apply_outcome_to_state` in `sim/search.py` to union non-hardcoded conditions into the frozenset
4. Added Ever Ready initialization comment in `sim/initiative.py`
5. Verified all 315 existing tests still pass

### Remaining steps (next session picks up here)
4. Implement 14 evaluators in `pf2e/actions.py` (END_TURN, PLANT_BANNER, RAISE_SHIELD, STEP, STRIDE, STRIKE, TRIP, DISARM, DEMORALIZE, CREATE_A_DIVERSION, FEINT, SHIELD_BLOCK, INTERCEPT_ATTACK, ACTIVATE_TACTIC)
5. Implement `evaluate_action()` dispatcher in `pf2e/actions.py`
6. Implement `generate_candidates()` in `sim/candidates.py`
7. Wire real callables into `simulate_round()` in `sim/search.py`
8. Create `sim/cli.py` + `sim/__main__.py` (CLI entry point)
9. Implement `RoundRecommendation` + `format_recommendation()` in `sim/search.py`
10. Write tests (~46 new): `tests/test_evaluators.py`, `tests/test_integration.py`, `tests/test_cli.py`
11. Full regression: `pytest tests/ -v` → ~361 passing
12. Verify Strike Hard EV 8.55 (8th verification)
13. Update `CHANGELOG.md`
14. Update this file with final test count

### Key blockers resolved in this commit
- `map_count` field on CombatantSnapshot (needed for MAP tracking in STRIKE/TRIP/DISARM)
- `conditions` frozenset on both snapshot types (needed for immunity tracking in DEMORALIZE/CREATE_A_DIVERSION)
- `apply_outcome_to_state` now unions non-hardcoded condition strings into the frozenset

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 7 times through CP5.1.3b. 8th pending.
- **55% prone** — Tactical Takedown.
- **EV 5.95** — Mortar.
- **Aetregan HP 15**
- **Lore +7**

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
