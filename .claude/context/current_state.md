# Current State

**Last updated:** CP7 complete.

## Latest Test Count

**444 passing.**

## Active Work

**CP7 — Validation and Calibration** (complete).

### Completed
- Survival bonus: flat 15 per surviving PC + 0.5 × HP (was only 0.5 × HP)
- Threat-weighted Taunt/Raise Shield EV (not just adjacent enemies)
- score_delta added to Create a Diversion, Demoralize, Feint, Raise Shield
- Recall Knowledge party-wide damage type advantage
- Scenario 2 anthem_active=false (Dalai casts as action)
- Verified: hidden bonus doesn't leak into reaction Strikes
- Strike Hard EV 8.55 (12th consecutive verification)

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 12 times.
- **Scenario 1** — Victory in 1 round (trivial), Score ~245
- **Scenario 2 seed 42** — Victory in 2 rounds, Score ~250
- **Scenario 2 seed 7** — Victory in 2 rounds, Score ~297

## Known Calibration Targets (CP9+)

- Difficulty rating thresholds (round-count based only)
- Mortar chain credit discount (0.3/0.35 heuristic)
- Skill-action filtering threshold (not yet implemented — global 25% planned)
- Per-round re-branching (not yet implemented — planned for CP8+)
- Survival bonus weights (15 per survivor + 0.5×HP, verify with more scenarios)

## Next Checkpoint

CP8 — Level advancement (L2-L5), feat progression

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
