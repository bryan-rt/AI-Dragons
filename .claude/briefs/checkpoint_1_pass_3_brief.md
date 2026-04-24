# Checkpoint 1 Pass 3: Tactic Dispatcher Implementation

## Context

The Pass 2 architectural plan is approved with no remaining UNVERIFIED items. Time to write code. This brief tells you exactly what to implement, in what order, with what tests.

**Standing rules apply**: verify against AoN, cite URLs in docstrings, read existing code first, surface discrepancies, don't expand scope, test what you build.

## Pre-implementation: Read existing code

Before writing anything, read these files to understand the current foundation:

- `pf2e/character.py` — Character and CombatantState dataclasses (you'll modify these)
- `pf2e/combat_math.py` — the derivation functions you'll call from evaluators
- `pf2e/equipment.py` — weapon/shield dataclasses
- `tests/fixtures.py` — character factories you'll update
- `CHANGELOG.md` — discoveries documented so far

## Scope

### What to implement

1. **Foundation change**: Add `speed` to `Character`, `current_speed` to `CombatantState`, and `effective_speed()` helper
2. **Fixture updates**: Corrected speeds for all four party members
3. **New module**: `pf2e/tactics.py` with TacticDefinition, TacticContext, TacticResult, MockSpatialQueries, dispatcher, 5 evaluators, and the FOLIO_TACTICS registry
4. **New module**: `tests/test_tactics.py` with the test scenarios from Pass 2
5. **CHANGELOG update**: document the Speed addition and Aetregan's corrected Speed

### What NOT to implement

- No grid logic (`sim/grid.py`) — Checkpoint 2
- No scenario loader — Checkpoint 3
- No defensive value computation — Checkpoint 4
- No turn planning — Checkpoint 5
- No formatter — Checkpoint 6
- No real spatial queries — use MockSpatialQueries only

---

## Implementation Order

Work in this order to minimize churn:

### Step 1: Add Speed to Character and CombatantState

**File: `pf2e/character.py`**

Add to `Character` (frozen dataclass):

```python
# Base speed in feet, from ancestry + feats (not armor/conditions).
# (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)
speed: int = 25
```

Add to `CombatantState` (mutable):

```python
# Current speed, if modified by armor or conditions.
# None = use character.speed as-is.
current_speed: int | None = None
```

**File: `pf2e/combat_math.py`** (or a new `pf2e/movement.py` if you prefer — but combat_math.py is fine)

Add helper function:

```python
def effective_speed(state: CombatantState) -> int:
    """Current effective speed, accounting for armor and conditions.
    
    Returns state.current_speed if set, else state.character.speed.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)
    """
    if state.current_speed is not None:
        return state.current_speed
    return state.character.speed
```

### Step 2: Update fixtures with correct speeds

**File: `tests/fixtures.py`**

Per verified ancestry data (from Pass 2):

- Aetregan: `speed=30` (Elf base)
- Rook: `speed=25` (Automaton base — the full plate penalty is applied via CombatantState.current_speed=20 when relevant, NOT baked into Character)
- Dalai: `speed=25` (Human base)
- Erisen: `speed=35` (Elf 30 + Nimble Elf +5)

Update each `make_*()` factory function. Add a docstring note explaining why (especially for Erisen's +5 from Nimble Elf).

Also add a helper factory for Rook in armor:

```python
def make_rook_combat_state(anthem_active: bool = False) -> CombatantState:
    """Rook's CombatantState with full plate speed penalty applied.
    
    Base Speed 25 - full plate penalty 10 + Str 18 threshold reduction 5 = 20 ft.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169 — Str threshold reduces
    speed penalty and check penalty by 5.)
    """
    state = CombatantState.from_character(make_rook(), anthem_active=anthem_active)
    state.current_speed = 20
    return state
```

This helper gets used in the tactical takedown tests where Rook's effective speed matters.

### Step 3: Update existing tests with speed values

**File: `tests/test_combat_math.py`** — no changes needed if tests don't touch speed.

Add a small test in `test_combat_math.py` for the new `effective_speed()` function:

```python
class TestEffectiveSpeed:
    def test_default_uses_character_speed(self):
        aetregan = CombatantState.from_character(make_aetregan())
        assert effective_speed(aetregan) == 30  # Elf base
    
    def test_current_speed_override(self):
        rook = CombatantState.from_character(make_rook())
        rook.current_speed = 20  # full plate applied
        assert effective_speed(rook) == 20
    
    def test_erisen_nimble_elf(self):
        erisen = CombatantState.from_character(make_erisen())
        assert effective_speed(erisen) == 35  # 30 + Nimble Elf 5
```

**File: `tests/test_abilities.py`** — no changes.

**File: `tests/test_equipment.py`** — no changes.

**File: `tests/test_proficiency.py`** — no changes.

Run `pytest tests/ -v` at this point. All existing tests must still pass (97/97 plus the new effective_speed tests).

### Step 4: Create pf2e/tactics.py

This is the main deliverable. Structure:

```python
"""Commander tactic definitions, dispatcher, and evaluators.

The five folio tactics for Aetregan (Battlecry! Commander, level 1):
- Strike Hard! (offensive, 2 actions)
- Gather to Me! (mobility, 1 action)
- Tactical Takedown (offensive, 2 actions)
- Defensive Retreat (mobility, 2 actions — placeholder evaluator)
- Mountaineering Training (mobility, 1 action — placeholder evaluator)

Three are prepared by default; the other two are in the folio for future
re-preparation.

(AoN: https://2e.aonprd.com/Tactics.aspx)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pf2e.character import CombatantState
from pf2e.combat_math import (
    D20Outcomes, class_dc, effective_speed,
    enumerate_d20_outcomes, expected_strike_damage,
)
from pf2e.equipment import EquippedWeapon
from pf2e.types import SaveType


# --- Data types ---

@dataclass(frozen=True)
class TacticDefinition:
    """Declarative description of a Commander tactic.
    
    (Full docstring from Pass 2 Section 1.)
    """
    name: str
    aon_url: str
    action_cost: int
    traits: frozenset[str]
    range_type: str
    target_type: str
    granted_action: str
    modifiers: dict[str, Any]
    prerequisites: tuple[str, ...]


@dataclass
class EnemyState:
    """Enemy combatant with position and mutable conditions."""
    name: str
    ac: int
    saves: dict[SaveType, int]
    position: tuple[int, int]
    off_guard: bool = False
    prone: bool = False


class SpatialQueries(Protocol):
    """Abstract spatial query interface.
    
    Checkpoint 1: MockSpatialQueries with pre-computed data.
    Checkpoint 2: GridSpatialQueries backed by a real grid.
    """
    def is_in_banner_aura(self, combatant_name: str) -> bool: ...
    def enemies_reachable_by(self, combatant_name: str) -> list[str]: ...
    def is_adjacent(self, a_name: str, b_name: str) -> bool: ...
    def can_reach_with_stride(
        self, combatant_name: str, target_name: str, max_distance_ft: int,
    ) -> bool: ...
    def distance_ft(self, a_name: str, b_name: str) -> int: ...


@dataclass
class MockSpatialQueries:
    """Test double for SpatialQueries. All answers pre-computed."""
    in_aura: dict[str, bool] = field(default_factory=dict)
    reachable_enemies: dict[str, list[str]] = field(default_factory=dict)
    adjacencies: set[tuple[str, str]] = field(default_factory=set)
    distances: dict[tuple[str, str], int] = field(default_factory=dict)
    
    def is_in_banner_aura(self, name: str) -> bool:
        return self.in_aura.get(name, False)
    
    def enemies_reachable_by(self, name: str) -> list[str]:
        return self.reachable_enemies.get(name, [])
    
    def is_adjacent(self, a: str, b: str) -> bool:
        return (a, b) in self.adjacencies or (b, a) in self.adjacencies
    
    def can_reach_with_stride(self, name: str, target: str, max_ft: int) -> bool:
        dist = self.distances.get(
            (name, target),
            self.distances.get((target, name), 999),
        )
        return dist <= max_ft
    
    def distance_ft(self, a: str, b: str) -> int:
        return self.distances.get(
            (a, b), self.distances.get((b, a), 999),
        )


@dataclass
class TacticContext:
    """Everything a tactic evaluator needs."""
    commander: CombatantState
    squadmates: list[CombatantState]
    enemies: list[EnemyState]
    banner_position: tuple[int, int] | None
    banner_planted: bool
    spatial: SpatialQueries
    anthem_active: bool = True
    
    def get_squadmate(self, name: str) -> CombatantState | None:
        """Look up a squadmate's CombatantState by name."""
        for sq in self.squadmates:
            if sq.character.name == name:
                return sq
        return None
    
    def get_enemy(self, name: str) -> EnemyState | None:
        """Look up an enemy by name."""
        for e in self.enemies:
            if e.name == name:
                return e
        return None


@dataclass(frozen=True)
class TacticResult:
    """The evaluated outcome of considering a single tactic."""
    tactic_name: str
    action_cost: int
    eligible: bool
    ineligibility_reason: str = ""
    expected_damage_dealt: float = 0.0
    expected_damage_avoided: float = 0.0
    best_target_ally: str = ""
    best_target_enemy: str = ""
    justification: str = ""
    conditions_applied: dict[str, list[str]] = field(default_factory=dict)
    condition_probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    squadmates_responding: int = 0
    
    @property
    def net_value(self) -> float:
        return self.expected_damage_dealt + self.expected_damage_avoided


# --- Registry ---

STRIKE_HARD = TacticDefinition(...)  # exact fields from Pass 2
GATHER_TO_ME = TacticDefinition(...)
TACTICAL_TAKEDOWN = TacticDefinition(...)
DEFENSIVE_RETREAT = TacticDefinition(...)
MOUNTAINEERING_TRAINING = TacticDefinition(...)

FOLIO_TACTICS: dict[str, TacticDefinition] = {
    "strike_hard": STRIKE_HARD,
    "gather_to_me": GATHER_TO_ME,
    "tactical_takedown": TACTICAL_TAKEDOWN,
    "defensive_retreat": DEFENSIVE_RETREAT,
    "mountaineering_training": MOUNTAINEERING_TRAINING,
}

PREPARED_TACTICS: tuple[str, ...] = (
    "strike_hard",
    "gather_to_me",
    "tactical_takedown",
)


# --- Evaluators ---

def _evaluate_reaction_strike(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Strike Hard! — ally makes a reaction Strike at MAP 0."""
    # Implementation per Pass 1 Section 6.1, with Pass 2 corrections.
    ...

def _evaluate_reaction_stride(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Gather to Me! — all squadmates Stride toward banner aura.
    
    Implementation per Pass 2 Updated Section 4 (with response tracking).
    """
    ...

def _evaluate_stride_half(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Tactical Takedown — two allies half-Stride, enemy Reflex save or prone."""
    # Implementation per Pass 2 Updated Section 5 (condition_probabilities, 55%).
    ...

def _evaluate_free_step(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Defensive Retreat — placeholder (Checkpoint 4 defensive value pending)."""
    ...

def _evaluate_passive_buff(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Mountaineering Training — placeholder (situational buff)."""
    ...


# --- Dispatcher ---

_EVALUATORS: dict[str, Callable[[TacticDefinition, TacticContext], TacticResult]] = {
    "reaction_strike": _evaluate_reaction_strike,
    "reaction_stride": _evaluate_reaction_stride,
    "stride_half_speed": _evaluate_stride_half,
    "free_step": _evaluate_free_step,
    "passive_buff": _evaluate_passive_buff,
}


def evaluate_tactic(
    definition: TacticDefinition,
    context: TacticContext,
) -> TacticResult:
    """Evaluate a single tactic. Routes by granted_action."""
    evaluator = _EVALUATORS.get(definition.granted_action)
    if evaluator is None:
        return TacticResult(
            tactic_name=definition.name,
            action_cost=definition.action_cost,
            eligible=False,
            ineligibility_reason=(
                f"No evaluator for granted_action={definition.granted_action!r}"
            ),
        )
    return evaluator(definition, context)


def evaluate_all_prepared(
    prepared: list[TacticDefinition],
    context: TacticContext,
) -> list[TacticResult]:
    """Evaluate all prepared tactics, return sorted by net_value descending."""
    results = [evaluate_tactic(t, context) for t in prepared]
    return sorted(results, key=lambda r: r.net_value, reverse=True)
```

### Step 5: Implement each evaluator

Use the Pass 2 plan as your reference, but here are specific implementation notes:

**`_evaluate_reaction_strike` (Strike Hard!):**

For each squadmate in `ctx.squadmates`:
1. Skip if not `ctx.spatial.is_in_banner_aura(sq.character.name)`
2. Skip if `sq.reactions_available == 0 and not sq.drilled_reaction_available`
3. Get reachable enemies: `ctx.spatial.enemies_reachable_by(sq.character.name)`
4. For each reachable enemy, for each equipped weapon the squadmate has:
   - Get the EnemyState: `ctx.get_enemy(enemy_name)`
   - Compute EV: `expected_strike_damage(sq, weapon, enemy.ac, is_reaction=True, off_guard=enemy.off_guard)`
   - Track best (ally, weapon, enemy, EV) tuple

If no valid combination found → ineligible with reason.

Otherwise return TacticResult with:
- `expected_damage_dealt = best_ev`
- `best_target_ally = best_ally_name`
- `best_target_enemy = best_enemy_name`
- `justification = f"Strike Hard! → {ally} {weapon} reaction Strike at +{bonus} (MAP 0) vs {enemy} AC {ac}, EV {ev:.2f}"`
- `squadmates_responding = 1`

**`_evaluate_reaction_stride` (Gather to Me!):**

Per Pass 2 Section 4. Count `will_respond` and `cannot_respond`, build justification string. Always eligible (even if 0 respond — note this in justification).

**`_evaluate_stride_half` (Tactical Takedown!):**

1. Get all squadmates in aura with reactions available (or drilled reaction): call this the "eligible pool"
2. If len(eligible_pool) < 2 → ineligible
3. For each pair (ally1, ally2) from eligible_pool:
   - For each enemy in ctx.enemies:
     - Check if ally1 can reach enemy with half effective_speed(ally1) AND ally2 can reach enemy with half effective_speed(ally2)
     - `ctx.spatial.can_reach_with_stride(ally_name, enemy.name, effective_speed(ally_state) // 2)` — note integer division for half-Speed
   - If both can reach, this is a valid (pair, enemy) combination
4. Among valid combinations, pick the best target. "Best" = lowest Reflex save (most likely to fall prone). If multiple enemies have the same save, pick arbitrarily (document this choice).
5. If no valid combination → ineligible with reason "no enemy reachable by 2 squadmates with half-Speed Stride"
6. Otherwise: compute prone probability via `enumerate_d20_outcomes(save_mod, class_dc)`, return TacticResult with condition_probabilities populated

**`_evaluate_free_step` (Defensive Retreat!):**

Placeholder per Pass 1 Section 6.4. Returns eligible if `any(sq.character.name for sq in squadmates if ctx.spatial.is_in_banner_aura(sq.character.name))`, with zero EV and justification noting "Defensive value pending Checkpoint 4."

**`_evaluate_passive_buff` (Mountaineering Training!):**

Placeholder per Pass 1 Section 6.5. Always eligible, zero EV, justification notes "No vertical terrain in scenario; no value computed."

### Step 6: Create tests/test_tactics.py

Mirror the Pass 1 Section 7 test scenarios with the Pass 2 enhancements. Structure:

```python
"""Tests for tactic representation and dispatcher."""

import pytest

from pf2e.character import CombatantState
from pf2e.tactics import (
    DEFENSIVE_RETREAT, GATHER_TO_ME, MOUNTAINEERING_TRAINING,
    STRIKE_HARD, TACTICAL_TAKEDOWN,
    EnemyState, MockSpatialQueries, TacticContext,
    evaluate_all_prepared, evaluate_tactic,
)
from pf2e.types import SaveType
from tests.fixtures import (
    make_aetregan, make_dalai, make_erisen, make_rook,
    make_rook_combat_state,
)


# --- Fixtures ---

@pytest.fixture
def bandit1() -> EnemyState:
    return EnemyState(
        name="Bandit1",
        ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=(3, 5),
    )


@pytest.fixture
def base_context(bandit1):
    """A default context with all four party members and one bandit."""
    aetregan = CombatantState.from_character(make_aetregan())
    rook = make_rook_combat_state()
    dalai = CombatantState.from_character(make_dalai())
    erisen = CombatantState.from_character(make_erisen())
    
    return TacticContext(
        commander=aetregan,
        squadmates=[rook, dalai, erisen],
        enemies=[bandit1],
        banner_position=(3, 3),
        banner_planted=True,
        spatial=MockSpatialQueries(),
        anthem_active=True,
    )


# --- Strike Hard tests ---

class TestStrikeHard:
    def test_eligible_rook_strikes_bandit(self, base_context, bandit1):
        """Rook in aura + Bandit in reach → EV ~6.80 (reaction, MAP 0).
        
        Anthem is active in base_context, so Rook gets +1 attack/damage.
        With Anthem: EV should be higher than 6.80. Compute expected.
        """
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            reachable_enemies={"Rook": ["Bandit1"], "Dalai Alpaca": []},
            adjacencies={("Rook", "Bandit1")},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Rook"
        assert result.best_target_enemy == "Bandit1"
        # Without Anthem: 6.80. With Anthem (+1/+1): higher. Verify actual value.
        assert result.expected_damage_dealt > 6.80
    
    def test_ineligible_no_squadmate_in_aura(self, base_context):
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": False, "Dalai Alpaca": False, "Erisen": False},
            reachable_enemies={"Rook": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert not result.eligible
        assert "aura" in result.ineligibility_reason.lower()
    
    def test_ineligible_no_reachable_enemy(self, base_context):
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
            reachable_enemies={"Rook": []},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert not result.eligible
    
    def test_picks_best_ally(self, base_context):
        """Both Rook and Dalai in aura with reachable enemy. Rook's EV wins."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={"Rook": ["Bandit1"], "Dalai Alpaca": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.best_target_ally == "Rook"
    
    def test_skips_ally_without_reactions(self, base_context):
        """Rook has no reactions left; only Dalai responds."""
        base_context.squadmates[0].reactions_available = 0
        base_context.squadmates[0].drilled_reaction_available = False
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={"Rook": ["Bandit1"], "Dalai Alpaca": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Dalai Alpaca"
    
    def test_drilled_reaction_allows_depleted_ally(self, base_context):
        """Rook has 0 reactions but drilled_reaction_available=True. Rook still responds."""
        base_context.squadmates[0].reactions_available = 0
        base_context.squadmates[0].drilled_reaction_available = True
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
            reachable_enemies={"Rook": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Rook"


class TestGatherToMe:
    def test_always_eligible(self, base_context):
        base_context.spatial = MockSpatialQueries()  # empty
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0
        assert "pending" in result.justification.lower()
    
    def test_response_count(self, base_context):
        """All 3 squadmates have reactions → 3 of 3."""
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.squadmates_responding == 3
        assert "3 of 3" in result.justification
    
    def test_partial_response(self, base_context):
        """Erisen used his reaction. 2 of 3 can respond."""
        base_context.squadmates[2].reactions_available = 0
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.squadmates_responding == 2
        assert "2 of 3" in result.justification
        assert "Erisen" in result.justification


class TestTacticalTakedown:
    def test_eligible_with_two_allies(self, base_context, bandit1):
        """Rook and Dalai both in aura, both can reach bandit with half-Speed."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            distances={
                ("Rook", "Bandit1"): 10,       # Rook Speed 20, half=10 ✓
                ("Dalai Alpaca", "Bandit1"): 10,  # Dalai Speed 25, half=12 ✓
            },
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert result.eligible
        # Reflex +5 vs DC 17: 55% prone chance
        assert result.condition_probabilities == {"Bandit1": {"prone": pytest.approx(0.55, abs=0.01)}}
        assert result.conditions_applied == {"Bandit1": ["prone"]}
    
    def test_ineligible_one_ally_in_aura(self, base_context):
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": False, "Erisen": False},
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert not result.eligible
    
    def test_ineligible_no_shared_reachable_enemy(self, base_context):
        """Both in aura but neither can reach the bandit with half-Speed."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            distances={
                ("Rook", "Bandit1"): 50,      # too far
                ("Dalai Alpaca", "Bandit1"): 50,
            },
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert not result.eligible


class TestDefensiveRetreat:
    def test_eligible_squadmate_in_aura(self, base_context):
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
        )
        result = evaluate_tactic(DEFENSIVE_RETREAT, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0
        assert "pending" in result.justification.lower()


class TestMountaineeringTraining:
    def test_always_eligible_but_zero_ev(self, base_context):
        result = evaluate_tactic(MOUNTAINEERING_TRAINING, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0
        assert "vertical terrain" in result.justification.lower() or "situational" in result.justification.lower()


class TestEvaluateAllPrepared:
    def test_sorts_by_net_value(self, base_context):
        """Run all 3 prepared tactics, verify sorted."""
        prepared_defs = [STRIKE_HARD, GATHER_TO_ME, TACTICAL_TAKEDOWN]
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={"Rook": ["Bandit1"]},
            distances={
                ("Rook", "Bandit1"): 10,
                ("Dalai Alpaca", "Bandit1"): 10,
            },
            adjacencies={("Rook", "Bandit1")},
        )
        results = evaluate_all_prepared(prepared_defs, base_context)
        assert len(results) == 3
        # Strike Hard should win in this setup (has damage EV; others are 0 or prone-setup)
        assert results[0].tactic_name == "Strike Hard!"
```

Note on the Anthem-active numbers: the base_context fixture sets `anthem_active=True`, so Rook gets +1 status to attack and damage. That means the Strike Hard EV for Rook longsword vs Bandit AC 15 won't be 6.80 — it'll be higher. Verify the actual computed value with a small hand-calculation and set the test expectation accordingly. Use `pytest.approx` with 0.01 tolerance.

### Step 7: Update CHANGELOG.md

Append a new section:

```markdown
## [1.0] - Checkpoint 1: Tactic Dispatcher

### Foundation additions
- **Speed on Character and CombatantState**: Character.speed is base (ancestry+feats),
  CombatantState.current_speed is the combat-time override for armor penalties and
  conditions. effective_speed(state) returns the currently active value.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)

### Character sheet corrections
- **Aetregan Speed**: Corrected from assumed 25 to 30. Aetregan is an Elf
  (30 ft base Speed). Earlier scenario assumptions of 25 ft were wrong.
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60)
- **Erisen Speed**: 35 ft (Elf 30 + Nimble Elf +5).
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=16)
- **Rook Speed**: Base 25 (Automaton), effective 20 with full plate (−10 penalty,
  Str 18 threshold reduces by 5).
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169)
- **Dalai Speed**: 25 ft (Human base).
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)

### New module: pf2e/tactics.py
- TacticDefinition, TacticContext, TacticResult, EnemyState, SpatialQueries protocol, MockSpatialQueries
- FOLIO_TACTICS registry with all 5 of Aetregan's folio tactics
- PREPARED_TACTICS tuple listing the 3 currently prepared
- Per-tactic evaluators: Strike Hard! and Tactical Takedown are fully functional;
  Gather to Me! tracks response counts; Defensive Retreat and Mountaineering Training
  are placeholders returning eligible-with-zero-EV.
- Dispatcher `evaluate_tactic()` routes by granted_action;
  `evaluate_all_prepared()` returns sorted results.

### Verified AoN citations
- Defensive Retreat: https://2e.aonprd.com/Tactics.aspx?ID=1
- Mountaineering Training: https://2e.aonprd.com/Tactics.aspx?ID=3
- Prone condition: https://2e.aonprd.com/Conditions.aspx?ID=88

### Design decisions
- Tactic modifiers remain `dict[str, Any]` — typed variants deferred until vocabulary stabilizes.
- Spatial queries as Protocol with MockSpatialQueries for Checkpoint 1 tests.
  Checkpoint 2 will add GridSpatialQueries backed by a real grid.
- Conditions on enemies tracked via TacticResult.conditions_applied and
  condition_probabilities for downstream use in Checkpoint 5's turn evaluator.
```

---

## Validation Checklist

- [ ] All existing tests still pass after Speed field additions (97/97 originally)
- [ ] `effective_speed()` helper tests pass (3 new cases)
- [ ] All tactic evaluator tests pass (roughly 14-16 new cases)
- [ ] Strike Hard returns correct EV (account for Anthem +1/+1 active)
- [ ] Tactical Takedown produces exactly 55% prone probability for Reflex +5 vs DC 17
- [ ] Gather to Me correctly counts responding squadmates
- [ ] `pytest tests/ -v` shows 100% pass
- [ ] CHANGELOG updated with Checkpoint 1 entry
- [ ] All new docstrings cite AoN URLs
- [ ] No files created outside `pf2e/tactics.py` and `tests/test_tactics.py` (other than CHANGELOG update)
- [ ] No implementation of sim/, grid logic, scenario loader, or turn planner

## Common pitfalls

**Anthem bonus stacking.** base_context has anthem_active=True. This sets CombatantState.status_bonus_attack=1 and status_bonus_damage=1. Every Strike EV in tests must account for this. If you expected 6.80 from earlier docs, the actual test value with Anthem will be higher. Compute it fresh using enumerate_d20_outcomes.

**Half-speed rounding.** PF2e rounds fractions down by default. `effective_speed() // 2` gives 12 for Speed 25 (not 13). Verify this is Python's intended behavior (integer division). 

**Dalai's speed.** Dalai is Human, Speed 25. Half-Speed = 12. If your Tactical Takedown test sets her distance to 15 ft from an enemy, she CANNOT reach (12 < 15). Confirm distances in tests are consistent with half-Speed limits.

**Drilled reactions.** The foundation has a `drilled_reaction_available: bool` on CombatantState. For Checkpoint 1, tests can just set this manually on squadmate states to simulate the Commander granting the drilled reaction. The optimization of which ally to grant it to is Checkpoint 5's job.

## What Comes After

1. You implement everything above.
2. You run `pytest tests/ -v` and confirm 100% pass.
3. You push the repo.
4. I review via the connector.
5. We move to Checkpoint 2: Grid and Spatial Reasoning.
