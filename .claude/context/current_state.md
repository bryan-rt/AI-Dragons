# Current State

**Last updated:** After CP5.1.3b (Algorithms) — commit 0208c38.

Update this file at the end of every checkpoint.

## Latest Test Count

**315 passing** (after CP5.1.3b).

## Active Work

**CP5.1.3c — Action Evaluators** (Pass 1 planning not yet started).

Expected scope (from ROADMAP):
- 15 ActionType evaluators: STRIDE, STEP, STRIKE, TRIP, DISARM, RAISE_SHIELD,
  SHIELD_BLOCK (reaction), PLANT_BANNER (stub), ACTIVATE_TACTIC, DEMORALIZE,
  CREATE_A_DIVERSION (Warfare Lore via Deceptive Tactics), FEINT (same),
  INTERCEPT_ATTACK (Guardian reaction), EVER_READY (Guardian reaction refresh),
  END_TURN
- `--debug-search` CLI flag (deferred from CP5.1.3b)
- Output formatter for RoundRecommendation
- End-to-end integration test: load scenario → run full round → recommendation
- Expected test count: ~365-385 (~50-70 new tests)

## Known Regression Anchors

All must pass at every checkpoint:

- **EV 8.55** — Rook longsword reaction Strike with Anthem vs Bandit1 AC 15.
  `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk`.
  Verified 7 times through CP5.1.3b.
- **55% prone probability** — Tactical Takedown vs Reflex +5 DC 17.
- **EV 5.95 per target** — Light mortar 2d6 DC 17 vs Reflex +5.
- **Aetregan max HP 15** — Elf 6 + (Commander 8 + Con +1) × 1.
- **Aetregan Warfare/Deity Lore +7** — Int +4 + trained proficiency +3.

## Completed Checkpoints Summary

| CP | Tests | Key Addition |
|---|---|---|
| CP0 | ~40 | Foundation types |
| CP0.5 | 97 | Corrections and cleanup |
| CP1 | 123 | Tactic dispatcher |
| CP2 | 171 | Grid and spatial |
| CP3 | 181 | Scenario loading |
| CP4 | 199 | Defensive value |
| CP4.5 | 207 | Aetregan reconciliation |
| CP5.1.3a | 255 | Foundation (data model, skills, HP tracking) |
| CP4.6 | 255 | Repo restructuring (no code changes) |
| CP4.7 | 255 | Methodology documentation (no code changes) |
| CP5.1.3b | 315 | Algorithms (search, damage pipeline, initiative, state threading) |

## Architecture added in CP5.1.3b

- `sim/round_state.py` — CombatantSnapshot (16 fields), EnemySnapshot (14 fields),
  RoundState with from_scenario, with_pc_update, with_enemy_update
- `pf2e/damage_pipeline.py` — resolve_strike_outcome: Intercept → Shield Block →
  Resistance → Temp HP → Real HP (AoN-verified order)
- `sim/initiative.py` — roll_initiative: seeded isolated RNG, partial override,
  enemy-beats-PC tiebreaker
- `sim/search.py` — beam_search_turn K=(50,20,10), adversarial_enemy_turn K=(20,10,5),
  simulate_round, score_state, ScoreBreakdown, SearchConfig, TurnPlan

## Key Decisions since last update

- D21: RoundState as frozen snapshots (cheap branching, shared Character)
- D22: Kill/drop branching collapses to two worlds per crossing target
- D23: Reactions as full search-branching (C2). 15s timing target. C1 escape hatch
  available if real evaluators blow the budget in CP5.1.3c.
- D24: Temp HP absorption not counted as damage_taken in scoring

## Next Up

Write CP5.1.3c Pass 1 planning brief.

Key design questions to surface in CP5.1.3c Pass 1:
1. STRIDE destination heuristic — 5 categories + "adjacent to wounded ally" (6th)
2. CREATE_A_DIVERSION / FEINT using Warfare Lore via Deceptive Tactics flag
3. How ACTIVATE_TACTIC wraps existing evaluate_tactic() — probably a thin wrapper
4. Whether INTERCEPT_ATTACK / SHIELD_BLOCK evaluators wire into existing
   resolve_strike_outcome or duplicate the logic
5. Timing reality check — CP5.1.3b's mock evaluators ran in 0.07s; real evaluators
   will be heavier. Surface if C2 reaction branching needs D23 escape hatch.

## Known TODOs

- Reaction timing reality check (C2 vs C1) — defer decision to after real evaluators land
- Support-role multiplier hardcoded to Dalai by name → CP6 refactor to role_weight field
- Reaction policies use greedy heuristics in some paths → CP6 optimal timing
- Multi-enemy coordination not explicitly modeled → CP6 upgrade candidate

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
- Commit 0208c38: CP5.1.3b complete (315 tests, EV 8.55 ×7)
