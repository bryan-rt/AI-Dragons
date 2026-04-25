# Current State

**Last updated:** CP5.2 complete.

## Latest Test Count

**393 passing** (362 prior + 31 new).

## Active Work

**CP5.2 — Class Features** (Pass 3 complete).

### Completed (this checkpoint)
1. 6 new ActionType entries: ANTHEM, SOOTHE, MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH, TAUNT
2. 4 new Character flags: has_courageous_anthem, has_soothe, has_light_mortar, has_taunt
3. Party factories updated (Dalai, Erisen, Rook)
4. Mortar auto-deploy at combat start via has_light_mortar
5. [combatant_state] scenario file section
6. _effective_status_bonus_attack/damage helpers + STRIKE integration
7. Anthem state propagation in apply_outcome_to_state
8. conditions_removed handling in apply_outcome_to_state
9. 6 new evaluators: ANTHEM, SOOTHE, MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH, TAUNT
10. INTERCEPT_ATTACK extended to 15-ft range vs taunted enemy
11. All new evaluators registered in dispatcher (20 total)
12. generate_candidates updated for all 6 new action types
13. 31 new tests
14. Strike Hard EV 8.55 (9th consecutive verification)

## Known Regression Anchors

- **EV 8.55** — Strike Hard. Verified 9 times through CP5.2.
- **55% prone** — Tactical Takedown.
- **EV 5.95** — Mortar.
- **Aetregan HP 15**
- **Lore +7**

## Known Simplifications (CP6 calibration targets)

- ANTHEM remaining_strikes: capped at min(actions_remaining, 2)
- ANTHEM/SOOTHE role multiplier: hardcoded Dalai name check
- TAUNT score: rough avg_enemy_dmg calculation
- Mortar target-point selection: targets all enemies (simplified burst)
- Composition conflict handling: deferred (only one composition at L1)
- RAISE_SHIELD danger estimation: approximate
- Enemy MAP not tracked per snapshot

## Next Checkpoint

CP5.3 — General skill actions (Aid, Recall Knowledge, Seek, Hide, Sneak)

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
