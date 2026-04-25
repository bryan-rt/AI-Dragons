# Current State

**Last updated:** CP5.3 complete.

## Latest Test Count

**417 passing** (393 prior + 24 new).

## Active Work

**CP5.3 — General Skill Actions** (Pass 3 complete).

### Completed (this checkpoint)
1. 5 new ActionType entries: RECALL_KNOWLEDGE, HIDE, SNEAK, SEEK, AID
2. weakness/resistance fields on EnemyState and EnemySnapshot
3. Scenario parser extension: weakness_*/resistance_* keys
4. New scenario: checkpoint_2_two_bandits.scenario (2 enemies, W/R)
5. Mortar friendly fire fix (subtracts ally damage from score)
6. _has_recalled() helper for conditional W/R application
7. STRIKE: conditional W/R, Hidden +2 attack, clears Hidden after
8. STEP confirmed: does not clear Hidden
9. 5 new evaluators: RECALL_KNOWLEDGE, HIDE, SNEAK, SEEK, AID
10. All registered in dispatcher (25 total)
11. generate_candidates updated for all 5 new types
12. Probability helpers added
13. Strike Hard EV 8.55 (10th consecutive verification)

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 10 times through CP5.3.
- **55% prone** — Tactical Takedown.
- **EV 5.95** — Mortar.
- **checkpoint_2** — New 2-bandit scenario (EV targets TBD from run)

## Known Simplifications (CP6 calibration targets)

- HIDE cover proxy: "not adjacent to any enemy" — no LoS check
- RECALL_KNOWLEDGE DC: flat 15 — no level-based table
- RECALL_KNOWLEDGE: Society only for humanoids — no creature-type routing
- AID: uses actor's highest skill — no action-type matching
- AID: 0.5 next-round discount — calibrate with multi-round sim
- SNEAK destination filter: no LoS check for cover maintenance
- Mortar friendly fire: simplified (adjacent to enemy = in burst)

## Next Checkpoint

CP6 — Multi-round simulation, scoring calibration, multi-buff refactor

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
