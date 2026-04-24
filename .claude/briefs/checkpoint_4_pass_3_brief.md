# Checkpoint 4 Pass 3: Defensive Value Computation — Implementation

## Context

Pass 2 is approved with one judgment call: make `banner_planted` a required parameter on `GridSpatialQueries` (no default). Time to write code.

**Standing rules apply**: verify against AoN, cite URLs in docstrings, read existing code first, surface discrepancies, don't expand scope, test what you build.

## One Change from Pass 2 Review

`GridSpatialQueries.__init__` takes `banner_planted: bool` as a **required** parameter (no default). This forces existing test callers to explicitly declare banner state, which is the correct defensive choice given the aura behavior difference. Existing tests in `tests/test_grid_spatial.py` that directly construct `GridSpatialQueries` will need updates to pass `banner_planted=True` or `banner_planted=False`.

The tests that construct through `Scenario.build_tactic_context()` are fine — the threading from `TacticContext.banner_planted` happens automatically.

## Pre-implementation: Read existing code

Before writing anything:

- `pf2e/character.py` — confirm `CombatantState.guardian_reactions_available` exists (Pass 2 verified at line 71). Confirm `armor_class()` helper in `combat_math.py`.
- `pf2e/combat_math.py` — confirm `map_penalty(attack_number, agile)` exists at line 273. See the existing `expected_strike_damage` for the MAP pattern.
- `pf2e/equipment.py` — confirm `ArmorData.ac_bonus` field (used for Guardian's Armor eligibility check).
- `pf2e/tactics.py` — `TacticResult` dataclass, `_evaluate_reaction_stride`, `_evaluate_free_step`.
- `sim/grid_spatial.py` — `GridSpatialQueries.__init__`, `is_in_banner_aura`.
- `sim/scenario.py` — `_build_enemy`, `Scenario.build_tactic_context`.
- `tests/test_grid_spatial.py` — every call site for `GridSpatialQueries(...)` direct constructor. These all need updates for the new required parameter.

## Scope

### What to implement

1. Foundation: `banner_planted` required parameter on `GridSpatialQueries`, threading through `Scenario.build_tactic_context()`, regression test for 40-ft planted aura.
2. `EnemyState` offensive field extensions.
3. Scenario parser updates for enemy offensive stats.
4. Core math helpers in `pf2e/combat_math.py`: `plant_banner_temp_hp`, `guardians_armor_resistance`, `_has_guardians_armor`, `expected_incoming_damage`, `expected_enemy_turn_damage`, `temp_hp_ev`.
5. `TacticResult.damage_prevented_sources` field with canonical key vocabulary.
6. `intercept_attack_ev()` function in `pf2e/tactics.py` (standalone helper, not yet wired into any evaluator — Checkpoint 5 will call it).
7. Update `_evaluate_reaction_stride` (Gather to Me) to compute defensive EV.
8. Update `_evaluate_free_step` (Defensive Retreat) to compute defensive EV.
9. Update `scenarios/checkpoint_1_strike_hard.scenario` with enemy offensive stats.
10. Integration tests.
11. CHANGELOG.

### What NOT to implement

- No Shield Block, Raise Shield, or Taunt modeling (Checkpoint 5 action economy)
- No Plant Banner as an evaluatable action (it's a feat, not a tactic; Checkpoint 5 handles turn-level action choice)
- No carried-banner-follows-commander dynamics
- No AoE friendly-fire (Checkpoint 5)
- No sophisticated Intercept Attack target selection — simple "lowest-AC ally within 10 ft"
- No multi-round combat simulation — per-tactic defensive EV only

---

## Implementation Order

### Step 1: Foundation update — `banner_planted` parameter

#### Step 1a: Update `GridSpatialQueries`

In `sim/grid_spatial.py`:

```python
class GridSpatialQueries:
    def __init__(
        self,
        grid_state: GridState,
        commander: CombatantState,
        squadmates: list[CombatantState],
        enemies: list[EnemyState],
        banner_position: Pos | None,
        banner_planted: bool,  # REQUIRED — no default
    ) -> None:
        ...
        self._banner_planted = banner_planted
    
    def is_in_banner_aura(self, name: str) -> bool:
        """True if combatant is within the banner aura.
        
        Base aura: 30-ft emanation. When the banner is planted, the aura
        expands to a 40-ft burst.
        (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
        (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
        """
        if self._banner_pos is None:
            return False
        pos = self._positions.get(name)
        if pos is None:
            return False
        radius = 40 if self._banner_planted else 30
        return grid.distance_ft(pos, self._banner_pos) <= radius
    
    @classmethod
    def from_context(
        cls, grid_state: GridState, ctx: TacticContext,
    ) -> GridSpatialQueries:
        return cls(
            grid_state,
            ctx.commander,
            ctx.squadmates,
            ctx.enemies,
            ctx.banner_position,
            banner_planted=ctx.banner_planted,
        )
```

#### Step 1b: Update `Scenario.build_tactic_context()`

In `sim/scenario.py`:

```python
def build_tactic_context(self) -> TacticContext:
    spatial = GridSpatialQueries(
        grid_state=self.grid,
        commander=self.commander,
        squadmates=list(self.squadmates),
        enemies=list(self.enemies),
        banner_position=self.banner_position,
        banner_planted=self.banner_planted,  # NEW
    )
    return TacticContext(
        commander=self.commander,
        squadmates=list(self.squadmates),
        enemies=list(self.enemies),
        banner_position=self.banner_position,
        banner_planted=self.banner_planted,
        spatial=spatial,
        anthem_active=self.anthem_active,
    )
```

#### Step 1c: Update existing tests in `test_grid_spatial.py`

Every direct `GridSpatialQueries(...)` call needs `banner_planted=True` or `banner_planted=False` added. For tests where the banner is in play (e.g., the killer swap test), use `True` (matching what the original Strike Hard scenario implies). For tests with `banner_position=None`, use `False`.

Run `pytest tests/ -v`. All 181 existing tests must still pass after Step 1 is complete. Stop and fix any failures before proceeding.

#### Step 1d: Add the 40-ft aura regression test

To `tests/test_grid_spatial.py`:

```python
class TestPlantedBannerAuraExpansion:
    """Regression test for Checkpoint 4 C.1 — planted banner 40-ft burst.
    
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
    """
    
    def test_ally_at_35ft_diagonal_in_planted_aura(self):
        """5 diagonal squares = 5+10+5+10+5 = 35 ft.
        
        Under 30-ft emanation: OUT. Under 40-ft burst (planted): IN.
        """
        grid = GridState(rows=10, cols=10, walls=set())
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally = make_rook_combat_state()
        ally.position = (5, 5)  # 5 diagonal from banner
        
        # With banner planted (40-ft burst): IN aura
        spatial_planted = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[ally],
            enemies=[],
            banner_position=(0, 0),
            banner_planted=True,
        )
        assert spatial_planted.is_in_banner_aura("Rook") is True
        
        # With banner carried (30-ft emanation): OUT of aura
        spatial_carried = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[ally],
            enemies=[],
            banner_position=(0, 0),
            banner_planted=False,
        )
        assert spatial_carried.is_in_banner_aura("Rook") is False
```

### Step 2: Extend `EnemyState` with offensive stats

In `pf2e/character.py`:

```python
@dataclass
class EnemyState:
    name: str
    ac: int
    saves: dict[SaveType, int]
    position: tuple[int, int]
    off_guard: bool = False
    prone: bool = False
    # Offensive stats for defensive EV computation (Checkpoint 4)
    attack_bonus: int = 0
    damage_dice: str = ""          # e.g., "1d8"; empty = no modeled offense
    damage_bonus: int = 0
    num_attacks_per_turn: int = 2
```

All new fields have defaults. Existing scenarios without enemy offensive stats produce 0 defensive EV (empty `damage_dice` short-circuits the computation).

### Step 3: Update scenario parser

In `sim/scenario.py`, `_build_enemy()`:

```python
def _build_enemy(token: str, spec: dict[str, str], pos: Pos) -> EnemyState:
    required = ("name", "ac", "ref", "fort", "will")
    missing = [k for k in required if k not in spec]
    if missing:
        raise ScenarioParseError(
            f"Enemy '{token}' missing required fields: {missing}"
        )
    try:
        return EnemyState(
            name=spec["name"],
            ac=int(spec["ac"]),
            saves={
                SaveType.REFLEX: int(spec["ref"]),
                SaveType.FORTITUDE: int(spec["fort"]),
                SaveType.WILL: int(spec["will"]),
            },
            position=pos,
            off_guard=spec.get("off_guard", "false").lower() == "true",
            prone=spec.get("prone", "false").lower() == "true",
            # NEW offensive fields (all optional)
            attack_bonus=int(spec.get("atk", "0")),
            damage_dice=spec.get("dmg", ""),
            damage_bonus=int(spec.get("dmg_bonus", "0")),
            num_attacks_per_turn=int(spec.get("attacks", "2")),
        )
    except ValueError as e:
        raise ScenarioParseError(
            f"Enemy '{token}': invalid integer in stats: {e}"
        ) from e
```

Enemy line format in scenario files:
```
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2
```

All offensive fields optional. Document in the file-format section of `sim/scenario.py`'s module docstring.

### Step 4: Core math helpers in `pf2e/combat_math.py`

```python
def plant_banner_temp_hp(level: int) -> int:
    """Temp HP granted by Plant Banner feat per ally per round.
    
    4 at level 1, +4 at level 4 and every 4 levels thereafter.
    Temp HP renews each turn an ally starts within the burst.
    
    Note: PF2e temp HP doesn't stack — allies take the highest active
    source. For Checkpoint 4, Plant Banner is assumed to be the only
    active temp HP source.
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2321 — temp HP rules)
    """
    return 4 * (1 + level // 4)


def guardians_armor_resistance(level: int) -> int:
    """Physical damage resistance from Guardian's Armor class feature.
    
    Resistance = 1 + (level // 2). Applies while wearing medium/heavy
    armor.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
    """
    return 1 + level // 2


def _has_guardians_armor(character: Character) -> bool:
    """True if character has active Guardian's Armor.
    
    Uses guardian_reactions > 0 as a Guardian-class proxy (they get the
    Ever Ready reaction at level 1). A proper class_name field would be
    cleaner but is scope creep.
    Requires medium or heavy armor (ac_bonus >= 4).
    """
    if character.guardian_reactions == 0:
        return False
    if character.armor is None:
        return False
    return character.armor.ac_bonus >= 4


def expected_incoming_damage(
    attacker: EnemyState,
    target: CombatantState,
    attack_number: int = 1,
) -> float:
    """Expected damage from one enemy Strike against a specific target.
    
    Accounts for:
    - Target's effective AC (raised shield, off-guard, frightened)
      via armor_class()
    - Attacker's MAP for the given attack number
    - Guardian's Armor resistance if the target qualifies
    
    Returns 0.0 if attacker has no modeled damage.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2187 — attack rolls)
    """
    if not attacker.damage_dice:
        return 0.0
    ac = armor_class(target)
    effective_bonus = attacker.attack_bonus + map_penalty(attack_number, agile=False)
    outcomes = enumerate_d20_outcomes(effective_bonus, ac)
    hit_dmg = die_average(attacker.damage_dice) + attacker.damage_bonus
    crit_dmg = hit_dmg * 2
    raw_ev = (
        (outcomes.success / 20) * hit_dmg
        + (outcomes.critical_success / 20) * crit_dmg
    )
    # Apply Guardian's Armor resistance (per-hit, approximated as
    # resistance × hit_probability reduction in EV)
    if _has_guardians_armor(target.character):
        resistance = guardians_armor_resistance(target.character.level)
        hit_prob = (outcomes.success + outcomes.critical_success) / 20
        raw_ev -= resistance * hit_prob
        raw_ev = max(0.0, raw_ev)
    return raw_ev


def expected_enemy_turn_damage(
    attacker: EnemyState,
    target: CombatantState,
) -> float:
    """Total expected damage across an enemy's full turn of Strikes.
    
    Sums expected damage across num_attacks_per_turn Strikes with
    escalating MAP.
    """
    total = 0.0
    for i in range(1, attacker.num_attacks_per_turn + 1):
        total += expected_incoming_damage(attacker, target, i)
    return total


def temp_hp_ev(temp_hp: int, expected_damage: float) -> float:
    """EV of temp HP given expected incoming damage.
    
    Temp HP absorbs min(temp_hp, expected_damage). Correct as an EV
    approximation: if expected damage exceeds temp HP, all temp HP is
    consumed; otherwise only the incoming damage is absorbed.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2321)
    """
    return float(min(float(temp_hp), expected_damage))
```

### Step 5: Add `damage_prevented_sources` to TacticResult

In `pf2e/tactics.py`:

```python
@dataclass(frozen=True)
class TacticResult:
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
    # NEW: canonical breakdown of defensive EV sources.
    # Canonical keys:
    #   "plant_banner_temp_hp"       — allies gaining temp HP in banner burst
    #   "guardians_armor_resistance" — Rook's passive physical resistance
    #   "intercept_attack"           — Rook redirecting damage from ally
    #   "gather_reposition"          — allies Striding out of enemy reach
    #   "retreat_steps"              — allies Stepping out of enemy reach
    damage_prevented_sources: dict[str, float] = field(default_factory=dict)
    
    @property
    def net_value(self) -> float:
        return self.expected_damage_dealt + self.expected_damage_avoided
```

### Step 6: Add `intercept_attack_ev()` to `pf2e/tactics.py`

Standalone helper that Checkpoint 5's turn evaluator will call. Not wired into any tactic evaluator (Intercept Attack isn't a tactic).

```python
def intercept_attack_ev(
    rook: CombatantState,
    ally: CombatantState,
    enemies: list[EnemyState],
    spatial: SpatialQueries,
) -> float:
    """EV of Rook using Intercept Attack to protect a specific ally.
    
    Checks eligibility:
    1. Rook has a guardian reaction available
    2. Ally is within 10 ft of Rook
    3. Rook can Step (5 ft) to end adjacent to ally
    4. At least one enemy has modeled offensive capability
    
    Returns the resistance savings (Guardian's Armor) for one intercepted
    hit. At level 1: 1.0.
    
    SIMPLIFICATION: Assumes Rook intercepts exactly once per round. A more
    accurate model would weight by P(hit occurs) across the enemy turn;
    flag as future work for Checkpoint 5.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=67 — Guardian's Armor)
    """
    # Reaction available?
    if rook.guardian_reactions_available <= 0:
        return 0.0
    # Within 10 ft?
    rook_pos = rook.position
    ally_pos = ally.position
    from sim.grid import distance_ft as _distance_ft
    if _distance_ft(rook_pos, ally_pos) > 10:
        return 0.0
    # Can Step (5 ft) to adjacent?
    if not spatial.can_reach_with_stride(
        rook.character.name, ally.character.name, 5,
    ):
        return 0.0
    # At least one enemy with offense?
    if not any(e.damage_dice for e in enemies):
        return 0.0
    # EV = resistance savings for one intercepted hit
    from pf2e.combat_math import guardians_armor_resistance
    return float(guardians_armor_resistance(rook.character.level))
```

Note: the `from sim.grid import` inside the function is deliberate to avoid circular imports at module load. `pf2e/tactics.py` can't import `sim/` at the top level without creating a cycle.

Alternative: rely entirely on `spatial.distance_ft(rook.character.name, ally.character.name)` via the Protocol. That's cleaner:

```python
if spatial.distance_ft(rook.character.name, ally.character.name) > 10:
    return 0.0
```

Use this version — it avoids the `sim/` import entirely.

### Step 7: Update `_evaluate_reaction_stride` (Gather to Me defensive EV)

In `pf2e/tactics.py`. Currently this evaluator returns `expected_damage_dealt=0.0` with the justification "Defensive value pending Checkpoint 4." Now it fills in the defensive value.

```python
def _evaluate_reaction_stride(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Gather to Me! — allies Stride toward banner aura.
    
    Defensive value:
    1. Allies entering the banner aura gain temp HP (if planted)
    2. Allies leaving enemy reach prevent expected damage
    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=2)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796 — temp HP source)
    """
    will_respond: list[str] = []
    cannot_respond: list[str] = []
    
    for sq in ctx.squadmates:
        if _has_reaction(sq):
            will_respond.append(sq.character.name)
        else:
            cannot_respond.append(sq.character.name)
    
    # Compute defensive EV for responding squadmates
    temp_hp_total = 0.0
    reposition_total = 0.0
    
    if ctx.banner_planted:
        temp_hp_per_ally = plant_banner_temp_hp(ctx.commander.character.level)
    else:
        temp_hp_per_ally = 0
    
    for sq in ctx.squadmates:
        if sq.character.name in cannot_respond:
            continue
        
        # (1) Temp HP value for allies entering aura
        currently_in_aura = ctx.spatial.is_in_banner_aura(sq.character.name)
        if not currently_in_aura and ctx.banner_planted:
            # Ally will Stride into aura, gain temp HP
            expected_dmg = _expected_damage_to_ally(sq, ctx)
            temp_hp_total += temp_hp_ev(temp_hp_per_ally, expected_dmg)
        
        # (2) Repositioning value — damage prevented by leaving enemy reach
        # Simplified: sum expected damage from enemies whose nearest PC is
        # this ally (those are assumed to target this ally)
        reposition_total += _damage_prevented_by_reposition(sq, ctx)
    
    total_avoided = temp_hp_total + reposition_total
    sources: dict[str, float] = {}
    if temp_hp_total > 0:
        sources["plant_banner_temp_hp"] = temp_hp_total
    if reposition_total > 0:
        sources["gather_reposition"] = reposition_total
    
    # Justification text
    responding = len(will_respond)
    total = len(ctx.squadmates)
    justification = (
        f"Gather to Me! \u2192 {responding} of {total} squadmates "
        f"Stride toward banner aura ({defn.action_cost} action). "
        f"Defensive EV: {total_avoided:.2f} "
        f"(temp HP: {temp_hp_total:.2f}, reposition: {reposition_total:.2f})."
    )
    
    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        expected_damage_avoided=total_avoided,
        justification=justification,
        squadmates_responding=responding,
        damage_prevented_sources=sources,
    )
```

Helper functions (module-private to `pf2e/tactics.py`):

```python
def _expected_damage_to_ally(
    ally: CombatantState, ctx: TacticContext,
) -> float:
    """Expected damage to this ally this round across all enemy attacks.
    
    Heuristic: each enemy attacks their nearest PC. For a given ally,
    sum expected_enemy_turn_damage from enemies whose nearest PC is
    this ally.
    """
    total = 0.0
    for enemy in ctx.enemies:
        if not enemy.damage_dice:
            continue
        if _nearest_pc_to_enemy(enemy, ctx) == ally.character.name:
            total += expected_enemy_turn_damage(enemy, ally)
    return total


def _nearest_pc_to_enemy(enemy: EnemyState, ctx: TacticContext) -> str:
    """Which PC (commander or squadmate) is nearest to this enemy?"""
    candidates = [ctx.commander] + list(ctx.squadmates)
    min_dist = float("inf")
    nearest_name = ""
    for pc in candidates:
        dist = ctx.spatial.distance_ft(enemy.name, pc.character.name)
        if dist < min_dist:
            min_dist = dist
            nearest_name = pc.character.name
    return nearest_name


def _damage_prevented_by_reposition(
    ally: CombatantState, ctx: TacticContext,
) -> float:
    """Damage prevented if ally Strides away from enemies threatening them.
    
    Simplification: sum expected damage from enemies whose nearest PC is
    this ally AND who are currently within melee reach (5-10 ft) of the
    ally. Gather to Me moves the ally toward the banner; we assume this
    Strides the ally out of those enemies' reach.
    
    For Checkpoint 4, this is a heuristic. A proper implementation would
    check where the ally lands and recompute reach. Flag for Checkpoint 5.
    """
    total = 0.0
    for enemy in ctx.enemies:
        if not enemy.damage_dice:
            continue
        if _nearest_pc_to_enemy(enemy, ctx) != ally.character.name:
            continue
        dist = ctx.spatial.distance_ft(enemy.name, ally.character.name)
        # Enemy within melee range (treat 10 ft as upper bound)
        if dist <= 10:
            total += expected_enemy_turn_damage(enemy, ally)
    return total
```

### Step 8: Update `_evaluate_free_step` (Defensive Retreat defensive EV)

```python
def _evaluate_free_step(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Defensive Retreat — allies Step up to 3 times as free actions.
    
    Defensive value: damage prevented by each ally Stepping out of enemy
    reach. 3 × 5 ft = 15 ft total movement; sufficient to clear 5-ft
    melee reach (1 Step) and 10-ft reach (2 Steps).
    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=1)
    """
    any_in_aura = any(
        ctx.spatial.is_in_banner_aura(sq.character.name)
        for sq in ctx.squadmates
    )
    if not any_in_aura:
        return TacticResult(
            tactic_name=defn.name,
            action_cost=defn.action_cost,
            eligible=False,
            ineligibility_reason="No squadmates in banner aura.",
        )
    
    # Compute defensive EV
    retreat_total = 0.0
    for sq in ctx.squadmates:
        if not ctx.spatial.is_in_banner_aura(sq.character.name):
            continue
        retreat_total += _damage_prevented_by_reposition(sq, ctx)
    
    sources: dict[str, float] = {}
    if retreat_total > 0:
        sources["retreat_steps"] = retreat_total
    
    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        expected_damage_avoided=retreat_total,
        justification=(
            f"Defensive Retreat \u2192 Squadmates Step away from enemies "
            f"({defn.action_cost} actions). Defensive EV: {retreat_total:.2f}."
        ),
        damage_prevented_sources=sources,
    )
```

### Step 9: Update `scenarios/checkpoint_1_strike_hard.scenario`

Add offensive stats to Bandit1 so defensive-EV tests can use this scenario:

```
[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2
```

This is a moderately threatening L1 enemy: +7 attack (against AC 15-19, hits 35-55% of the time), 1d8+3 damage (avg 7.5 per hit), 2 attacks per turn.

The Strike Hard regression test (EV 8.55 offensive) is unchanged — Strike Hard doesn't produce defensive EV. But future tests can use this scenario to compute defensive EV from banner temp HP.

### Step 10: Integration tests — `tests/test_defense.py`

Create a new test file:

```python
"""Tests for Checkpoint 4 defensive value computation."""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.combat_math import (
    expected_enemy_turn_damage, expected_incoming_damage,
    guardians_armor_resistance, plant_banner_temp_hp, temp_hp_ev,
)
from pf2e.tactics import (
    DEFENSIVE_RETREAT, GATHER_TO_ME, STRIKE_HARD,
    evaluate_tactic, intercept_attack_ev,
)
from pf2e.types import SaveType
from sim.grid import GridState
from sim.grid_spatial import GridSpatialQueries
from sim.scenario import load_scenario
from tests.fixtures import (
    make_aetregan, make_dalai, make_erisen, make_rook,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


class TestCoreMath:
    """Unit tests for the math primitives."""
    
    def test_plant_banner_temp_hp_scaling(self):
        assert plant_banner_temp_hp(1) == 4
        assert plant_banner_temp_hp(3) == 4
        assert plant_banner_temp_hp(4) == 8
        assert plant_banner_temp_hp(7) == 8
        assert plant_banner_temp_hp(8) == 12
        assert plant_banner_temp_hp(20) == 24
    
    def test_guardians_armor_resistance_scaling(self):
        assert guardians_armor_resistance(1) == 1
        assert guardians_armor_resistance(2) == 2
        assert guardians_armor_resistance(3) == 2
        assert guardians_armor_resistance(20) == 11
    
    def test_temp_hp_ev_capped(self):
        # Damage exceeds temp HP → temp HP fully absorbed
        assert temp_hp_ev(4, 8.0) == 4.0
    
    def test_temp_hp_ev_partial(self):
        # Damage less than temp HP → only damage absorbed
        assert temp_hp_ev(4, 2.5) == 2.5
    
    def test_temp_hp_ev_zero_damage(self):
        assert temp_hp_ev(4, 0.0) == 0.0


class TestExpectedIncomingDamage:
    """Tests for the per-Strike enemy damage EV."""
    
    def _make_bandit(self, atk: int = 7) -> EnemyState:
        return EnemyState(
            name="Bandit1",
            ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5),
            attack_bonus=atk,
            damage_dice="1d8",
            damage_bonus=3,
            num_attacks_per_turn=2,
        )
    
    def test_first_strike_against_dalai(self):
        bandit = self._make_bandit()
        dalai = CombatantState.from_character(make_dalai())
        ev = expected_incoming_damage(bandit, dalai, attack_number=1)
        # Compute by hand: AC 16 (Dalai), attack +7 vs AC 16.
        # Verify the EV is in a sensible range (>0, < hit_dmg avg)
        assert ev > 0.0
        assert ev < 8.0  # hit damage avg + some margin
    
    def test_second_strike_map_reduces_ev(self):
        bandit = self._make_bandit()
        dalai = CombatantState.from_character(make_dalai())
        ev1 = expected_incoming_damage(bandit, dalai, attack_number=1)
        ev2 = expected_incoming_damage(bandit, dalai, attack_number=2)
        assert ev2 < ev1  # MAP reduces EV
    
    def test_rook_resistance_reduces_ev(self):
        """Rook's Guardian's Armor reduces expected damage by 1 × hit_prob."""
        bandit = self._make_bandit()
        # Rook in full plate = Guardian's Armor active
        rook = make_rook_combat_state()
        ev_rook = expected_incoming_damage(bandit, rook, attack_number=1)
        # Same attack on a non-Guardian for comparison
        dalai = CombatantState.from_character(make_dalai())
        ev_dalai = expected_incoming_damage(bandit, dalai, attack_number=1)
        # Rook's EV is LOWER because of resistance + higher AC
        assert ev_rook < ev_dalai
    
    def test_no_damage_dice_returns_zero(self):
        bandit = EnemyState(
            name="Harmless", ac=15,
            saves={SaveType.REFLEX: 0, SaveType.FORTITUDE: 0, SaveType.WILL: 0},
            position=(5, 5),
            attack_bonus=0, damage_dice="", damage_bonus=0,
            num_attacks_per_turn=0,
        )
        dalai = CombatantState.from_character(make_dalai())
        assert expected_incoming_damage(bandit, dalai) == 0.0


class TestInterceptAttackEv:
    """Tests for the standalone intercept_attack_ev function."""
    
    def _setup(self, ally_pos: tuple[int, int], enemy_has_offense: bool = True):
        """Return (rook, ally, enemies, spatial) fixture."""
        grid = GridState(rows=10, cols=10, walls=set())
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        rook = make_rook_combat_state()
        rook.position = (5, 5)
        # Ally at specified position
        dalai = CombatantState.from_character(make_dalai())
        dalai.position = ally_pos
        # Enemy at (5, 7) — adjacent to where a (5, 6) ally would be
        damage = "1d8" if enemy_has_offense else ""
        enemy = EnemyState(
            name="Bandit1", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 7),
            attack_bonus=7, damage_dice=damage, damage_bonus=3,
            num_attacks_per_turn=2,
        )
        spatial = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[rook, dalai], enemies=[enemy],
            banner_position=None, banner_planted=False,
        )
        return rook, dalai, [enemy], spatial
    
    def test_ally_adjacent_and_threatened(self):
        """Ally at (5, 6), Rook at (5, 5). Distance 5 ft. Should intercept."""
        rook, ally, enemies, spatial = self._setup((5, 6))
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        # Resistance at L1 = 1
        assert ev == pytest.approx(1.0, abs=EV_TOLERANCE)
    
    def test_ally_too_far(self):
        """Ally at (5, 9), Rook at (5, 5). Distance 20 ft. Out of range."""
        rook, ally, enemies, spatial = self._setup((5, 9))
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0
    
    def test_rook_no_guardian_reaction(self):
        rook, ally, enemies, spatial = self._setup((5, 6))
        rook.guardian_reactions_available = 0
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0
    
    def test_no_offensive_enemy(self):
        rook, ally, enemies, spatial = self._setup(
            (5, 6), enemy_has_offense=False,
        )
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0


class TestGatherToMeDefensive:
    """Tests for Gather to Me!'s defensive EV."""
    
    def test_temp_hp_for_ally_entering_aura(self):
        """Banner planted, ally outside aura with threatening enemy.
        
        Gather to Me pulls ally into aura → temp HP value in defensive EV.
        """
        # Specifics left to the agent — verify that:
        # 1. result.expected_damage_avoided > 0
        # 2. result.damage_prevented_sources has "plant_banner_temp_hp" key
        # 3. The value is min(4, expected_damage)
        ...  # Implement based on the scenario setup
    
    def test_no_defensive_ev_without_banner(self):
        """Without planted banner, Gather still runs but no temp HP EV."""
        # Verify: result.damage_prevented_sources has no "plant_banner_temp_hp"
        ...
    
    def test_strike_hard_regression_from_scenario_file(self):
        """EV 8.55 unchanged after Checkpoint 4 changes."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )
        # Strike Hard produces no defensive EV
        assert result.expected_damage_avoided == 0.0
        assert result.damage_prevented_sources == {}
```

Implement the specific scenarios for `test_temp_hp_for_ally_entering_aura` and `test_no_defensive_ev_without_banner` based on the patterns above. The test should:
1. Build a scenario where at least one ally is OUT of the 40-ft planted burst
2. The ally is within threat range of an enemy with offensive stats
3. Call `evaluate_tactic(GATHER_TO_ME, ctx)` 
4. Assert `result.damage_prevented_sources["plant_banner_temp_hp"] > 0`
5. Assert the value is bounded by `min(4, expected_damage)` (use `pytest.approx`)

### Step 11: Update CHANGELOG.md

```markdown
## [4.0] - Checkpoint 4: Defensive Value Computation

### Correctness fix
- **Planted banner aura expands to 40-ft burst.** The Commander's base
  banner is a 30-ft emanation. When planted via the Plant Banner feat,
  "any effects that normally happen in an emanation around your banner
  instead happen in a burst that is 10 feet larger" — so the aura
  expands to 40 ft. Previous checkpoints hardcoded 30 ft regardless of
  banner state. Fixed in `GridSpatialQueries.is_in_banner_aura()`.
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)

### Foundation updates
- `GridSpatialQueries.__init__` now requires `banner_planted: bool`
  (no default) — explicit choice, no silent fallback.
- `Scenario.build_tactic_context()` threads `banner_planted` to
  `GridSpatialQueries`.
- `EnemyState` extended with offensive stats: `attack_bonus`,
  `damage_dice`, `damage_bonus`, `num_attacks_per_turn`. All optional.
  Empty `damage_dice` means the enemy has no modeled offensive EV.
- Scenario file `[enemies]` line format extended:
  `m1 name=X ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2`
- `TacticResult.damage_prevented_sources: dict[str, float]` added with
  canonical keys: plant_banner_temp_hp, guardians_armor_resistance,
  intercept_attack, gather_reposition, retreat_steps.

### New math helpers in pf2e/combat_math.py
- `plant_banner_temp_hp(level)` — 4 * (1 + level // 4)
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
- `guardians_armor_resistance(level)` — 1 + level // 2
  (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
- `_has_guardians_armor(character)` — uses guardian_reactions>0 + armor
  ac_bonus>=4 as proxy for Guardian-in-armor
- `expected_incoming_damage(attacker, target, attack_number)` — enemy
  Strike EV with MAP, target AC, and Guardian's Armor resistance
- `expected_enemy_turn_damage(attacker, target)` — sum across enemy's
  num_attacks_per_turn
- `temp_hp_ev(temp_hp, expected_damage)` — min(temp_hp, expected_damage)

### Tactic evaluator updates
- `_evaluate_reaction_stride` (Gather to Me!) now computes defensive EV:
  temp HP for allies entering planted-banner burst, plus damage
  prevented by allies leaving enemy reach.
- `_evaluate_free_step` (Defensive Retreat) now computes defensive EV:
  damage prevented by Steps out of enemy reach.

### New standalone function
- `intercept_attack_ev(rook, ally, enemies, spatial)` in pf2e/tactics.py.
  Not wired into any tactic evaluator (Intercept Attack is a Guardian
  reaction, not a tactic). Checkpoint 5's turn evaluator will call it.

### Scenario updates
- scenarios/checkpoint_1_strike_hard.scenario — Bandit1 now has
  offensive stats (atk=7 dmg=1d8 dmg_bonus=3 attacks=2).

### Design decisions
- Intercept Attack EV is conservative: models only resistance savings
  per intercepted hit (1 at L1). "Preventing crits on squishy allies"
  and "keeping allies conscious" require HP tracking (future work).
- Enemy target selection heuristic: "attacks nearest PC." Smarter AI
  flagged as future work.
- Temp HP non-stacking rule not enforced; Plant Banner is the only
  active temp HP source at L1.
- Repositioning value uses simplified "if enemy within 10 ft, assume
  Gather/Retreat moves ally out of reach." Proper post-movement reach
  recomputation is Checkpoint 5.
```

---

## Validation Checklist

- [ ] Step 1 completed: 181 existing tests still pass after `banner_planted` threading
- [ ] Step 1d: 40-ft planted aura regression test passes
- [ ] Step 2: `EnemyState` extensions build cleanly
- [ ] Step 3: Scenario parser accepts new fields; old scenarios still parse
- [ ] Step 4: Core math helpers work (`TestCoreMath` class passes)
- [ ] Step 5: `TacticResult.damage_prevented_sources` added
- [ ] Step 6: `intercept_attack_ev` function works (`TestInterceptAttackEv` passes)
- [ ] Step 7: Gather to Me's defensive EV shows up in `damage_prevented_sources`
- [ ] Step 8: Defensive Retreat's defensive EV shows up in `damage_prevented_sources`
- [ ] Step 9: checkpoint_1_strike_hard.scenario still loads cleanly
- [ ] Step 10: All integration tests pass
- [ ] **Strike Hard regression**: EV 8.55 offensive, 0 defensive, empty damage_prevented_sources
- [ ] Target: ~200-220 tests total
- [ ] CHANGELOG updated
- [ ] All docstrings cite AoN URLs
- [ ] No files outside the listed scope

## Common Pitfalls

**Required parameter breaks silent constructions.** After Step 1a, every direct `GridSpatialQueries(...)` call must pass `banner_planted`. If `test_grid_spatial.py` has tests you forgot to update, they'll fail with a TypeError. Grep for `GridSpatialQueries(` in the test files to find all call sites before running the suite.

**The 10-ft Intercept range uses strict distance_ft, not Chebyshev.** The 10-ft-reach exception (2 squares diagonal) applies to weapon reach, NOT to general "within N feet" triggers like Intercept Attack. Use `spatial.distance_ft(a, b) > 10` (which calls `grid.distance_ft`), not Chebyshev.

**Circular imports.** `pf2e/tactics.py` must not import from `sim/` at the top level. The `SpatialQueries` Protocol is structurally typed — `intercept_attack_ev(..., spatial: SpatialQueries)` accepts any object with the right methods. Use `spatial.distance_ft()` (from the Protocol) rather than importing `sim.grid.distance_ft` directly.

**Guardian's Armor resistance is per-hit, not per-EV.** The formula `raw_ev -= resistance * hit_prob` is correct. Don't just do `raw_ev -= resistance` — that would overcount (implies resistance applies even when attacks miss).

**Empty `damage_dice` is the no-offense sentinel.** `expected_incoming_damage` must early-return 0 when `damage_dice == ""`. Don't rely on `die_average("")` to work sensibly.

**Anthem is active in the Strike Hard regression scenario.** EV 8.55 uses anthem-buffed numbers. Don't regress this.

**`damage_prevented_sources` must use canonical keys.** Any divergence (e.g., "temp_hp_from_banner" instead of "plant_banner_temp_hp") breaks Checkpoint 6's formatter plans. Stick to the documented vocabulary.

**Floor the EV at 0.** After resistance subtraction, make sure the EV doesn't go negative. Use `max(0.0, raw_ev)`.

**`CombatantState.position` for the commander in `_nearest_pc_to_enemy`.** The commander is a PC too. Include them in the candidates list.

## What Comes After

1. You implement everything above.
2. You run `pytest tests/ -v` and confirm 100% pass.
3. You push.
4. I review.
5. We move to Checkpoint 5: the turn evaluator — combining offensive and defensive EV across 3-action sequences. This is where `intercept_attack_ev()` gets called, action economy matters, and the simulator can answer "what should Aetregan do this turn?"
