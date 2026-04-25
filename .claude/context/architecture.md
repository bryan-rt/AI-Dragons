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

### pf2e/actions.py (added CP5.1 3a, evaluators CP5.1.3c)
- `ActionType` enum (15 types)
- `Action`, `ActionOutcome`, `ActionResult` frozen dataclasses
- 14 evaluators: `evaluate_end_turn`, `evaluate_plant_banner`, `evaluate_raise_shield`, `evaluate_step`, `evaluate_stride`, `evaluate_strike`, `evaluate_trip`, `evaluate_disarm`, `evaluate_demoralize`, `evaluate_create_a_diversion`, `evaluate_feint`, `evaluate_shield_block`, `evaluate_intercept_attack`, `evaluate_activate_tactic`
- `evaluate_action()` dispatcher (routes by ActionType)
- `_ACTION_EVALUATORS` dispatch table (EVER_READY excluded — passive feature)
- Private geometry helpers: `_grid_distance_ft`, `_is_within_weapon_reach`
- Uses TYPE_CHECKING guard for `sim/round_state` imports (duck typing at runtime)

### pf2e/damage_pipeline.py (added CP5.1.3b)
Strict PF2e damage resolution. `resolve_strike_outcome()` as the main entry. Resolution order: Intercept Attack → Shield Block → Resistance → Temp HP → Real HP.

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

### sim/round_state.py (added CP5.1.3b)
- `CombatantSnapshot` (16 fields, frozen)
- `EnemySnapshot` (14 fields, frozen)
- `RoundState` with `from_scenario`, `with_pc_update`, `with_enemy_update`. Shallow-clone branching via `dataclasses.replace()` with shared `Character`.

### sim/search.py (added CP5.1.3b, extended CP5.1.3c)
- `SearchConfig`, `TurnPlan`, `ScoreBreakdown`
- `beam_search_turn` K=50/20/10 depth 3
- `adversarial_enemy_turn` K=20/10/5
- `simulate_round`, `score_state`
- `RoundRecommendation`, `format_recommendation()` (CP5.1.3c)
- `run_simulation(scenario, seed)` — convenience entry point (CP5.1.3c)
- Action economy tracking: `_update_action_economy()` for MAP + actions_remaining

### sim/candidates.py (added CP5.1.3c)
`generate_candidates(state, actor_name)` — generates legal parameterized Actions for the beam search. PC candidates: STRIKE, TRIP, DISARM, STEP, STRIDE, RAISE_SHIELD, DEMORALIZE, CREATE_A_DIVERSION, FEINT, ACTIVATE_TACTIC, END_TURN. Enemy candidates: STRIKE, END_TURN.

### sim/cli.py + sim/__main__.py (added CP5.1.3c)
CLI entry point. `python -m sim --scenario X --seed 42 --debug-search`.

### sim/initiative.py (added CP5.1.3b)
`roll_initiative()` — seeded isolated RNG, partial override, enemy-beats-PC tiebreaker.

## Planned Modules (not yet present)

### sim/importers/pathbuilder.py (CP5.1.4 — Phase B)
JSON parser producing `Character` objects from Pathbuilder export format. Called by `sim/party.py` factories once the importer lands. Scope-bounded: same `Character` out, just JSON in.

### pf2e/effects/registry.py (Phase B+, post-CP9)
Python registry mapping `effect_kind` strings to handler functions. Engine wiring only — no data rows reference specific handlers. Replaces today's hard-coded `has_X` boolean flags once the catalog ships.

### tools/build_catalog.py (Phase B+, post-CP9)
Build-time script that reads vendored Foundry VTT pf2e JSON compendium, transforms to our schema, and writes `pf2e/data/catalog.sqlite`. Not runtime code.

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
