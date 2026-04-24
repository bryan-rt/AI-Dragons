# Architecture (CLI Agent Reference)

## Two-Package Structure

Strict unidirectional dependency:

```
sim/     (simulator layer)
  ↓ imports from
pf2e/    (pure rules engine)
```

**Rule: `pf2e/` never imports from `sim/`.** Enforced by convention, not by tooling. If you find yourself needing to import `sim/` from `pf2e/`, stop and reconsider — the thing you need probably belongs in `pf2e/` already, or the abstraction is in the wrong layer.

Tests import from both freely.

## Module Responsibilities

### pf2e/types.py
Core enums and type aliases. Zero dependencies on other `pf2e/` modules.

Current contents:
- `Ability`, `ProficiencyRank`, `WeaponCategory`, `WeaponGroup`, `DamageType`, `SaveType`
- `Skill` (added CP5.1 3a), `SKILL_ABILITY` lookup

### pf2e/abilities.py
`AbilityScores` dataclass.

### pf2e/proficiency.py
`proficiency_bonus(rank, level)` function.

### pf2e/equipment.py
Equipment data classes. All frozen.
- `Weapon`, `WeaponRunes`, `EquippedWeapon`
- `ArmorData`
- `Shield`

### pf2e/character.py
- `Character` — frozen, build data
- `CombatantState` — mutable, per-round state
- `EnemyState` — mutable, enemy data

### pf2e/combat_math.py
The core rules engine. All derivation functions live here.

Key functions:
- `enumerate_d20_outcomes(bonus, dc)` — returns `D20Outcomes(crit_success, success, failure, critical_failure)`
- `attack_bonus`, `damage_avg`, `expected_strike_damage`
- `armor_class`, `class_dc`, `save_bonus`, `perception_bonus`
- `skill_bonus`, `lore_bonus` (added CP5.1 3a)
- `map_penalty`, `die_average`, `melee_reach_ft`, `effective_speed`, `max_hp`
- Defensive: `plant_banner_temp_hp`, `guardians_armor_resistance`, `temp_hp_ev`, `expected_incoming_damage`, `expected_enemy_turn_damage`
- Siege: `SiegeWeapon`, `EnemyTarget`, `expected_aoe_damage`, `siege_save_dc`

### pf2e/tactics.py
Tactic system.
- Data types: `TacticDefinition`, `TacticContext`, `TacticResult`, `SpatialQueries` Protocol, `MockSpatialQueries`
- Tactic constants: `STRIKE_HARD`, `GATHER_TO_ME`, `TACTICAL_TAKEDOWN`, `DEFENSIVE_RETREAT`, `MOUNTAINEERING_TRAINING`, `SHIELDS_UP`
- Registry: `FOLIO_TACTICS` (dict), `PREPARED_TACTICS` (tuple)
- Dispatcher: `evaluate_tactic`, `evaluate_all_prepared`
- Evaluators: `_evaluate_reaction_strike`, `_evaluate_reaction_stride`, `_evaluate_stride_half`, `_evaluate_free_step`, `_evaluate_passive_buff`, `_evaluate_reaction_raise_shield` (stub)
- Standalone: `intercept_attack_ev`

### pf2e/actions.py (added CP5.1 3a)
- `ActionType` enum (15 types)
- `Action` frozen dataclass
- `ActionOutcome` frozen dataclass
- `ActionResult` frozen dataclass with `expected_damage_dealt` property, `verify_probability_sum()` method
- Pass 3c will add `_ACTION_EVALUATORS` dispatch table and `evaluate_action()` function

### pf2e/damage_pipeline.py (will be added CP5.1 3b)
Strict PF2e damage resolution. `resolve_strike()` as the main entry.

### sim/grid.py
Pure grid geometry, no pf2e dependencies.
- `Pos = tuple[int, int]`
- `GridState` dataclass
- `distance_ft`, `chebyshev_squares`, `is_adjacent`, `is_within_reach`
- `squares_in_emanation`
- `shortest_movement_cost` (BFS)
- `parse_map`, `render_map`

### sim/grid_spatial.py
`GridSpatialQueries` class implementing the `SpatialQueries` Protocol.

### sim/party.py
Character factories, weapon/armor constants, token-to-factory mapping.

### sim/scenario.py
Scenario file loading, parsing, `Scenario` dataclass.

### sim/round_state.py (will be added CP5.1 3b)
`RoundState` with shallow-clone and hybrid branching semantics.

### sim/search.py (will be added CP5.1 3b)
`SearchConfig`, `beam_search_turn`, `adversarial_enemy_turn`, `simulate_round`.

### sim/initiative.py (will be added CP5.1 3b)
`roll_initiative()` — seeded Perception + d20 roll.

## Layering Violations to Watch For

**Forbidden:**
- `pf2e/*` importing from `sim/*` — ever
- Characters knowing about grids — positions live on `CombatantState`, not `Character`
- Combat math functions receiving character names — they take `Character` or `CombatantState`, not `str`
- `tests/fixtures.py` growing new logic — it's a shim for backward compat

**Permitted:**
- `sim/*` importing from `pf2e/*` — the whole point
- Tests importing from both
- `pf2e/types.py` being imported everywhere (it has no dependencies)

## Module Addition Checklist

When a brief says "create new module X":

1. Add `pf2e/X.py` or `sim/X.py` with module docstring at top
2. Create corresponding test file `tests/test_X.py`
3. Add to `CHANGELOG.md`'s checkpoint section
4. If it exposes public types, consider re-exporting from `pf2e/__init__.py` or `sim/__init__.py`
5. Update this file (`.claude/context/architecture.md`) with the module's role

## Import Patterns

For `pf2e/` modules:
```python
from __future__ import annotations

from dataclasses import dataclass, field
# ... other stdlib

from pf2e.types import Ability, ProficiencyRank, Skill
from pf2e.abilities import AbilityScores
# ... other pf2e/
```

For `sim/` modules:
```python
from __future__ import annotations

from dataclasses import dataclass, field
# ... other stdlib

from pf2e.character import CombatantState, EnemyState
from pf2e.combat_math import armor_class
# ... other pf2e/

from sim.grid import GridState
# ... other sim/
```

For tests:
```python
import pytest

from pf2e.combat_math import armor_class
from pf2e.tactics import STRIKE_HARD, evaluate_tactic
from sim.scenario import load_scenario
from tests.fixtures import make_aetregan, make_rook
```
