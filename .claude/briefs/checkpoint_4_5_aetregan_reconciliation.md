# Checkpoint 4.5: Aetregan Reconciliation

## Context

Actual Pathbuilder character sheet was provided. Reconciliation against `make_aetregan()` found several discrepancies. This is a small, focused checkpoint to fix them plus establish the HP-tracking infrastructure CP5 will need. Decision log (from conversation):

- **Plant Banner is NOT a level-1 feat for Aetregan.** She'll take it at level 2. Keep the CP4 infrastructure (`banner_planted` toggle, 40-ft burst logic, Plant Banner temp HP helper). It's correct per PF2e rules for any Commander who has the feat; it just doesn't apply to L1 Aetregan.
- **L1 Commander feat: Deceptive Tactics**, not Plant Banner. Enables Warfare Lore substitution for Create a Diversion and Feint. Combat-relevant, but the skill-action system it plugs into is CP5 work — we just note it here.
- **Folio tactics: Shields Up! instead of Defensive Retreat.** Implementing Shields Up! is CP5 work. In CP4.5 we remove Defensive Retreat from `FOLIO_TACTICS` and leave a stub entry for Shields Up! so the folio composition reflects reality.
- **HP tracking**: add `ancestry_hp` and `class_hp` fields to Character with default 0 (backward compatible); implement `max_hp()` helper; populate Aetregan's fields (6 / 8). Other squadmates' HP data is deferred to CP5.

## Scope

### What to implement

1. Character data fixes: Cha 10, Perception EXPERT, Scorpion Whip weapon.
2. HP infrastructure: `ancestry_hp` and `class_hp` fields, `max_hp()` helper.
3. Carried-banner support: aura follows commander when `banner_planted=False`.
4. Scenario parser: accept `planted = false`.
5. Folio tactic update: remove Defensive Retreat, stub in Shields Up!.
6. Update `scenarios/checkpoint_1_strike_hard.scenario` for carried banner.
7. Update existing tests to match new data.
8. New HP and carried-banner regression tests.
9. CHANGELOG.

### What NOT to implement

- No skill proficiency system (CP5).
- No Create a Diversion / Feint / Demoralize / Aid / Recall Knowledge action modeling (CP5).
- No Shields Up! evaluator (CP5 — we only add the tactic definition as a stub that returns ineligible).
- No HP tracking for Rook / Dalai / Erisen (CP5 — their `ancestry_hp` and `class_hp` stay at default 0).
- No Lengthy Diversion modeling (CP5).

## Pre-implementation: read existing code

Before editing, call `view` on:

- `pf2e/character.py` — `Character` dataclass field order; we're adding fields at the end.
- `pf2e/combat_math.py` — find a good location for `max_hp()`; probably near `effective_speed()`.
- `pf2e/tactics.py` — `FOLIO_TACTICS`, `DEFENSIVE_RETREAT`, `_evaluate_free_step`. We're removing `defensive_retreat` from the folio dict but keeping the definition and evaluator in the file for future use by other commanders.
- `sim/party.py` — `WHIP`, `make_aetregan()`. We're adding `SCORPION_WHIP` and updating the factory.
- `sim/grid_spatial.py` — `GridSpatialQueries.__init__`, `is_in_banner_aura`. We're adding carried-banner support.
- `sim/scenario.py` — `_parse_banner`. We're removing the `planted=false` restriction.
- `scenarios/checkpoint_1_strike_hard.scenario` — updating banner block.
- `tests/test_combat_math.py` — find `test_aetregan_perception`, any test that references Aetregan's Cha.
- `tests/test_grid_spatial.py` — `TestPlantedBannerAuraExpansion` regression test.
- `tests/test_scenario.py` — `TestKillerValidation.test_strike_hard_from_disk` — expectations on `scenario.banner_planted`.
- `CHANGELOG.md` — most recent entry is `[4.0]`; we're appending `[4.5]`.

---

## Implementation

### Step 1: Add HP fields to `Character`

In `pf2e/character.py`, add to the end of the `Character` dataclass:

```python
@dataclass(frozen=True)
class Character:
    # ... existing fields ...
    speed: int = 25
    # Max HP components — default 0 for backward compatibility.
    # Characters with tracked HP must set both.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2145)
    ancestry_hp: int = 0
    class_hp: int = 0
```

Both fields default to 0 so existing factories (Rook, Dalai, Erisen) continue to work unchanged.

### Step 2: Add `max_hp()` helper

In `pf2e/combat_math.py`, add near `effective_speed()`:

```python
def max_hp(character: Character) -> int:
    """Maximum hit points for a character.

    Formula: ancestry_hp + (class_hp + Con modifier) × level.
    Returns 0 if the character has no HP data (both ancestry_hp and
    class_hp at default 0) — this is a sentinel, not a real HP value.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2145)
    """
    con_mod = character.abilities.mod(Ability.CON)
    return character.ancestry_hp + (character.class_hp + con_mod) * character.level
```

### Step 3: Add Scorpion Whip weapon

In `sim/party.py`, add below `WHIP`:

```python
SCORPION_WHIP = Weapon(
    name="Scorpion Whip",
    category=WeaponCategory.MARTIAL,
    group=WeaponGroup.FLAIL,
    damage_die="d4",
    damage_die_count=1,
    damage_type=DamageType.SLASHING,
    range_increment=None,
    # Same as Whip minus the nonlethal trait: scorpion whips deal lethal
    # damage. Uncommon rarity is not modeled.
    # (AoN: https://2e.aonprd.com/Weapons.aspx?ID=114)
    traits=frozenset({"finesse", "reach", "trip", "disarm"}),
    hands=1,
)
```

Then re-export from `tests/fixtures.py` alongside `WHIP`:

```python
from sim.party import (
    # ... existing exports ...
    SCORPION_WHIP,
    WHIP,
    # ...
)
```

### Step 4: Update `make_aetregan()`

In `sim/party.py`, three changes to the factory:

1. `cha=12` → `cha=10`
2. `perception_rank=ProficiencyRank.TRAINED` → `perception_rank=ProficiencyRank.EXPERT`
3. `equipped_weapons=(EquippedWeapon(WHIP),)` → `equipped_weapons=(EquippedWeapon(SCORPION_WHIP),)`
4. Add `ancestry_hp=6, class_hp=8` at the end

Final factory:

```python
def make_aetregan() -> Character:
    """Aetregan — Commander (Battlecry!), level 1.

    Key ability: INT. Wields Scorpion Whip (finesse, reach, trip, disarm),
    wears Inventor Subterfuge Suit, carries Steel Shield. Has Shield
    Block feat and Drilled Reactions.

    AC: 10 + Dex 3 + trained medium 3 + suit 2 = 18 (no shield).
    Class DC: 10 + Int 4 + trained 3 = 17.
    Perception: Wis 1 + expert 5 = +6.
    Max HP: 6 (Elf) + (8 (Commander) + 1 (Con)) × 1 = 15.

    L1 Commander Feat: Deceptive Tactics (use Warfare Lore for Create
    a Diversion and Feint). Skill action modeling is CP5 work.

    Folio (5 tactics): Strike Hard!, Gather to Me!, Tactical Takedown,
    Mountaineering Training, Shields Up!. Prepared set (3): Strike Hard!,
    Gather to Me!, Tactical Takedown.

    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60 — Elf)
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — Commander)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7794 — Deceptive Tactics)
    """
    return Character(
        name="Aetregan",
        level=1,
        abilities=AbilityScores(
            str_=10, dex=16, con=12, int_=18, wis=12, cha=10,
        ),
        key_ability=Ability.INT,
        weapon_proficiencies={
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
        },
        armor_proficiency=ProficiencyRank.TRAINED,
        perception_rank=ProficiencyRank.EXPERT,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.TRAINED,
            SaveType.REFLEX: ProficiencyRank.EXPERT,
            SaveType.WILL: ProficiencyRank.EXPERT,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(SCORPION_WHIP),),
        armor=SUBTERFUGE_SUIT,
        shield=STEEL_SHIELD,
        has_shield_block=True,
        speed=30,
        ancestry_hp=6,
        class_hp=8,
    )
```

### Step 5: Carried-banner support in GridSpatialQueries

The rule: when `banner_planted=False`, the aura follows the commander (banner is worn on her backpack). When `banner_planted=True`, the aura is centered on the planted position.

In `sim/grid_spatial.py`, update `__init__` to track commander name, and update `is_in_banner_aura`:

```python
class GridSpatialQueries:
    def __init__(
        self,
        grid_state: GridState,
        commander: CombatantState,
        squadmates: list[CombatantState],
        enemies: list[EnemyState],
        banner_position: Pos | None,
        banner_planted: bool,
    ) -> None:
        self._grid = grid_state
        self._banner_pos = banner_position
        self._banner_planted = banner_planted
        self._commander_name = commander.character.name  # NEW
        # ... rest unchanged ...

    def is_in_banner_aura(self, name: str) -> bool:
        """True if combatant is within the banner aura.

        Planted banner: 40-ft burst from planted position.
        Carried banner: 30-ft emanation from commander's current position.
        (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — base 30-ft emanation)
        (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796 — planted expansion)
        """
        if self._banner_planted:
            if self._banner_pos is None:
                return False
            center = self._banner_pos
            radius = 40
        else:
            # Carried: aura emanates from commander's position
            center = self._positions.get(self._commander_name)
            if center is None:
                return False
            radius = 30
        pos = self._positions.get(name)
        if pos is None:
            return False
        return grid.distance_ft(pos, center) <= radius
```

### Step 6: Scenario parser — accept `planted=false`

In `sim/scenario.py`, `_parse_banner()`, remove the error for `planted=false`:

```python
def _parse_banner(
    text: str | None, grid_fallback_pos: Pos | None,
) -> tuple[Pos | None, bool]:
    """Parse [banner] section. Falls back to grid token if no section."""
    if not text:
        if grid_fallback_pos is not None:
            return grid_fallback_pos, True
        return None, False

    kv = _parse_meta(text)

    planted_str = kv.get("planted", "true").lower()
    if planted_str not in ("true", "false"):
        raise ScenarioParseError(
            f"[banner] planted must be 'true' or 'false', got '{planted_str}'"
        )
    planted = planted_str == "true"

    # Position is required for planted banners; informational for carried.
    # If carried banner has no position specified, return None.
    pos_str = kv.get("position")
    if pos_str is None:
        if planted:
            raise ScenarioParseError(
                "[banner] section with planted=true requires 'position = row, col'"
            )
        return None, False

    try:
        parts = pos_str.split(",")
        pos: Pos = (int(parts[0].strip()), int(parts[1].strip()))
    except (ValueError, IndexError) as e:
        raise ScenarioParseError(
            f"[banner] invalid position '{pos_str}': {e}"
        ) from e

    return pos, planted
```

The position is still stored when `planted=false` (for informational reasons — a scenario might specify where Aetregan's banner "started" the round even though the aura follows her), but `GridSpatialQueries` ignores it in favor of the commander's current position.

### Step 7: Update FOLIO_TACTICS — remove Defensive Retreat, stub Shields Up!

In `pf2e/tactics.py`, keep `DEFENSIVE_RETREAT` definition and `_evaluate_free_step` function in the file (for any future commander who has the tactic), but remove `defensive_retreat` from `FOLIO_TACTICS`.

Add a stub `SHIELDS_UP` definition and a placeholder evaluator:

```python
SHIELDS_UP = TacticDefinition(
    name="Shields Up!",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=12",
    action_cost=1,
    traits=frozenset({"offensive"}),
    range_type="banner_aura",
    target_type="all_squadmates_in_aura",
    granted_action="reaction_raise_shield",
    modifiers={
        "parry_weapons_position_defensively": True,
        "shield_cantrip_substitutable": True,
    },
    prerequisites=("squadmate_in_aura_with_shield",),
)


def _evaluate_reaction_raise_shield(
    defn: TacticDefinition, ctx: TacticContext,
) -> TacticResult:
    """Shields Up! — squadmates raise shields as reactions.

    NOT IMPLEMENTED in Checkpoint 4.5. Full evaluator is Checkpoint 5
    work (requires per-ally +2 AC defensive math against expected enemy
    Strikes). For now, returns eligible=False.
    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=12)
    """
    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=False,
        ineligibility_reason=(
            "Shields Up! evaluator is not yet implemented "
            "(pending Checkpoint 5)."
        ),
    )
```

Register the new evaluator in `_EVALUATORS`:

```python
_EVALUATORS: dict[
    str, Callable[[TacticDefinition, TacticContext], TacticResult]
] = {
    "reaction_strike": _evaluate_reaction_strike,
    "reaction_stride": _evaluate_reaction_stride,
    "stride_half_speed": _evaluate_stride_half,
    "free_step": _evaluate_free_step,
    "passive_buff": _evaluate_passive_buff,
    "reaction_raise_shield": _evaluate_reaction_raise_shield,  # NEW
}
```

Update `FOLIO_TACTICS`:

```python
FOLIO_TACTICS: dict[str, TacticDefinition] = {
    "strike_hard": STRIKE_HARD,
    "gather_to_me": GATHER_TO_ME,
    "tactical_takedown": TACTICAL_TAKEDOWN,
    "mountaineering_training": MOUNTAINEERING_TRAINING,
    "shields_up": SHIELDS_UP,
}
```

`PREPARED_TACTICS` unchanged (Strike Hard, Gather to Me, Tactical Takedown remains a reasonable L1 combat prep).

Update the module docstring at the top of `pf2e/tactics.py` to reflect the new folio composition.

### Step 8: Update the canonical scenario file

Update `scenarios/checkpoint_1_strike_hard.scenario`:

```
[banner]
planted = false
position = 5, 5
```

The `position` field is retained for informational purposes (shows where Aetregan is carrying the banner at round start); `GridSpatialQueries` ignores it when `planted=false`.

Update the scenario's `[meta]` description to reflect the correction:

```
[meta]
name = Strike Hard Validation
level = 1
source = Checkpoint 1 ground truth
description = Rook adjacent to Bandit1. Aetregan carries her banner (30-ft emanation). Anthem active.
```

### Step 9: Update tests affected by data changes

**`tests/test_combat_math.py`**:

- `test_aetregan_perception`: currently expects +4 (Wis 1 + trained 3). After CP4.5: +6 (Wis 1 + expert 5).
  ```python
  def test_aetregan_perception(self) -> None:
      """Wis 12 → mod +1, expert +5 = +6.
      
      Updated in Checkpoint 4.5: Commander has expert Perception at
      L1 per AoN (https://2e.aonprd.com/Classes.aspx?ID=66).
      """
      assert perception_bonus(make_aetregan()) == 6
  ```

- All existing whip-based tests pass `WHIP` explicitly as the weapon, not Aetregan's equipped weapon, so they continue to work unchanged. Verify by grep: any test that reads from `make_aetregan().equipped_weapons[0]` needs to update its expected weapon name from "Whip" to "Scorpion Whip".

**`tests/test_scenario.py`**:

- `TestKillerValidation.test_strike_hard_from_disk`: update the banner_planted assertion:
  ```python
  assert scenario.banner_planted is False  # was: True
  ```
- The `expected_damage_dealt == pytest.approx(8.55)` assertion must still hold. Strike Hard's evaluator doesn't depend on aura radius beyond "is the ally in aura?" and Rook at (5,6) is 5 ft from Aetregan at (5,5), within the 30-ft carried aura.

**`tests/test_grid_spatial.py`**:

- `TestPlantedBannerAuraExpansion.test_35ft_diagonal_in_planted_out_carried`: the test still works because for the carried case, the commander is at (0, 0) and the ally is 5 diagonal = 35 ft away, which is outside the 30-ft carried aura. Update the rationale comment to note that the False case now represents "carried banner follows commander":
  ```python
  def test_35ft_diagonal_in_planted_out_carried(self) -> None:
      """Ally 5 diagonal squares (35 ft) from banner.
      
      Planted (40-ft burst): IN aura.
      Carried (30-ft emanation centered on commander): OUT of aura.
      After CP4.5: carried banner aura is centered on commander, not
      on banner_position. This test's commander-at-(0,0) happens to
      match the banner_position used in the planted case, so the
      numerical result is unchanged.
      """
  ```

- Any other test in `test_grid_spatial.py` with `banner_planted=False` and a `banner_position` that DOESN'T match commander's position will change meaning. Grep for `banner_planted=False` and verify.

**`tests/test_tactics.py`**:

- `base_context` fixture uses `banner_planted=True`. Tests that depend on aura membership should still work (mock spatial queries don't rely on the real calculation).
- Note that `FOLIO_TACTICS` no longer contains `defensive_retreat`, but the test file imports `DEFENSIVE_RETREAT` directly and uses it in `TestDefensiveRetreat`. The tests still work because the tactic definition is still in the module — just not in the folio dict. No test change needed there.

### Step 10: Add new tests

Create `tests/test_hp.py`:

```python
"""Tests for HP infrastructure added in Checkpoint 4.5."""

from pf2e.character import Character
from pf2e.combat_math import max_hp
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


class TestMaxHp:
    def test_aetregan_max_hp_15(self) -> None:
        """Elf 6 + (Commander 8 + Con +1) × L1 = 15."""
        assert max_hp(make_aetregan()) == 15

    def test_unset_hp_returns_zero(self) -> None:
        """Characters with default ancestry_hp=0 and class_hp=0 return 0.
        
        This is a sentinel indicating HP data is not yet populated.
        CP5 will populate the squadmates.
        """
        assert max_hp(make_rook()) == 0
        assert max_hp(make_dalai()) == 0
        assert max_hp(make_erisen()) == 0

    def test_max_hp_scales_with_level(self) -> None:
        """Formula: ancestry_hp + (class_hp + Con) × level."""
        from pf2e.abilities import AbilityScores
        from pf2e.equipment import EquippedWeapon
        from pf2e.types import (
            Ability, ProficiencyRank, SaveType, WeaponCategory,
        )
        from tests.fixtures import WHIP
        
        # Synthetic L5 character: Elf, Con +2, Commander
        abilities = AbilityScores(str_=10, dex=14, con=14, int_=18, wis=10, cha=10)
        c5 = Character(
            name="Test",
            level=5,
            abilities=abilities,
            key_ability=Ability.INT,
            weapon_proficiencies={
                WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
                WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
                WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
                WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
            },
            armor_proficiency=ProficiencyRank.TRAINED,
            perception_rank=ProficiencyRank.EXPERT,
            save_ranks={
                SaveType.FORTITUDE: ProficiencyRank.TRAINED,
                SaveType.REFLEX: ProficiencyRank.EXPERT,
                SaveType.WILL: ProficiencyRank.EXPERT,
            },
            class_dc_rank=ProficiencyRank.TRAINED,
            equipped_weapons=(EquippedWeapon(WHIP),),
            ancestry_hp=6,
            class_hp=8,
        )
        # Expected: 6 + (8 + 2) × 5 = 6 + 50 = 56
        assert max_hp(c5) == 56
```

Add a carried-banner test to `tests/test_grid_spatial.py`:

```python
class TestCarriedBannerFollowsCommander:
    """Carried banner's aura is centered on the commander, not on banner_position.
    
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
    """
    
    def test_aura_centered_on_commander_when_carried(self) -> None:
        grid = GridState(rows=20, cols=20)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (10, 10)
        ally = make_rook_combat_state()
        ally.position = (10, 15)  # 5 squares orthogonal = 25 ft
        
        # Carried: aura emanates from commander at (10, 10).
        # Ally at 25 ft → IN 30-ft aura.
        # banner_position=(0, 0) is specified but IGNORED because carried.
        carried = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[ally], enemies=[],
            banner_position=(0, 0),  # deliberately bogus
            banner_planted=False,
        )
        assert carried.is_in_banner_aura("Rook") is True
    
    def test_aura_not_centered_on_commander_when_planted(self) -> None:
        """Sanity: planted banner does NOT follow commander."""
        grid = GridState(rows=20, cols=20)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (10, 10)
        ally = make_rook_combat_state()
        ally.position = (10, 15)
        
        # Planted at (0, 0), ally at (10, 15) = way more than 40 ft from banner
        planted = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[ally], enemies=[],
            banner_position=(0, 0),
            banner_planted=True,
        )
        assert planted.is_in_banner_aura("Rook") is False
```

Add a folio composition test to `tests/test_tactics.py`:

```python
class TestFolioComposition:
    """Aetregan's folio reflects her actual character build."""
    
    def test_folio_has_five_tactics(self) -> None:
        from pf2e.tactics import FOLIO_TACTICS
        assert len(FOLIO_TACTICS) == 5
    
    def test_folio_contains_shields_up_not_defensive_retreat(self) -> None:
        from pf2e.tactics import FOLIO_TACTICS
        assert "shields_up" in FOLIO_TACTICS
        assert "defensive_retreat" not in FOLIO_TACTICS
    
    def test_shields_up_not_yet_implemented(self) -> None:
        """Shields Up! evaluator is stubbed; CP5 implements it."""
        from pf2e.tactics import SHIELDS_UP, evaluate_tactic
        # Build a minimal context
        aetregan = CombatantState.from_character(make_aetregan())
        rook = make_rook_combat_state()
        ctx = TacticContext(
            commander=aetregan, squadmates=[rook], enemies=[],
            banner_position=None, banner_planted=False,
            spatial=MockSpatialQueries(), anthem_active=False,
        )
        result = evaluate_tactic(SHIELDS_UP, ctx)
        assert not result.eligible
        assert "not yet implemented" in result.ineligibility_reason.lower()
```

### Step 11: CHANGELOG

Append to `CHANGELOG.md`:

```markdown
## [4.5] - Aetregan Reconciliation

Small reconciliation pass to align `make_aetregan()` with the actual
Pathbuilder character sheet. No architectural changes — data fixes and
infrastructure prep for Checkpoint 5.

### Character corrections
- Cha: 12 → 10 (ability score correction)
- Perception: trained → expert (Commander gets expert Perception at L1)
  (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
- Weapon: Whip → Scorpion Whip (same d4/reach/finesse/trip/disarm,
  no nonlethal)
  (AoN: https://2e.aonprd.com/Weapons.aspx?ID=114)

### Folio composition
- Removed Defensive Retreat from `FOLIO_TACTICS` (not in Aetregan's
  actual folio). Tactic definition and `_evaluate_free_step` evaluator
  retained for other potential commanders.
- Added stub `SHIELDS_UP` tactic definition. Full evaluator deferred
  to CP5.
  (AoN: https://2e.aonprd.com/Tactics.aspx?ID=12)

### HP infrastructure (foundation for CP5)
- Added `ancestry_hp` and `class_hp` fields to `Character`, defaulting
  to 0 for backward compatibility.
- Added `max_hp(character)` helper in `pf2e/combat_math.py`.
  Formula: `ancestry_hp + (class_hp + Con_mod) × level`.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2145)
- Aetregan: `ancestry_hp=6, class_hp=8` → max HP 15 at L1.
- Rook, Dalai, Erisen: fields unset (default 0). Populating squadmate
  HP data is CP5 work.

### Carried-banner support
- `GridSpatialQueries.is_in_banner_aura` now handles carried banner
  (`banner_planted=False`): aura emanates from commander's current
  position, 30-ft radius. Previously only planted banners were
  supported.
- Scenario parser now accepts `planted = false`. `position` field is
  optional for carried banner (stored but ignored by spatial query).
- Updated `scenarios/checkpoint_1_strike_hard.scenario` to
  `planted = false` (reflecting Aetregan's actual L1 build without
  Plant Banner feat).

### Deferred to CP5
- L1 Commander feat Deceptive Tactics: lets Aetregan substitute
  Warfare Lore for Deception in Create a Diversion and Feint checks.
  Requires the skill-proficiency system.
- L1 skill feat Lengthy Diversion: extends off-guard duration from
  Create a Diversion.
- Shields Up! tactic evaluator.
- HP tracking for Rook, Dalai, Erisen.
- Skill proficiencies across all characters.

### Tests
- New: `tests/test_hp.py` (3 tests).
- New: carried-banner tests in `tests/test_grid_spatial.py`.
- New: folio composition tests in `tests/test_tactics.py`.
- Updated: `test_aetregan_perception` (+4 → +6).
- Updated: `TestKillerValidation.test_strike_hard_from_disk`
  (`banner_planted=False`).
- Regression: Strike Hard EV 8.55 still holds with carried banner
  (Rook at 5 ft from commander, well within 30-ft aura).
```

Target final test count: ~205-210.

---

## Validation checklist

- [ ] Step 1: `ancestry_hp` and `class_hp` fields on Character with defaults 0. All existing tests still pass (no factory needs updating yet except Aetregan).
- [ ] Step 2: `max_hp()` returns 15 for Aetregan, 0 for others.
- [ ] Step 3: `SCORPION_WHIP` constant exists with correct traits (no nonlethal, no uncommon). Re-exported from `tests/fixtures.py`.
- [ ] Step 4: `make_aetregan()` has Cha 10, Perception EXPERT, SCORPION_WHIP equipped, ancestry_hp=6, class_hp=8.
- [ ] Step 5: `GridSpatialQueries.is_in_banner_aura` returns True for an ally within 30 ft of commander when banner carried. Banner_position argument is ignored when `banner_planted=False`.
- [ ] Step 6: Scenario parser accepts `planted = false`. Position is optional when planted=false.
- [ ] Step 7: `FOLIO_TACTICS` has 5 entries including `shields_up`, excluding `defensive_retreat`. `SHIELDS_UP` evaluator returns ineligible.
- [ ] Step 8: `checkpoint_1_strike_hard.scenario` has `planted = false`. Strike Hard EV 8.55 still computes correctly from the file.
- [ ] Step 9: All updated tests pass.
- [ ] Step 10: New tests pass (HP, carried banner, folio composition).
- [ ] Step 11: CHANGELOG updated.
- [ ] **Full test suite passes** — target ~205-210 tests.
- [ ] **Strike Hard regression (EV 8.55) survives** — the killer test from CP1/CP2/CP3/CP4.

## Common pitfalls

**The regression EV 8.55 must still hold.** Strike Hard's evaluator checks whether Rook is in the banner aura. With carried banner, Aetregan at (5,5), Rook at (5,6) = 5 ft distance, within 30 ft. Rook is in aura. Evaluator proceeds normally. The anthem-buffed +8 attack vs AC 15 produces EV 8.55. If this doesn't hold, there's a bug in the carried-banner logic.

**Don't delete the Defensive Retreat tactic definition or its evaluator.** Only remove the `"defensive_retreat"` key from the `FOLIO_TACTICS` dict. The `DEFENSIVE_RETREAT` constant and `_evaluate_free_step` function stay in the module — they're correct code for any commander who has Defensive Retreat in their folio.

**Grep for `make_aetregan().equipped_weapons[0]`.** If any test inspects the weapon name on Aetregan's equipped weapon, it expects "Whip" and will fail against "Scorpion Whip". Update those tests to expect "Scorpion Whip" or to not check the name.

**Grep for tests that pass `WHIP` explicitly.** These test attack/damage/EV math with a specific weapon. They still work because they pass WHIP, not Aetregan's equipped weapon, and Whip mechanics are unchanged. Don't reflexively swap WHIP → SCORPION_WHIP in these tests; they're testing the Whip specifically.

**`banner_position` is stored but not used when `banner_planted=False`.** If a test relies on the aura being centered at `banner_position` when carried, it's testing the old (wrong) behavior. The correct behavior is "aura centered on commander". Update tests accordingly.

**Shields Up! returns ineligible.** The stub is intentional. Tests should not expect it to be eligible until CP5 implements the evaluator.

**HP defaults to 0 for non-Aetregan characters.** This is a temporary sentinel. CP5 will populate Rook/Dalai/Erisen. Don't panic if `max_hp(make_rook()) == 0` — that's by design for CP4.5.

**Scenario file position field stays but is informational.** Keeping `position = 5, 5` in the [banner] block with `planted = false` is not a bug; it's "where Aetregan happens to be at round start" in the informational layer. The spatial queries use commander's live position.

## What comes after

1. You implement CP4.5.
2. All tests pass, target ~205-210 total.
3. I review.
4. We move to CP5 Pass 1 — the full turn evaluator brief, with everything we've decided (full round, adversarial minimax, party-preservation-weighted victory scoring, outcome buckets, beam search K=50/20/10, strict PF2e defensive composition, kitchen sink action pool staged as CP5.1 / 5.2 / 5.3).
