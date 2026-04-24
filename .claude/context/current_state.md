# Current State

**Last updated:** After CP5.1 Pass 3a implementation and CP4.7 methodology hardening.

Update this file at the end of every checkpoint.

## Latest Test Count

**255 passing** (after CP5.1 Pass 3a).

## Active Work

**CP5.1 Pass 3b — Algorithms** (pending brief).

Expected scope (from Pass 2 architectural commitments):
- `sim/round_state.py`: `RoundState` with shallow-clone + frozenset conditions
- `sim/search.py`: beam search K=50/20/10 at depth 3
- Adversarial enemy sub-search (K=20, depth 3)
- Hybrid state threading: EV-collapse with kill/drop branching at 5% threshold
- Scoring function: `kill_value = max_hp + 10 × num_attacks`, `drop_cost = max_hp + 10 × role_multiplier` (Dalai = 2x)
- `sim/initiative.py`: seeded Perception + d20 rolling
- `pf2e/damage_pipeline.py`: strict PF2e damage resolution (attack → damage → Intercept → Shield Block → resistance → temp HP)

Expected test count after Pass 3b: ~295-315.

## Known Regression Anchors

All must pass at every checkpoint:

- **EV 8.55** — Rook longsword reaction Strike with Anthem vs Bandit1 AC 15 (Strike Hard tactic). Located in `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk`.
- **55% prone probability** — Tactical Takedown vs Reflex +5 DC 17. `tests/test_tactics.py`.
- **EV 5.95 per target** — Light mortar 2d6 DC 17 vs Reflex +5. `tests/test_combat_math.py`.
- **Aetregan max HP 15** — After CP4.5. `tests/test_hp.py`.
- **Aetregan Warfare/Deity Lore +7** — Int +4 + trained +3 = +7 at level 1. `tests/test_skills.py`.

## Completed Checkpoints Summary

| CP | Test Count | Key Addition |
|---|---|---|
| CP0 | ~40 | Foundation types |
| CP0.5 | 97 | Corrections and cleanup |
| CP1 | 123 | Tactic dispatcher |
| CP2 | 171 | Grid and spatial |
| CP3 | 181 | Scenario loading |
| CP4 | 199 | Defensive value |
| CP4.5 | 207 | Aetregan reconciliation |
| CP5.1 Pass 3a | 255 | Foundation (data model, skill system, HP tracking, initiative parsing) |
| CP4.6 | 255 | Repo restructuring (no code changes) |
| CP4.7 | 255 | Methodology documentation (no code changes) |

## Next Up

Write CP5.1 Pass 3b brief, then implement.

## Known TODOs

From past checkpoints, things flagged for future resolution:

- **CP5.1 3b:** Support-role multiplier hardcoded to Dalai by name. Refactor to `role_weight` field on Character in CP6.
- **CP5.1 3b:** Reaction policies (Intercept, Shield Block) use greedy heuristics. Optimal reaction timing deferred to CP6.
- **CP5.2:** Multi-enemy coordination (flanking, spread damage) emerges from single-best-response sometimes but isn't explicitly modeled. CP6 upgrade candidate.
- **CP6:** Expectimax enemy search over top-3 enemy plans (currently single-best-response).
- **CP6:** Scoring weight calibration from CP7 feedback.
- **CP8:** Level 2+ character advancement. Aetregan's L2 Plant Banner upgrade is on this.
- **Phase B (post-CP9):** Pathbuilder importer, effects catalog extraction from hard-coded flags.

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN (PF2e rules reference): https://2e.aonprd.com
