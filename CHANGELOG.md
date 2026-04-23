# Changelog

## [0.5] - Foundation Cleanup

### Corrections from initial brief
- **Mortar EV per target**: 5.95, not 5.60 as originally stated.
  The boundary case `total <= DC-10` includes equality, so with
  Erisen's mortar (DC 17) vs a Reflex +5 enemy, both rolls 1 AND 2
  produce critical failures (totals 6 and 7, both <= 7).
  Brief originally undercounted to 1 crit fail; correct count is 2.

- **Aetregan Wis**: Corrected from 11 to 12. PF2e Remaster attribute
  boosts increase a modifier by 1 (effectively +2 to score). Score 11
  is not achievable via boosts from 10.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2110)

- **Save bonuses**: Several derivations in the brief were off by 1
  due to incorrect ability modifier assumptions:
  - Aetregan Will: now +6 (Wis 12 -> mod +1, expert +5). Was +5.
  - Aetregan Perception: now +4 (Wis +1, trained +3). Was +3.
  - Dalai Reflex: +5 (Dex 14 -> +2, trained +3). Brief said +6.
  - Dalai Will: +5 (Wis 10 -> +0, expert +5). Brief said +6.

  Derivation from ability scores is the ground truth.

### Foundation design choices
- **Frozen Character, mutable CombatantState**: Character represents
  an immutable build. Per-round combat state (reactions, conditions,
  shield raised, status bonuses) lives on CombatantState wrapper.

- **Trait strings, not enums**: Weapon traits are a frozenset of
  lowercase strings (e.g., "finesse", "agile", "thrown_10").
  Open-ended without enum maintenance burden. Validated implicitly
  by trait-checking properties on Weapon.

- **D20Outcomes enumeration**: All EV calculations go through a
  single `enumerate_d20_outcomes(bonus, dc)` function that counts
  d20 faces by degree of success, with nat 1/20 rules applied.
  This is the load-bearing primitive for both attack EV and save EV.

### Bug fixes (Checkpoint 0.5)
- `Weapon.is_ranged`: now correctly returns True for thrown-trait
  weapons with range increments (javelins, daggers).
  (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
- `Weapon.is_melee`: now correctly returns True for thrown-melee
  weapons (daggers can be used in melee).
- `attack_ability`: fixed to distinguish pure-ranged weapons from
  thrown-melee weapons used in melee mode. A dagger used in melee
  now correctly follows finesse rules instead of always using Dex.
- Dagger fixture: `range_increment` set to 10 (matching the weapon's
  actual PF2e Range entry) instead of None.
  (AoN: https://2e.aonprd.com/Weapons.aspx?ID=358)
- Aetregan Wis: corrected from 11 to 12.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2110)
