# Changelog

## [1.0] - Checkpoint 1: Tactic Dispatcher

### Foundation additions
- **Speed on Character and CombatantState**: Character.speed is base
  (ancestry+feats), CombatantState.current_speed is the combat-time
  override for armor penalties. effective_speed(state) returns the
  active value.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)

### Character sheet corrections
- **Aetregan Speed**: 30 ft (Elf base, not 25 as assumed).
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60)
- **Erisen Speed**: 35 ft (Elf 30 + Nimble Elf +5).
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=16)
- **Rook Speed**: Base 25 (Automaton), effective 20 with full plate.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169)
- **Dalai Speed**: 25 ft (Human base).
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=64)

### New module: pf2e/tactics.py
- TacticDefinition, TacticContext, TacticResult, EnemyState,
  SpatialQueries protocol, MockSpatialQueries
- FOLIO_TACTICS registry with all 5 of Aetregan's folio tactics:
  - Strike Hard! (https://2e.aonprd.com/Tactics.aspx?ID=13)
  - Gather to Me! (https://2e.aonprd.com/Tactics.aspx?ID=2)
  - Tactical Takedown (https://2e.aonprd.com/Tactics.aspx?ID=14)
  - Defensive Retreat (https://2e.aonprd.com/Tactics.aspx?ID=1)
  - Mountaineering Training (https://2e.aonprd.com/Tactics.aspx?ID=3)
- Dispatcher: evaluate_tactic() routes by granted_action;
  evaluate_all_prepared() returns results sorted by net_value.
- Evaluators: Strike Hard computes reaction Strike EV at MAP 0;
  Tactical Takedown computes prone probability via d20 enumeration;
  Gather to Me tracks squadmate response counts;
  Defensive Retreat and Mountaineering Training are placeholders.

### Design decisions
- Dispatch via dict of callables keyed by granted_action string.
- SpatialQueries as Protocol; MockSpatialQueries for Checkpoint 1 tests.
  Checkpoint 2 will add real grid-backed implementation.
- TacticResult includes conditions_applied and condition_probabilities
  for Checkpoint 5's turn evaluator to use.
- Tactic modifiers remain dict[str, Any].

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
