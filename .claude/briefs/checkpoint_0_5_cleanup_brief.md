# Checkpoint 0.5: Foundation Cleanup

## Context

Pass 2.5 produced a working PF2e rules engine with 90/90 tests passing. Code review surfaced four small issues to address before we move to Checkpoint 1 (Tactic Dispatcher). This is a focused cleanup task — no architectural changes, no new features.

**Standing rules for every brief from this point forward:**

1. **Verify rules against Archives of Nethys (https://2e.aonprd.com/) before stating them.** Use web search. Cite URLs. If a search fails, mark the claim UNVERIFIED and flag it for review.
2. **Cite AoN URLs in every docstring** for non-trivial mechanics.
3. **Read existing code before proposing changes.** Pull actual files; don't rely on memory.
4. **Surface discrepancies, don't silently fix them.** If math doesn't match the brief, flag it.
5. **Don't expand scope.** New ideas go into "open questions for next checkpoint."
6. **Test what you build.** New functions get tests; fixes get regression tests.

## Current state

The repo contains:
- `pf2e/types.py`, `abilities.py`, `proficiency.py`, `equipment.py`, `character.py`, `combat_math.py`
- `tests/fixtures.py`, `test_abilities.py`, `test_proficiency.py`, `test_equipment.py`, `test_combat_math.py`

All tests pass with `pytest tests/ -v`. Read `tests/fixtures.py` and `pf2e/equipment.py` before starting — those are the files most affected by this cleanup.

---

## Cleanup Tasks

### Task 1: Fix `Weapon.is_ranged` to correctly handle thrown weapons

**Current code (pf2e/equipment.py):**

```python
@property
def is_ranged(self) -> bool:
    return self.range_increment is not None and not self.is_thrown
```

**Bug:** This excludes thrown-trait weapons from being "ranged." But in PF2e, a thrown weapon IS a ranged weapon when thrown — see https://2e.aonprd.com/Traits.aspx?ID=195 ("You can throw this weapon as a ranged attack").

A javelin (range_increment=30, traits include "thrown_30") is genuinely a ranged weapon. The current code says is_ranged=False for it, which is wrong.

**Fix:** Make `is_ranged` purely based on whether the weapon has a range_increment:

```python
@property
def is_ranged(self) -> bool:
    """True if the weapon can be used at range (has a range increment).
    
    This includes both pure ranged weapons (bows, firearms) and 
    thrown-trait melee weapons that have a range increment.
    """
    return self.range_increment is not None
```

**Add test:** In `tests/test_equipment.py`, add a hypothetical javelin fixture and confirm `is_ranged=True`. Also confirm a longsword stays `is_ranged=False`.

**Verify against AoN:** Confirm the weapon traits page (https://2e.aonprd.com/Traits.aspx?ID=195) and the Weapons rules page (https://2e.aonprd.com/Rules.aspx?ID=2176) are consistent with this interpretation.

---

### Task 2: Clean up dagger range representation

**Current code (tests/fixtures.py):**

```python
DAGGER = Weapon(
    name="Dagger",
    ...
    range_increment=None,  # melee mode (can also be thrown, handled separately)
    traits=frozenset({"agile", "finesse", "thrown_10", "versatile_s"}),
    hands=1,
)
```

**Issue:** A dagger's actual PF2e stats include "Range 10 ft" as a property of the weapon itself (https://2e.aonprd.com/Weapons.aspx?ID=171). The agent's design hides this in the trait string `thrown_10`. This will be fragile when the simulator needs to compute "is the target within thrown range" — the code would have to parse the trait string.

**Fix:** Set `range_increment=10` on the dagger fixture (matching its actual PF2e Range entry). The dagger is now is_melee=False AND is_ranged=True (after Task 1's fix). The `thrown` parameter on attack/damage functions still controls whether you're throwing it for the current Strike.

But wait — this breaks the current handling. If `range_increment=10`, then `is_melee` returns False, but a dagger CAN be used in melee. We need a different way to represent "weapon usable in both modes."

**Recommended approach:** Add a property `is_melee_thrown` (a melee weapon that has the thrown trait) and treat thrown-melee weapons as melee by default but with the `thrown=True` parameter to switch modes.

Concretely:

```python
@property
def is_melee(self) -> bool:
    """True if this is fundamentally a melee weapon.
    
    A weapon is melee if either:
    - It has no range increment, OR
    - It has the thrown trait (thrown weapons are melee weapons that
      can ALSO be thrown — they're listed in the Melee Weapons table
      in the rules).
    
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
    """
    return self.range_increment is None or self.is_thrown

@property
def is_ranged(self) -> bool:
    """True if the weapon has a range increment (can attack at range)."""
    return self.range_increment is not None
```

This way:
- Longsword: range_increment=None, no thrown trait → is_melee=True, is_ranged=False ✓
- Javelin: range_increment=30, thrown trait → is_melee=True, is_ranged=True ✓
- Dagger: range_increment=10, thrown trait → is_melee=True, is_ranged=True ✓
- Longbow: range_increment=100, no thrown trait → is_melee=False, is_ranged=True ✓

The `thrown` parameter on attack/damage functions still controls whether the current Strike uses ranged or melee mechanics for a thrown-melee weapon.

**Update fixtures:** Change DAGGER's `range_increment` from `None` to `10`. Update any tests that rely on `is_melee` or `is_ranged` for the dagger to confirm the new behavior is correct.

**Update `attack_ability` and `damage_ability_mod`:** Verify the logic still works with the new `is_melee` definition. The thrown branch should still take priority over the melee branch when `thrown=True`.

**Verify against AoN:** Look at the dagger's actual stat block (https://2e.aonprd.com/Weapons.aspx?ID=171) and confirm Range 10 ft is listed as a property of the weapon.

---

### Task 3: Confirm Aetregan's Wisdom score

**Current state:** `tests/fixtures.py` shows Aetregan with `wis=11`. This produces:
- Wis modifier: `(11 - 10) // 2 = 0`
- Will save: 0 (Wis) + 5 (expert at level 1) = +5
- Perception: 0 + 3 (trained) = +3

**The user originally specified:** "I just changed my stats and dropped my +1 in CHA for +1 in WIS to help shore up my saves... so now I have a +4 in nature, religion, and survival."

The +4 to those skills implies Wis +1 (since trained at level 1 = +3, plus Wis +1 = +4). That requires **Wis 12, not Wis 11**.

In PF2e, attribute boosts work in increments: a boost from 10 takes you to 12, not 11. Going from 10 to 11 only happens via specific apex items at high level. The user's boost should have produced Wis 12.

**Fix:** Update `make_aetregan()` in `tests/fixtures.py` to use `wis=12`. Update the affected tests:
- `test_aetregan_saves`: Will save should be +6 (was +5)
- `test_aetregan_perception`: Perception should be +4 (was +3)
- Any other Wis-derived assertions

**Verify against AoN:** Confirm the attribute boost rules (https://2e.aonprd.com/Rules.aspx?ID=2275 — "Attribute Boosts") clarify that boosts from below 18 are +2 to the score.

If after research the agent finds a reason Wis 11 would be correct (e.g., partial boost rules I'm forgetting), flag it and don't make the change. Default assumption is Wis 12.

---

### Task 4: Document discoveries in a CHANGELOG

Create `CHANGELOG.md` at the repo root. Add an entry for Checkpoint 0.5 that captures what we learned during foundation development:

```markdown
# Changelog

## [0.5] - Foundation Cleanup

### Corrections from initial brief
- **Mortar EV per target**: 5.95, not 5.60 as originally stated.
  The boundary case `total ≤ DC-10` includes equality, so with 
  Erisen's mortar (DC 17) vs a Reflex +5 enemy, both rolls 1 AND 2
  produce critical failures (rolls 1+5=6 and 2+5=7, both ≤ 7).
  Brief originally undercounted to 1 crit fail; correct count is 2.
  
- **Save bonuses**: Several derivations in the brief were off by 1
  due to incorrect ability modifier assumptions:
  - Aetregan's Wis 11 → mod 0 (not +1 as the brief stated)
    [If Wis updated to 12 in Task 3, this entry becomes obsolete.]
  - Dalai's Reflex: Dex 14 + trained = +5 (brief said +6)
  - Dalai's Will: Wis 10 + expert = +5 (brief said +6)
  
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
- `Weapon.is_melee`: now correctly returns True for thrown-melee
  weapons (daggers can be used in melee).
- Dagger fixture: `range_increment` now set to 10 (matching the
  weapon's actual PF2e Range entry) instead of None.
- Aetregan Wis: corrected from 11 to 12. [If applicable.]
```

This CHANGELOG becomes the canonical record of "things that surprised us during development." Future checkpoints append to it.

---

## What NOT to do

- Do not refactor the architecture. The Pass 2 design is approved.
- Do not add new tactics. That's Checkpoint 1.
- Do not add grid logic. That's Checkpoint 2.
- Do not optimize the d20 enumeration loop (it's fine).
- Do not reorganize the tests file structure.

---

## Validation checklist before declaring done

- [ ] All 4 cleanup tasks addressed
- [ ] All existing tests still pass
- [ ] New tests added for: javelin (or other thrown ranged weapon) is_ranged behavior, dagger melee+ranged dual mode
- [ ] CHANGELOG.md exists at repo root with the Checkpoint 0.5 entry
- [ ] AoN URLs cited in the docstrings of any modified functions
- [ ] Any UNVERIFIED items surfaced for user review
- [ ] `pytest tests/ -v` returns 100% pass

If Wis is changed to 12 (Task 3), expect the test count to increase by 0 (existing tests just get updated values). If a javelin is added (Task 1), expect 2-3 new test cases.

---

## What happens next

After this lands and tests pass:

1. You push the cleaned-up code.
2. I review via the connector.
3. We start **Checkpoint 1: Tactic Representation and Dispatcher** with a Pass 1 architectural brief.

Checkpoint 1 will be the first "real" three-pass loop. Foundation is now stable enough that Checkpoint 1 can build on top of it without churn underneath.
