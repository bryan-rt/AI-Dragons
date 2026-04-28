# CP10 Architecture Reference

## What CP10 Is

CP10 is a full architectural rebuild of the `pf2e/` rules engine around nine sequenced layers. It does NOT change simulator behavior — the same scenarios produce the same EVs. What changes is internal structure: hand-written duplicated evaluators → declarative data registries with shared chassis evaluators.

**Current state:** 578 tests, EV 7.65 (23rd verification). CP10.1 Pass 1 brief written. **Pass 2 is next.**

**Why we're doing this:** `pf2e/actions.py` has grown to ~2,500 lines with deeply duplicated logic. Adding Grapple requires copying ~80 lines from Trip. Adding any new action class = new bespoke evaluator. CP10 makes it data entry. Also fixes three confirmed bugs (see below).

---

## Bugs Fixed by CP10

1. **~~Rook immune to Demoralize/Fear~~ (resolved Pass 1.5)** — Automaton Constructed Body waives construct immunities. Rook has `immunity_tags=frozenset()`. Engine behavior for Demoralize/Fear against Rook was correct all along. (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)

2. **Flourish completely untracked (CP10.2)** — Beam can recommend 2 Flourish actions/turn. Illegal under PF2e rules. Fix: `used_flourish_this_turn: bool` on `CombatantSnapshot`.

3. **Cover + Raise Shield stacking incorrectly (CP10.3)** — Both give +2 circumstance to AC. Stacking rules say take highest only = +2, not +4. Fix: `BonusTracker` in `pf2e/modifiers.py`.

---

## Layer Map

```
CP10.1  pf2e/rolls.py          Roll Foundation — flat_check(), RollType, FortuneState
CP10.2  pf2e/traits.py         Trait System — immunity, flourish, MAP gates
CP10.3  pf2e/modifiers.py      Modifier Assembly — BonusTracker, stacking rules
CP10.4  pf2e/contest_roll.py   Chassis 1: ContestRoll (Trip/Grapple/Demoralize/etc.)
        pf2e/auto_state.py     Chassis 2: AutoStateChange (Stand/Raise Shield/etc.)
        pf2e/strike.py         Chassis 3: Strike (melee/ranged/spell attack)
        pf2e/save_damage.py    Chassis 4: BasicSave (save for damage fractions)
        pf2e/save_condition.py Chassis 5: NonBasicSave (save for condition by degree)
        pf2e/movement.py       Chassis 6: Movement (Stride/Step/Sneak/Tumble Through)
CP10.5  pf2e/conditions.py     Condition State Machine — full taxonomy, override hierarchy
CP10.6  extend sim/grid*.py    Spatial — flanking geometry, cover, range increments
CP10.7  pf2e/detection.py      Detection — 4-state visibility model
CP10.8  extend damage_pipeline Damage Resolution — persistent damage, splash
CP10.9  extend round_state     Death/Dying — dying N, wounded N, recovery checks
```

Dependency order: 10.1 → 10.2 → 10.3 → 10.4 → 10.5 → 10.6 → 10.7 → 10.8 → 10.9

---

## CP10.1 Detail: Roll Foundation (PASS 1 COMPLETE — PASS 2 NEXT)

**New file:** `pf2e/rolls.py`

**Purely additive.** No existing file changes. EV 7.65 trivially maintained.

### Types

```python
class RollType(Enum):
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=2284)"""
    STANDARD = auto()  # d20 + modifier, nat-1/20 degree shifts apply
    FLAT     = auto()  # d20 only, NO modifiers, no degree shifts

class FortuneState(Enum):
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=2849)"""
    NORMAL     = auto()  # roll once
    FORTUNE    = auto()  # roll twice, take higher
    MISFORTUNE = auto()  # roll twice, take lower
    CANCELLED  = auto()  # both present → cancel, roll once normally

    @staticmethod
    def combine(has_fortune: bool, has_misfortune: bool) -> "FortuneState": ...
```

### Key function

```python
def flat_check(dc: int) -> float:
    """P(d20 >= dc). No modifiers ever. Clamped to [0.0, 1.0].
    DC 5→0.80 (concealment), DC 11→0.50 (hidden), DC 15→0.30 (persistent dmg)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169)
    """
    return max(0.0, min(1.0, (21 - dc) / 20))
```

### Tests: `tests/test_cp10_1_rolls.py` (~20 tests)

Key assertions:
- `flat_check(5) == pytest.approx(0.80)`
- `flat_check(11) == pytest.approx(0.50)`
- `flat_check(15) == pytest.approx(0.30)`
- `flat_check(21) == pytest.approx(0.0)`
- `flat_check(0) == pytest.approx(1.0)` (clamped)
- `flat_check(-10) == pytest.approx(1.0)` (clamped)
- `flat_check(99) == pytest.approx(0.0)` (clamped)
- `FortuneState.combine(True, True) == FortuneState.CANCELLED`
- `FortuneState.combine(True, False) == FortuneState.FORTUNE`
- `FortuneState.combine(False, True) == FortuneState.MISFORTUNE`
- `FortuneState.combine(False, False) == FortuneState.NORMAL`
- `FortuneState.CANCELLED != FortuneState.NORMAL`
- `RollType.STANDARD != RollType.FLAT`
- EV 7.65 regression (24th verification)

### Confirmed design decisions

- **D34:** `D20Outcomes` stays in `combat_math.py` through CP10.3. Not moved in CP10.1.
- **D33:** Fortune distribution math (roll-twice-take-higher PMF) deferred to CP10.4.
- **D32:** `flat_check()` is a named function, not inline per evaluator.
- CP10.1 is **purely additive** — `git diff --name-only` should show only 2 new files.

### Open questions for Pass 2 (resolve before writing brief)

**Q1 — Flat check audit:** How many places in `actions.py` currently hardcode flat check probabilities as inline fractions (e.g., `11/20` for hidden, `5/20` for concealment)? The CLI agent should report this count before implementation. These are migration targets for CP10.7.

**Q2 — D34 confirm:** Confirm that `D20Outcomes` and `enumerate_d20_outcomes` stay in `combat_math.py` through CP10.3. (Recommendation: yes, migration happens naturally when CP10.3 BonusTracker touches all callers.)

**Q3 — Fortune math location:** When CP10.4 chassis evaluators need fortune to affect the d20 distribution, should `enumerate_d20_outcomes_with_fortune(bonus, dc, fortune: FortuneState)` live in `rolls.py` or `combat_math.py`? (Recommendation: `rolls.py` — it's a roll mechanics concern, not a character math concern.)

**Q4 — Nat-1/nat-20 encoding:** Should `RollType.STANDARD` carry an explicit `has_degree_shift: bool = True` to make the nat-1/nat-20 rule explicit, or leave it implicit? This matters when CP10.7 adds `RollType.FLAT` callers. (Recommendation: defer — implicit is sufficient for CP10.1, add if CP10.7 needs it.)

---

## CP10.2 Detail: Trait System

**New file:** `pf2e/traits.py`

```python
class MechanicalCategory(Enum):
    MAP | FLOURISH | OPEN | PRESS | REACTION_TRIGGER | IMMUNITY_GATE |
    DISRUPTION | AUDITORY | VISUAL | LINGUISTIC | STANCE | NONE

@dataclass(frozen=True)
class TraitDef:
    name: str
    mechanical_category: MechanicalCategory
    description: str
    aon_url: str

TRAIT_DEFINITIONS: dict[str, TraitDef]
```

Key functions:
```python
def check_trait_immunity(action_traits: frozenset[str], target_immunity_tags: frozenset[str]) -> bool
def check_flourish(defn, actor_snapshot) -> bool
def check_open_press(defn, actor_snapshot) -> bool
def get_triggers_reactive_strike(action_traits: frozenset[str]) -> bool
```

New field on `Character`:
```python
immunity_tags: frozenset[str] = field(default_factory=frozenset)
```

Automaton Constructed Body waives construct immunities.
Rook has `immunity_tags=frozenset()`. Engine behavior
for Demoralize/Fear against Rook was correct all along.
(AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)

New field on `CombatantSnapshot`:
```python
used_flourish_this_turn: bool = False
```

---

## CP10.3 Detail: Modifier Assembly

**New file:** `pf2e/modifiers.py`

```python
class BonusType(Enum):
    CIRCUMSTANCE | STATUS | ITEM | PROFICIENCY | UNTYPED

@dataclass
class BonusTracker:
    def add(self, value: int, type: BonusType, source: str) -> None: ...
    def total(self) -> int: ...
```

Stacking rules (AoN verified):

| Type | Multiple bonuses | Multiple penalties |
|---|---|---|
| Circumstance | Highest only | Worst only |
| Status | Highest only | Worst only |
| Item | Highest only | Worst only |
| Untyped | N/A | **All stack** |

Cover (+2 circ AC) + Raise Shield (+2 circ AC) → +2, not +4.
MAP (untyped penalty) correctly stacks with all other penalties.

---

## CP10.4 Detail: Six Chassis

All built on Layers 1-3. Each chassis follows this pattern:

```python
@dataclass(frozen=True)
class [Chassis]Def:
    traits: frozenset[str]       # Layer 1
    # ... chassis parameters ... # Layer 2

[CHASSIS]_REGISTRY: dict[ActionType, [Chassis]Def]

def evaluate_[chassis](action, state, spatial=None) -> ActionResult:
    defn = REGISTRY[action.type]
    # 1. Trait-driven eligibility (from traits.py)
    # 2. Chassis-driven eligibility
    # 3. Chassis math
    # 4. Trait post-processing
```

### CP10.4.1 ContestRoll — highest priority

Consolidates: Trip, Disarm, Demoralize, Create a Diversion, Feint (5 existing)
Adds: Grapple, Shove, Reposition, Escape, First Aid (stub), Command Animal, Steal

Example registry entry (Trip):
```python
ContestRollDef(
    traits=frozenset({"attack"}),
    roller_skill=Skill.ATHLETICS,
    target_dc_attr="reflex",
    range_type="melee_reach",
    requires_held_weapon_trait="trip",
    crit_success=DegreeEffect(conditions_on_target=("prone",)),
    success=DegreeEffect(conditions_on_target=("prone",)),
    failure=DegreeEffect(),
    crit_failure=DegreeEffect(conditions_on_actor=("prone",)),
)
```

New conditions needed: `grabbed`, `restrained`.

---

## CP10.5 Detail: Condition State Machine

Override hierarchy: Restrained overrides Grabbed. Blinded overrides Dazzled. Immobilized from multiple sources: highest severity wins.

Value conditions: Frightened N (decrements end of turn), Dying N (recovery check start of turn), Wounded N, Slowed N, Stunned N, Quickened, Clumsy/Drained/Enfeebled/Sickened N.

---

## CP10.6–10.9 Brief Overview

**CP10.6 Spatial:** Flanking geometric query (line between attacker+ally passes through opposite sides of target square → +2 circumstance to attack via BonusTracker). Cover levels. Range increment penalties (−2 circ per increment beyond first).

**CP10.7 Detection:** Four states replace binary hidden/observed. Concealed=DC5 flat check, Hidden=DC11. Undetected=can't target. Migration target: all inline flat check fractions in `actions.py` (Q1 above).

**CP10.8 Damage:** Persistent damage scheduling (bleed/fire): each start of turn, take damage, then DC15 `flat_check(15)` to remove. Wire existing `damage_pipeline.py` into `apply_outcome_to_state()`.

**CP10.9 Death/Dying:** 0HP → Dying N (N=1+wounded, 2+wounded on crit). Recovery check = `flat_check(dc=10+dying)` each start of turn. Dying 4 = dead. First Aid fully functional.

---

## Beam Search Impact Analysis

- Current candidates/turn: ~77. After CP10: ~98 (+27%).
- Beam K=50/20/10 absorbs this — depth-1 prunes to 50 regardless of input count.
- Total evaluations ~6,958/character turn (microseconds each). No combinatorial explosion.
- Add `--profile` CLI flag in CP10.4 for early warning if any evaluator is unexpectedly expensive.
- Beam widths K=50/20/10 stay unchanged through all of CP10 (D37).

---

## Key Regression Numbers (Hold Through All of CP10)

- **EV 7.65** — Strike Hard, Rook Earthbreaker reaction Strike with Anthem vs Bandit1 AC 15. 23 verifications. Must hold at every CP10.x sub-checkpoint.
- **55% prone probability** — Tactical Takedown vs Reflex +5, DC 17.
- **EV 5.95 per target** — Light mortar 2d6 DC 17 vs Reflex +5.

## What Not to Change in CP10.1

- Beam search K=50/20/10 stays as-is (D37).
- `D20Outcomes` and `enumerate_d20_outcomes` stay in `combat_math.py` (D34).
- Fortune distribution math stays stubbed (D33).
- The three-pass methodology applies to every CP10.x sub-checkpoint.
- CP10.1 touches **zero existing files**. Only two new files: `pf2e/rolls.py` and `tests/test_cp10_1_rolls.py`.
