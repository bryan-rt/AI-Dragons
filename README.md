# PF2e Tactical Combat Simulator

A Python CLI tool for evaluating Pathfinder 2e (Remaster) Commander tactic choices during combat encounters. Uses expected-value math to rank tactical options by net damage dealt/avoided.

## Project Status

**Foundation layer implemented** (Pass 2.5). The `pf2e/` package contains the rules engine: character data models, weapon/armor/shield representations, and all combat math derivation functions.

**Simulator layer pending** (Pass 3). The `sim/` package (grid parsing, tactic dispatch, turn evaluation, output formatting) will be built on top of this foundation.

## Module Structure

```
pf2e/
├── types.py           # Enums: Ability, ProficiencyRank, WeaponCategory, etc.
├── abilities.py       # AbilityScores dataclass + modifier computation
├── proficiency.py     # proficiency_bonus(rank, level) function
├── equipment.py       # Weapon, EquippedWeapon, WeaponRunes, Shield, ArmorData
├── character.py       # Character (immutable) + CombatantState (mutable)
└── combat_math.py     # All derivation functions (attack, damage, AC, saves, EV)

tests/
├── fixtures.py        # Party character factories (Aetregan, Rook, Dalai, Erisen)
├── test_abilities.py
├── test_proficiency.py
├── test_equipment.py
└── test_combat_math.py  # Validates all combat math against hand-derived targets
```

## Running Tests

```bash
pytest tests/ -v
```

Requires Python 3.10+ and pytest. No other dependencies.

## Design Principles

- **Derive, don't store.** All combat numbers (AC, attack bonus, damage, save bonuses, class DC) are computed from underlying character data at the moment they're needed.
- **Character is immutable.** `Character` is a frozen dataclass representing a build. Transient combat state (conditions, shield raised, reactions) lives on `CombatantState`.
- **Standard library only.** No third-party dependencies beyond pytest for tests.
