# Current State

**Last updated:** CP5.4 complete.

## Latest Test Count

**545 passing.**

## Active Work

**CP5.4 — Spell Chassis and Dalai's Combat Spells** (complete).

### Completed
- Parameterized spell chassis: 4 pattern evaluators (auto-hit, condition, attack roll, save damage)
- 3 AoN-verified spells: Fear, Force Barrage, Needle Darts
- CAST_SPELL ActionType with candidate generation and range filtering
- Character.known_spells populated by importer from SPELL_REGISTRY
- Dalai now casts Force Barrage in combat (replaces Create a Diversion)
- DamageType.FORCE, spell_attack_bonus() added
- 26 new tests, EV 7.65 (16th verification)

### AoN Corrections Applied
- Fear: 2 actions (not 1), AoN ID=1524
- Needle Darts: spell attack roll (not save), 3d4 (not 2d4), cantrip, AoN ID=1375
- Force Barrage: range 120 ft (not 60), AoN ID=1536

## Known Regression Anchors

- **EV 7.65** — Strike Hard (Rook Earthbreaker). 16th verification.

## Next Checkpoint

CP8 — Level advancement (L2-L5), feat progression

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN: https://2e.aonprd.com
