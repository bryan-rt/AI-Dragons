# Current State

**Last updated:** After CP4.5 completion, CP5.1 Pass 3a in progress on CLI agent.

Update this file at the end of every checkpoint.

## Latest Test Count

**207 passing** (after CP4.5). Expected ~235-245 after Pass 3a.

## Active Work

**CP5.1 Pass 3a — Foundation Implementation**

Brief: `.claude/briefs/checkpoint_5_1_pass_3a_brief.md`

Scope:
- `Skill` enum + `SKILL_ABILITY` lookup
- `Character` extensions: skill_proficiencies, lores, feat flags (has_plant_banner, has_deceptive_tactics, has_lengthy_diversion)
- `skill_bonus()`, `lore_bonus()` helpers
- Aetregan full skill data from JSON
- Squadmate HP and skill grounded defaults
- `ActionType` enum (15 types)
- `Action`, `ActionOutcome`, `ActionResult` dataclasses
- `CombatantState` HP tracking extensions
- `EnemyState` HP and perception extensions
- Scenario parser `[initiative]` section
- Tests across 5 new test files

Not in Pass 3a (deferred to 3b and 3c):
- `RoundState`, search algorithms, damage pipeline, scoring (3b)
- Per-action evaluators, stride destinations, output formatter (3c)

## Known Regression Anchors

All must pass at every checkpoint:

- **EV 8.55** — Rook longsword reaction Strike with Anthem vs Bandit1 AC 15 (Strike Hard tactic). Located in `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk`.
- **55% prone probability** — Tactical Takedown vs Reflex +5 DC 17. Located in `tests/test_tactics.py`.
- **EV 5.95 per target** — Light mortar 2d6 DC 17 vs Reflex +5. Located in `tests/test_combat_math.py`.
- **Aetregan max HP 15** — After CP4.5. Located in `tests/test_hp.py`.

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
| CP5.1 Pass 3a | ~235-245 (expected) | Foundation (in progress) |

## Next Up

After Pass 3a validates, CP5.1 Pass 3b will be written. Scope: search algorithms, state threading, damage pipeline, scoring function. ~40-60 new tests.

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
