# Checkpoint 5.1 Pass 3a: Foundation Implementation

## Context

CP5.1 is the full-round turn evaluator with adversarial enemies, hybrid state threading, beam search, and 15 action types. Pass 2 approved the full scope but split implementation into three phases:

- **Pass 3a (this brief)**: Foundation — data model extensions, types, helpers, data population
- **Pass 3b**: Algorithms — search, state threading, scoring, damage pipeline
- **Pass 3c**: Actions — per-action evaluators, integration, output formatting

Pass 3a is purely structural. No algorithms, no search, no evaluators. Just data model work. Target: ~30-40 new tests, 600-900 lines of new code.

Standing rules apply: verify against AoN, cite URLs, read existing code first, don't expand scope, test what you build.

## Scope

### What to implement in Pass 3a

1. `Skill` enum (16 skills) + `SKILL_ABILITY` lookup table
2. `Character` extensions: `skill_proficiencies`, `lores`, feat-presence flags
3. `skill_bonus()` and `lore_bonus()` helper functions
4. Populate Aetregan's skills and feat flags from her JSON
5. Populate Rook/Dalai/Erisen skills and HP data (grounded defaults, documented as such)
6. `ActionType` enum (15 action types)
7. `Action`, `ActionOutcome`, `ActionResult` dataclasses
8. `CombatantState` extensions: `current_hp`, `temp_hp`, `actions_remaining`
9. `EnemyState` extensions: `max_hp`, `current_hp`, `perception_bonus`, `actions_remaining`, + derived `perception_dc` property
10. Scenario parser: `[initiative]` section support (data only; ordering algorithm is 3b)
11. Tests for all the above
12. CHANGELOG

### What NOT to implement in Pass 3a

- `RoundState` (Pass 3b)
- Any search algorithm (Pass 3b)
- Per-action evaluators (Pass 3c)
- Damage pipeline (Pass 3b)
- Scoring function (Pass 3b)
- Stride destination enumeration heuristics (Pass 3c)
- `--debug-search` CLI flag (Pass 3c)
- Output formatter (Pass 3c)

## Pre-implementation: read existing code

Call `view` on:

- `pf2e/types.py` — existing enums; we're adding `Skill` alongside `Ability`, `ProficiencyRank`, `SaveType`
- `pf2e/character.py` — `Character`, `CombatantState`, `EnemyState`. We're extending all three.
- `pf2e/combat_math.py` — existing helper pattern; `skill_bonus()` and `lore_bonus()` go here near `save_bonus()`
- `pf2e/proficiency.py` — `proficiency_bonus()` signature
- `sim/party.py` — all four character factories. We're extending all four.
- `sim/scenario.py` — `Scenario` dataclass, `parse_scenario()`, `_split_into_sections()`. We're adding initiative parsing.
- `CHANGELOG.md` — format of existing entries

Grep:

- For every `make_aetregan()` call site to understand integration expectations.
- For `EnemyState(` constructions in tests (there are several in `test_defense.py`, `test_tactics.py`, etc.) — our new fields have defaults so existing calls work unchanged.

---

## Implementation

### Step 1: `Skill` enum + `SKILL_ABILITY` lookup

In `pf2e/types.py`, add at the end:

```python
class Skill(Enum):
    """The sixteen standard skills.
    
    Lores are tracked separately on Character.lores as a dict since they're
    arbitrary character-specific strings (Warfare Lore, Deity Lore, etc.).
    (AoN: https://2e.aonprd.com/Skills.aspx)
    """
    ACROBATICS = auto()
    ARCANA = auto()
    ATHLETICS = auto()
    CRAFTING = auto()
    DECEPTION = auto()
    DIPLOMACY = auto()
    INTIMIDATION = auto()
    MEDICINE = auto()
    NATURE = auto()
    OCCULTISM = auto()
    PERFORMANCE = auto()
    RELIGION = auto()
    SOCIETY = auto()
    STEALTH = auto()
    SURVIVAL = auto()
    THIEVERY = auto()
```

Also in `pf2e/types.py`, add the ability lookup:

```python
SKILL_ABILITY: dict[Skill, Ability] = {
    Skill.ACROBATICS: Ability.DEX,
    Skill.ARCANA: Ability.INT,
    Skill.ATHLETICS: Ability.STR,
    Skill.CRAFTING: Ability.INT,
    Skill.DECEPTION: Ability.CHA,
    Skill.DIPLOMACY: Ability.CHA,
    Skill.INTIMIDATION: Ability.CHA,
    Skill.MEDICINE: Ability.WIS,
    Skill.NATURE: Ability.WIS,
    Skill.OCCULTISM: Ability.INT,
    Skill.PERFORMANCE: Ability.CHA,
    Skill.RELIGION: Ability.WIS,
    Skill.SOCIETY: Ability.INT,
    Skill.STEALTH: Ability.DEX,
    Skill.SURVIVAL: Ability.WIS,
    Skill.THIEVERY: Ability.DEX,
}
```

### Step 2: `Character` extensions

In `pf2e/character.py`, add to the end of the `Character` dataclass:

```python
@dataclass(frozen=True)
class Character:
    # ... existing fields (up through ancestry_hp, class_hp) ...
    
    # Skill proficiencies — maps Skill to rank. Missing keys default to UNTRAINED.
    # (AoN: https://2e.aonprd.com/Skills.aspx)
    skill_proficiencies: dict[Skill, ProficiencyRank] = field(default_factory=dict)
    
    # Lore proficiencies — arbitrary character-specific strings.
    # e.g., {"Warfare": ProficiencyRank.TRAINED, "Deity": ProficiencyRank.TRAINED}
    # (AoN: https://2e.aonprd.com/Skills.aspx?ID=47)
    lores: dict[str, ProficiencyRank] = field(default_factory=dict)
    
    # Feat-presence flags for feats that affect action evaluator logic.
    # CP5.1 scope; may grow as CP5.2/5.3 add more feats.
    has_plant_banner: bool = False           # Commander Feat, not at L1 for Aetregan
    has_deceptive_tactics: bool = False      # Commander Feat 1 — Aetregan has this
    has_lengthy_diversion: bool = False      # Skill Feat — Aetregan has this
```

Note: `dict` is mutable even inside a frozen dataclass. By convention, these fields should not be mutated after construction. If you need to modify, produce a new Character via `dataclasses.replace`.

Required imports at top of `pf2e/character.py`:

```python
from pf2e.types import Ability, ProficiencyRank, SaveType, Skill, WeaponCategory
```

### Step 3: `skill_bonus()` and `lore_bonus()` helpers

In `pf2e/combat_math.py`, add near `save_bonus()`:

```python
def skill_bonus(character: Character, skill: Skill) -> int:
    """Total skill check bonus: ability mod + proficiency.
    
    Missing skill in skill_proficiencies defaults to UNTRAINED (0 proficiency).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2136)
    """
    from pf2e.types import SKILL_ABILITY
    ability = SKILL_ABILITY[skill]
    ability_mod = character.abilities.mod(ability)
    rank = character.skill_proficiencies.get(skill, ProficiencyRank.UNTRAINED)
    prof = proficiency_bonus(rank, character.level)
    return ability_mod + prof


def lore_bonus(character: Character, lore_name: str) -> int:
    """Total lore check bonus: Int mod + proficiency.
    
    Lores always use Int as the key ability, regardless of lore subject.
    Missing lore in character.lores defaults to UNTRAINED.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=47 — Lore)
    """
    ability_mod = character.abilities.mod(Ability.INT)
    rank = character.lores.get(lore_name, ProficiencyRank.UNTRAINED)
    prof = proficiency_bonus(rank, character.level)
    return ability_mod + prof
```

Import `Skill` at the top of `combat_math.py`:

```python
from pf2e.types import Ability, ProficiencyRank, SaveType, Skill
```

### Step 4: Populate Aetregan's skills and feat flags

In `sim/party.py`, update `make_aetregan()`. Her JSON shows:
- Trained: Acrobatics, Arcana, Crafting, Nature, Occultism, Religion, Society, Stealth, Survival, Thievery
- Untrained: Athletics, Deception, Diplomacy, Intimidation, Medicine, Performance
- Lores: Warfare (trained), Deity (trained)
- Feats: Deceptive Tactics, Lengthy Diversion (both relevant to CP5.1 action evaluators)

Add to the factory return:

```python
def make_aetregan() -> Character:
    """Aetregan — Commander (Battlecry!), level 1.
    
    ... existing docstring ...
    """
    return Character(
        # ... existing fields ...
        ancestry_hp=6,
        class_hp=8,
        skill_proficiencies={
            Skill.ACROBATICS: ProficiencyRank.TRAINED,
            Skill.ARCANA: ProficiencyRank.TRAINED,
            Skill.CRAFTING: ProficiencyRank.TRAINED,
            Skill.NATURE: ProficiencyRank.TRAINED,
            Skill.OCCULTISM: ProficiencyRank.TRAINED,
            Skill.RELIGION: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,
            Skill.STEALTH: ProficiencyRank.TRAINED,
            Skill.SURVIVAL: ProficiencyRank.TRAINED,
            Skill.THIEVERY: ProficiencyRank.TRAINED,
            # Untrained skills omitted — default to UNTRAINED via get()
        },
        lores={
            "Warfare": ProficiencyRank.TRAINED,
            "Deity": ProficiencyRank.TRAINED,
        },
        has_plant_banner=False,          # L2+ future upgrade
        has_deceptive_tactics=True,
        has_lengthy_diversion=True,
    )
```

### Step 5: Populate squadmate HP and skill data

Use grounded defaults per Pass 2. Document each as "grounded defaults; verify against character sheet."

#### Rook (Automaton Guardian)

```python
def make_rook() -> Character:
    """Rook — Automaton Guardian, level 1.
    
    ... existing docstring ...
    
    Added in CP5.1 Pass 3a:
    HP: 10 (Automaton) + (10 (Guardian) + 3 (Con)) × 1 = 23
    Skills: grounded defaults for Guardian + Automaton; verify against
    actual character sheet when available.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=67 — Guardian)
    """
    return Character(
        # ... existing fields ...
        ancestry_hp=10,  # Automaton
        class_hp=10,     # Guardian
        skill_proficiencies={
            Skill.ATHLETICS: ProficiencyRank.TRAINED,
            Skill.INTIMIDATION: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,       # Automaton affinity
            Skill.CRAFTING: ProficiencyRank.TRAINED,      # Automaton affinity
        },
        lores={},
    )
```

#### Dalai (Human Bard Warrior Muse)

```python
def make_dalai() -> Character:
    """Dalai Alpaca — Bard (Warrior Muse), level 1.
    
    ... existing docstring ...
    
    Added in CP5.1 Pass 3a:
    HP: 8 (Human) + (8 (Bard) + 1 (Con)) × 1 = 17
    Skills: grounded defaults for Bard + Warrior Muse; verify against
    actual character sheet when available.
    """
    return Character(
        # ... existing fields ...
        ancestry_hp=8,
        class_hp=8,
        skill_proficiencies={
            Skill.OCCULTISM: ProficiencyRank.TRAINED,      # Bard spellcasting
            Skill.PERFORMANCE: ProficiencyRank.TRAINED,    # Bard signature
            Skill.DIPLOMACY: ProficiencyRank.TRAINED,
            Skill.INTIMIDATION: ProficiencyRank.TRAINED,   # Warrior Muse
            Skill.ATHLETICS: ProficiencyRank.TRAINED,      # Warrior Muse
            Skill.ACROBATICS: ProficiencyRank.TRAINED,
        },
        lores={
            "Bardic": ProficiencyRank.TRAINED,
            "Warfare": ProficiencyRank.TRAINED,  # Shelyn follower, warrior muse
        },
    )
```

#### Erisen (Elf Inventor Munitions Master)

```python
def make_erisen() -> Character:
    """Erisen — Inventor (Munitions Master), level 1.
    
    ... existing docstring ...
    
    Added in CP5.1 Pass 3a:
    HP: 6 (Elf) + (8 (Inventor) + 2 (Con)) × 1 = 16
    Skills: grounded defaults for Inventor + Munitions Master; verify
    against actual character sheet when available.
    """
    return Character(
        # ... existing fields ...
        ancestry_hp=6,
        class_hp=8,
        skill_proficiencies={
            Skill.CRAFTING: ProficiencyRank.TRAINED,       # Inventor core
            Skill.ARCANA: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,
            Skill.ATHLETICS: ProficiencyRank.TRAINED,
            Skill.NATURE: ProficiencyRank.TRAINED,
        },
        lores={
            "Engineering": ProficiencyRank.TRAINED,
            "Alkenstar": ProficiencyRank.TRAINED,
        },
    )
```

### Step 6: `ActionType` enum

Create `pf2e/actions.py` (new module). Start with the enum and dataclasses:

```python
"""Action types and data structures for the turn evaluator.

Actions are the atomic choices a character makes during combat. Each
ActionType has an associated evaluator (implemented in Pass 3c) that
computes the outcome distribution for a given (action, state) pair.

Pass 3a delivers only the types — evaluators come in 3c.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ActionType(Enum):
    """All action types enumerable in CP5.1.
    
    Taxonomy:
    - Movement: STRIDE, STEP
    - Combat: STRIKE, TRIP, DISARM
    - Defense: RAISE_SHIELD, SHIELD_BLOCK (reaction)
    - Commander: PLANT_BANNER, ACTIVATE_TACTIC
    - Skill actions: DEMORALIZE, CREATE_A_DIVERSION, FEINT
    - Guardian reactions: INTERCEPT_ATTACK, EVER_READY
    - Control: END_TURN
    
    CP5.2 will add Taunt, healing, compositions, spells.
    CP5.3 will add Aid, Recall Knowledge, Seek/Hide/Sneak.
    """
    STRIDE = auto()
    STEP = auto()
    STRIKE = auto()
    TRIP = auto()
    DISARM = auto()
    RAISE_SHIELD = auto()
    SHIELD_BLOCK = auto()
    PLANT_BANNER = auto()
    ACTIVATE_TACTIC = auto()
    DEMORALIZE = auto()
    CREATE_A_DIVERSION = auto()
    FEINT = auto()
    INTERCEPT_ATTACK = auto()
    EVER_READY = auto()
    END_TURN = auto()
```

### Step 7: `Action`, `ActionOutcome`, `ActionResult` dataclasses

In `pf2e/actions.py`:

```python
@dataclass(frozen=True)
class Action:
    """A specific instance of an action, fully parameterized.
    
    Example:
        Action(type=ActionType.STRIDE, actor_name="Rook", 
               action_cost=1, target_position=(5, 8))
        Action(type=ActionType.STRIKE, actor_name="Aetregan",
               action_cost=1, target_name="Bandit1", weapon_name="Scorpion Whip")
        Action(type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
               action_cost=2, tactic_name="Strike Hard!")
    
    Unused fields stay at their defaults (empty string or None).
    The evaluator for each ActionType knows which fields are meaningful.
    """
    type: ActionType
    actor_name: str
    action_cost: int
    target_name: str = ""                               # single-target
    target_position: tuple[int, int] | None = None      # movement destination
    target_names: tuple[str, ...] = ()                  # multi-target (Create a Diversion)
    weapon_name: str = ""                               # STRIKE disambiguation
    tactic_name: str = ""                               # ACTIVATE_TACTIC


@dataclass(frozen=True)
class ActionOutcome:
    """One branch of an action's probability tree.
    
    Each outcome is a complete state-delta specification: what HP changes,
    what positions move, what conditions are applied or removed, what
    reactions get consumed.
    
    All dicts have convention: immutable after construction. Do not mutate.
    """
    probability: float
    hp_changes: dict[str, float] = field(default_factory=dict)
    position_changes: dict[str, tuple[int, int]] = field(default_factory=dict)
    conditions_applied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    conditions_removed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reactions_consumed: dict[str, int] = field(default_factory=dict)
    # Free-form description for debug output
    description: str = ""


@dataclass(frozen=True)
class ActionResult:
    """The evaluator's output for a single (action, state) pair.
    
    If eligible is False, outcomes is empty and ineligibility_reason explains.
    If eligible is True, outcomes is a tuple of ActionOutcome records whose
    probabilities sum to 1.0 (within floating-point tolerance).
    """
    action: Action
    outcomes: tuple[ActionOutcome, ...] = ()
    eligible: bool = True
    ineligibility_reason: str = ""
    
    @property
    def expected_damage_dealt(self) -> float:
        """Expected damage TO enemies across all outcomes.
        
        Negative hp_changes are damage; positive are healing.
        """
        total = 0.0
        for outcome in self.outcomes:
            for target_name, delta in outcome.hp_changes.items():
                if delta < 0:
                    total += outcome.probability * (-delta)
        return total
    
    @property
    def expected_damage_taken(self) -> float:
        """Expected damage TO the actor across all outcomes.
        
        Separate semantic from damage_dealt; the caller disambiguates
        using actor/target knowledge.
        """
        # Delegate to caller to filter by actor vs target
        # This property is intentionally simple; complex filtering is caller's job
        return 0.0  # placeholder; filled in by specific action evaluators
    
    def verify_probability_sum(self, tolerance: float = 1e-6) -> bool:
        """Sanity check: outcome probabilities sum to ~1.0 for eligible actions."""
        if not self.eligible:
            return len(self.outcomes) == 0
        total = sum(o.probability for o in self.outcomes)
        return abs(total - 1.0) < tolerance
```

### Step 8: `CombatantState` extensions

In `pf2e/character.py`, add fields to `CombatantState`:

```python
@dataclass
class CombatantState:
    # ... existing fields ...
    
    # HP tracking (added in Pass 3a for CP5.1)
    # current_hp=None means "at full HP" (computed from character.max_hp)
    current_hp: int | None = None
    temp_hp: int = 0
    
    # Action economy for the current turn (Pass 3b will reset this per turn)
    actions_remaining: int = 3
    
    @property
    def effective_current_hp(self) -> int:
        """Current HP with None treated as max."""
        from pf2e.combat_math import max_hp
        if self.current_hp is None:
            return max_hp(self.character)
        return self.current_hp
```

### Step 9: `EnemyState` extensions

In `pf2e/character.py`, add fields to `EnemyState`:

```python
@dataclass
class EnemyState:
    # ... existing fields ...
    
    # HP tracking (added in Pass 3a for CP5.1)
    max_hp: int = 20          # plausible L1 bandit default
    current_hp: int | None = None
    
    # Perception for initiative and Create-a-Diversion-style checks
    perception_bonus: int = 4  # plausible L1 enemy default
    
    # Action economy
    actions_remaining: int = 3
    
    @property
    def perception_dc(self) -> int:
        """DC for Deception/Stealth checks against this enemy."""
        return 10 + self.perception_bonus
    
    @property
    def effective_current_hp(self) -> int:
        """Current HP with None treated as max."""
        if self.current_hp is None:
            return self.max_hp
        return self.current_hp
```

### Step 10: Scenario parser `[initiative]` section

In `sim/scenario.py`, add initiative parsing. Start by adding a field to `Scenario`:

```python
@dataclass(frozen=True)
class Scenario:
    # ... existing fields ...
    
    # Initiative specification — Pass 3b uses this to roll/sort
    # None = use default seeded roll
    # Non-empty dict = explicit ordering (name → initiative total)
    # seed field used for reproducibility when rolling
    initiative_seed: int = 42
    initiative_explicit: dict[str, int] = field(default_factory=dict)
```

Parser helper:

```python
def _parse_initiative(text: str | None) -> tuple[int, dict[str, int]]:
    """Parse [initiative] section.
    
    Supports two modes:
    1. seed-only:
        [initiative]
        seed = 42
    2. explicit ordering:
        [initiative]
        Aetregan = 18
        Bandit1 = 12
    
    Returns (seed, explicit_dict). If section omitted, returns (42, {}).
    """
    if not text:
        return (42, {})
    
    seed = 42
    explicit: dict[str, int] = {}
    
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        
        if key.lower() == "seed":
            try:
                seed = int(value)
            except ValueError as e:
                raise ScenarioParseError(
                    f"[initiative] seed must be an integer: {value}"
                ) from e
        else:
            try:
                explicit[key] = int(value)
            except ValueError as e:
                raise ScenarioParseError(
                    f"[initiative] '{key}' must be an integer: {value}"
                ) from e
    
    return (seed, explicit)
```

Update `parse_scenario()` to wire this in:

```python
def parse_scenario(text: str) -> Scenario:
    sections = _split_into_sections(text)
    
    # ... existing parsing ...
    
    # NEW: initiative
    initiative_seed, initiative_explicit = _parse_initiative(
        sections.get("initiative")
    )
    
    return Scenario(
        # ... existing fields ...
        initiative_seed=initiative_seed,
        initiative_explicit=initiative_explicit,
    )
```

### Step 11: Tests

Create `tests/test_skills.py`:

```python
"""Tests for skill and lore proficiency system (CP5.1 Pass 3a)."""

import pytest

from pf2e.combat_math import lore_bonus, skill_bonus
from pf2e.types import Skill
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


EV_TOLERANCE = 0.01


class TestAetreganSkills:
    """Verified against JSON character sheet."""
    
    def test_warfare_lore_plus_8(self):
        """Int +4, trained +3, level 1 = +8."""
        assert lore_bonus(make_aetregan(), "Warfare") == 8
    
    def test_deity_lore_plus_8(self):
        assert lore_bonus(make_aetregan(), "Deity") == 8
    
    def test_arcana_plus_8(self):
        """Trained Int skill: +4 + 3 + 1 = +8."""
        assert skill_bonus(make_aetregan(), Skill.ARCANA) == 8
    
    def test_stealth_plus_7(self):
        """Dex 16 (+3), trained (+3), level 1 (+1) = +7."""
        assert skill_bonus(make_aetregan(), Skill.STEALTH) == 7
    
    def test_intimidation_untrained_plus_0(self):
        """Cha 10 (+0), untrained (+0) = +0."""
        assert skill_bonus(make_aetregan(), Skill.INTIMIDATION) == 0
    
    def test_deception_untrained_plus_0(self):
        """Cha 10 (+0), untrained (+0) = +0.
        
        Note: Deceptive Tactics feat lets Aetregan use Warfare Lore (+8)
        in place of Deception for Create a Diversion / Feint checks.
        The action evaluator (Pass 3c) handles the substitution.
        """
        assert skill_bonus(make_aetregan(), Skill.DECEPTION) == 0
    
    def test_athletics_untrained_plus_0(self):
        assert skill_bonus(make_aetregan(), Skill.ATHLETICS) == 0
    
    def test_unknown_lore_returns_untrained_bonus(self):
        """Lore not in character's list → untrained → Int mod only."""
        assert lore_bonus(make_aetregan(), "Underwater Basket Weaving") == 4
    
    def test_deceptive_tactics_flag_true(self):
        c = make_aetregan()
        assert c.has_deceptive_tactics is True
    
    def test_lengthy_diversion_flag_true(self):
        c = make_aetregan()
        assert c.has_lengthy_diversion is True
    
    def test_plant_banner_flag_false(self):
        """Aetregan doesn't have Plant Banner at L1 (planned for L2)."""
        c = make_aetregan()
        assert c.has_plant_banner is False


class TestSquadmateSkills:
    """Grounded defaults; verify against character sheets when available."""
    
    def test_rook_athletics_plus_8(self):
        """Rook Str 18 (+4), trained (+3), level 1 (+1) = +8."""
        assert skill_bonus(make_rook(), Skill.ATHLETICS) == 8
    
    def test_dalai_performance_plus_8(self):
        """Dalai Cha 18 (+4), trained (+3), level 1 (+1) = +8."""
        assert skill_bonus(make_dalai(), Skill.PERFORMANCE) == 8
    
    def test_erisen_crafting_plus_8(self):
        """Erisen Int 18 (+4), trained (+3), level 1 (+1) = +8."""
        assert skill_bonus(make_erisen(), Skill.CRAFTING) == 8


class TestUnsetSkill:
    def test_character_without_skill_returns_untrained(self):
        """Skill not in dict → UNTRAINED → just ability mod, no proficiency."""
        aetregan = make_aetregan()
        # MEDICINE not in her skill_proficiencies → untrained
        # Wis 12 (+1), untrained (+0) = +1
        assert skill_bonus(aetregan, Skill.MEDICINE) == 1
```

Create `tests/test_hp_extended.py` (extends `tests/test_hp.py` from CP4.5):

```python
"""Tests for HP data on all PCs (CP5.1 Pass 3a)."""

from pf2e.combat_math import max_hp
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


class TestAllPartyHP:
    def test_aetregan_15(self):
        assert max_hp(make_aetregan()) == 15
    
    def test_rook_23(self):
        """Automaton 10 + (Guardian 10 + Con +3) × 1 = 23."""
        assert max_hp(make_rook()) == 23
    
    def test_dalai_17(self):
        """Human 8 + (Bard 8 + Con +1) × 1 = 17."""
        assert max_hp(make_dalai()) == 17
    
    def test_erisen_16(self):
        """Elf 6 + (Inventor 8 + Con +2) × 1 = 16."""
        assert max_hp(make_erisen()) == 16
```

Create `tests/test_actions.py`:

```python
"""Tests for Action, ActionOutcome, ActionResult dataclasses (Pass 3a)."""

import pytest

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType


class TestActionConstruction:
    def test_stride_action(self):
        a = Action(
            type=ActionType.STRIDE,
            actor_name="Rook",
            action_cost=1,
            target_position=(5, 8),
        )
        assert a.type == ActionType.STRIDE
        assert a.actor_name == "Rook"
        assert a.target_position == (5, 8)
    
    def test_strike_action(self):
        a = Action(
            type=ActionType.STRIKE,
            actor_name="Aetregan",
            action_cost=1,
            target_name="Bandit1",
            weapon_name="Scorpion Whip",
        )
        assert a.target_name == "Bandit1"
        assert a.weapon_name == "Scorpion Whip"
    
    def test_action_is_frozen(self):
        a = Action(type=ActionType.END_TURN, actor_name="X", action_cost=0)
        with pytest.raises(Exception):
            a.actor_name = "Y"


class TestActionOutcome:
    def test_outcome_defaults(self):
        o = ActionOutcome(probability=1.0)
        assert o.hp_changes == {}
        assert o.conditions_applied == {}
    
    def test_outcome_damage(self):
        o = ActionOutcome(
            probability=0.5,
            hp_changes={"Bandit1": -8.5},
            description="Rook hits Bandit1 for 8.5 damage",
        )
        assert o.hp_changes == {"Bandit1": -8.5}
    
    def test_outcome_conditions(self):
        o = ActionOutcome(
            probability=0.6,
            conditions_applied={"Bandit1": ("off_guard",)},
        )
        assert "off_guard" in o.conditions_applied["Bandit1"]


class TestActionResult:
    def test_eligible_result(self):
        action = Action(type=ActionType.STRIDE, actor_name="Rook", action_cost=1)
        outcome = ActionOutcome(probability=1.0, description="Stride")
        r = ActionResult(action=action, outcomes=(outcome,))
        assert r.eligible
        assert r.verify_probability_sum()
    
    def test_ineligible_result(self):
        action = Action(
            type=ActionType.PLANT_BANNER, actor_name="Aetregan", action_cost=2,
        )
        r = ActionResult(
            action=action,
            outcomes=(),
            eligible=False,
            ineligibility_reason="Aetregan does not have Plant Banner feat",
        )
        assert not r.eligible
        assert "Plant Banner" in r.ineligibility_reason
        assert r.verify_probability_sum()  # 0 == 0 for ineligible
    
    def test_probability_sum_violation_detected(self):
        action = Action(type=ActionType.STRIDE, actor_name="X", action_cost=1)
        r = ActionResult(action=action, outcomes=(
            ActionOutcome(probability=0.3),
            ActionOutcome(probability=0.4),
        ))
        assert not r.verify_probability_sum()  # sums to 0.7
    
    def test_expected_damage_dealt(self):
        action = Action(type=ActionType.STRIKE, actor_name="Rook", action_cost=1)
        r = ActionResult(action=action, outcomes=(
            ActionOutcome(probability=0.5, hp_changes={"Bandit1": -10.0}),
            ActionOutcome(probability=0.5, hp_changes={}),
        ))
        assert r.expected_damage_dealt == pytest.approx(5.0)
```

Create `tests/test_combatant_extended.py`:

```python
"""Tests for CombatantState and EnemyState extensions (Pass 3a)."""

from pf2e.character import CombatantState, EnemyState
from pf2e.types import SaveType
from tests.fixtures import make_aetregan, make_rook_combat_state


class TestCombatantHP:
    def test_current_hp_defaults_to_none(self):
        state = CombatantState.from_character(make_aetregan())
        assert state.current_hp is None
    
    def test_effective_current_hp_with_none(self):
        """current_hp=None returns character's max_hp."""
        state = CombatantState.from_character(make_aetregan())
        assert state.effective_current_hp == 15  # Aetregan max
    
    def test_effective_current_hp_with_value(self):
        state = CombatantState.from_character(make_aetregan())
        state.current_hp = 8
        assert state.effective_current_hp == 8
    
    def test_temp_hp_default(self):
        state = CombatantState.from_character(make_aetregan())
        assert state.temp_hp == 0
    
    def test_actions_remaining_default(self):
        state = CombatantState.from_character(make_aetregan())
        assert state.actions_remaining == 3


class TestEnemyExtensions:
    def test_default_max_hp(self):
        e = EnemyState(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5),
        )
        assert e.max_hp == 20  # default
    
    def test_explicit_max_hp(self):
        e = EnemyState(
            name="Boss", ac=20,
            saves={SaveType.REFLEX: 8, SaveType.FORTITUDE: 10, SaveType.WILL: 5},
            position=(5, 5), max_hp=60,
        )
        assert e.max_hp == 60
    
    def test_effective_current_hp_with_none(self):
        e = EnemyState(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5), max_hp=20,
        )
        assert e.effective_current_hp == 20
    
    def test_perception_dc_derivation(self):
        e = EnemyState(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5), perception_bonus=4,
        )
        assert e.perception_dc == 14  # 10 + 4
    
    def test_actions_remaining_default(self):
        e = EnemyState(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5),
        )
        assert e.actions_remaining == 3
```

Create `tests/test_scenario_initiative.py`:

```python
"""Tests for scenario [initiative] section parsing (Pass 3a)."""

import pytest

from sim.scenario import ScenarioParseError, parse_scenario


BASE = """\
[grid]
. . . . .
. c g m .
. . . . .

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2
"""


class TestInitiativeSection:
    def test_no_section_defaults_to_seed_42(self):
        s = parse_scenario(BASE)
        assert s.initiative_seed == 42
        assert s.initiative_explicit == {}
    
    def test_seed_only(self):
        text = BASE + """
[initiative]
seed = 99
"""
        s = parse_scenario(text)
        assert s.initiative_seed == 99
        assert s.initiative_explicit == {}
    
    def test_explicit_ordering(self):
        text = BASE + """
[initiative]
Aetregan = 18
Bandit1 = 12
Rook = 10
"""
        s = parse_scenario(text)
        assert s.initiative_explicit == {
            "Aetregan": 18,
            "Bandit1": 12,
            "Rook": 10,
        }
    
    def test_invalid_seed_raises(self):
        text = BASE + """
[initiative]
seed = abc
"""
        with pytest.raises(ScenarioParseError, match="seed"):
            parse_scenario(text)
    
    def test_invalid_explicit_value_raises(self):
        text = BASE + """
[initiative]
Aetregan = notanumber
"""
        with pytest.raises(ScenarioParseError):
            parse_scenario(text)
```

### Step 12: CHANGELOG

Append to `CHANGELOG.md`:

```markdown
## [5.1-3a] - CP5.1 Pass 3a: Foundation

Foundation data model for the full-round turn evaluator. No algorithms,
no evaluators — only types, helpers, and data population. Algorithms
land in Pass 3b; action evaluators in Pass 3c.

### New types
- `Skill` enum with 16 standard skills; `SKILL_ABILITY` lookup table.
  (AoN: https://2e.aonprd.com/Skills.aspx)
- `ActionType` enum with 15 action types for CP5.1 scope.
- `Action`, `ActionOutcome`, `ActionResult` frozen dataclasses in
  new module `pf2e/actions.py`.

### Character extensions
- `Character.skill_proficiencies: dict[Skill, ProficiencyRank]`
- `Character.lores: dict[str, ProficiencyRank]`
- `Character.has_plant_banner` (False for Aetregan at L1; L2 upgrade)
- `Character.has_deceptive_tactics` (True for Aetregan)
- `Character.has_lengthy_diversion` (True for Aetregan)

### Helpers
- `skill_bonus(character, skill)` in `pf2e/combat_math.py`
- `lore_bonus(character, lore_name)` in `pf2e/combat_math.py`

### Character data population
- Aetregan: all 16 skills (10 trained, 6 untrained) and 2 lores (Warfare,
  Deity) from her Pathbuilder JSON.
- Rook: HP 23 (Automaton 10 + Guardian 10 + Con), skills grounded from
  Guardian + Automaton defaults.
- Dalai: HP 17 (Human 8 + Bard 8 + Con), skills grounded from Bard +
  Warrior Muse defaults.
- Erisen: HP 16 (Elf 6 + Inventor 8 + Con), skills grounded from
  Inventor + Munitions Master defaults.

Squadmate data is documented as "grounded defaults; verify against
character sheet when available."

### State extensions
- `CombatantState.current_hp: int | None` (None = full HP)
- `CombatantState.temp_hp: int = 0`
- `CombatantState.actions_remaining: int = 3`
- `CombatantState.effective_current_hp` property
- `EnemyState.max_hp: int = 20`, `current_hp: int | None`
- `EnemyState.perception_bonus: int = 4`, `perception_dc` property
- `EnemyState.actions_remaining: int = 3`
- `EnemyState.effective_current_hp` property

### Scenario parser
- `[initiative]` section supported. Optional seed-only mode or explicit
  ordering. Scenario stores `initiative_seed` and `initiative_explicit`;
  the actual rolling/sorting algorithm is Pass 3b work.

### Tests
Target ~30-40 new tests across:
- `tests/test_skills.py` (skill and lore bonus math)
- `tests/test_hp_extended.py` (HP for all 4 PCs)
- `tests/test_actions.py` (Action, ActionOutcome, ActionResult dataclasses)
- `tests/test_combatant_extended.py` (HP and actions_remaining fields)
- `tests/test_scenario_initiative.py` (initiative section parser)

### Deferred to Pass 3b
- `RoundState` with hybrid branching
- Beam search algorithm
- Adversarial enemy sub-search
- Damage pipeline
- Scoring function
- Initiative rolling/sorting from seed

### Deferred to Pass 3c
- Per-action evaluators (the 15 ActionTypes)
- Stride destination enumeration
- Output formatter
- `--debug-search` CLI flag
- End-to-end integration tests
```

Target test count after Pass 3a: ~235-245.

---

## Validation checklist

- [ ] Step 1: `Skill` enum with 16 members. `SKILL_ABILITY` lookup complete.
- [ ] Step 2: `Character` has `skill_proficiencies`, `lores`, `has_plant_banner`, `has_deceptive_tactics`, `has_lengthy_diversion`.
- [ ] Step 3: `skill_bonus()` and `lore_bonus()` work. Missing skill → UNTRAINED → just ability mod.
- [ ] Step 4: Aetregan has all 16 skill entries correctly set from JSON.
- [ ] Step 5: Rook HP 23, Dalai HP 17, Erisen HP 16. Each with documented grounded defaults.
- [ ] Step 6: `ActionType` enum with 15 members.
- [ ] Step 7: `Action`, `ActionOutcome`, `ActionResult` dataclasses work. Frozen. `verify_probability_sum()` detects violations.
- [ ] Step 8: `CombatantState.effective_current_hp` returns max_hp when current_hp is None.
- [ ] Step 9: `EnemyState.perception_dc = 10 + perception_bonus` derived correctly.
- [ ] Step 10: `[initiative]` section parsed; seed-only and explicit modes both work; invalid integers raise `ScenarioParseError`.
- [ ] Step 11: All new tests pass.
- [ ] **Full test suite passes** (existing + new). Target: ~235-245.
- [ ] **Strike Hard regression still holds** (EV 8.55) — nothing in Pass 3a changes combat math.
- [ ] Step 12: CHANGELOG updated.

## Common pitfalls

**`Character` is frozen, but mutable dict fields work with `default_factory`.** Python allows this — the dataclass prevents reassigning `character.skill_proficiencies` but doesn't prevent mutating the dict itself. By convention: never mutate skill_proficiencies, lores, or other dict fields after construction. Use `dataclasses.replace()` to produce a new Character if changes are needed.

**`Skill` import cycle risk.** `pf2e/types.py` defines `Skill`. `pf2e/character.py` uses it in type hints. `pf2e/combat_math.py` uses it in `skill_bonus`. Keep `Skill` in `types.py` (no imports from character/combat_math in types.py).

**`SKILL_ABILITY` lookup inside `skill_bonus`** — I put the import inside the function to avoid ordering issues. If the import order in types.py makes top-level imports clean, lift it.

**`perception_dc` is derived, not stored.** Do not add a `perception_dc` field to `EnemyState` — it's a property that returns `10 + perception_bonus`. If a test tries to construct `EnemyState(perception_dc=13)` it will fail. The correct construction is `EnemyState(perception_bonus=3)` which gives `perception_dc == 13`.

**Do not reset `actions_remaining` in `CombatantState.from_character()`.** Pass 3a's addition is that it defaults to 3. Pass 3b (the search algorithm) handles resetting per turn. For now, a fresh combatant state has 3 actions; code that wraps `from_character()` should not touch this field unless it knows what it's doing.

**Squadmate skill data is grounded-default, not authoritative.** Do not treat Rook's "Athletics TRAINED" as canonical PF2e accuracy — it's a reasonable assumption that the user will reconcile later. The docstrings say so. Do not add more skills "for realism" — stick to the list I specified.

**`[initiative]` explicit entries are name → initiative total, not name → modifier.** If a user writes `Aetregan = 18`, that means Aetregan's initiative total is 18, not that her Perception bonus is 18. Pass 3b's sorting algorithm will use this value directly.

**The `verify_probability_sum()` tolerance is 1e-6.** This catches floating-point drift. Tests that construct ActionResults with probabilities 0.1 + 0.2 + 0.3 + 0.4 will be fine (sum is 1.0 exactly). Tests with probability 1/3 repeated three times might fail the strict check — use 1e-4 if that's the intent.

## What comes after

1. You implement Pass 3a.
2. All tests pass (target ~235-245).
3. I review — same format as previous reviews.
4. We move to Pass 3b: the algorithms (search, state threading, scoring, damage pipeline).
5. Then Pass 3c: the action evaluators and integration.
6. CP5.1 complete. CP5.2 (class features) and CP5.3 (general skill actions) follow.
