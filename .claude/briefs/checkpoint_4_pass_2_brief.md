# Checkpoint 4 Pass 2: Corrections and Refinements

## Context

I independently verified the Phase A inventory against AoN. The agent's research is accurate. Plant Banner grants 4 temp HP at level 1 scaling every 4 levels, Guardian's Armor provides resistance 1+level//2 to physical damage, and Intercept Attack triggers on ally taking physical damage within 10 ft (15 ft for taunted enemies). The agent also correctly flagged that planted banner expands the aura to a 40-ft burst — a detail I missed in my preview.

The architectural plan is mostly approved. This Pass 2 brief covers one significant correction affecting existing checkpoints, plus several smaller refinements.

**Do NOT rewrite the whole plan.** Apply the corrections below and output a compact updated plan. Unchanged sections can be summarized as "unchanged from Pass 1."

## Corrections to Apply

### C.1 Planted banner expands aura to 40-ft burst — SIGNIFICANT CORRECTNESS FIX

Your Phase A research correctly surfaced this: "While your banner is planted, any effects that normally happen in an emanation around your banner instead happen in a burst that is 10 feet larger." A 30-ft emanation becomes a 40-ft burst. (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)

**This affects existing code.** `GridSpatialQueries.is_in_banner_aura()` currently checks `distance_ft(pos, banner) <= 30`, hardcoded regardless of banner state. This is wrong when the banner is planted — the check should use 40 ft.

Existing Checkpoint 1-3 tests still pass because all current scenarios have squadmates well within 30 ft. But the rule is wrong and will produce incorrect results for scenarios with wider spreads (e.g., Dalai at 35 ft from a planted banner should be in aura; currently would report out).

Required fix in Checkpoint 4:

1. **Update `GridSpatialQueries.is_in_banner_aura()`** to take banner-planted state into account:

```python
def is_in_banner_aura(self, name: str) -> bool:
    """True if combatant is within the banner aura.
    
    Base aura: 30-ft emanation. When the banner is planted (Plant Banner
    feat), the aura expands to a 40-ft burst.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — base aura)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796 — planted expansion)
    """
    if self._banner_pos is None:
        return False
    pos = self._positions.get(name)
    if pos is None:
        return False
    radius = 40 if self._banner_planted else 30
    return grid.distance_ft(pos, self._banner_pos) <= radius
```

2. **Add `banner_planted: bool` to `GridSpatialQueries.__init__`** and pass it from `TacticContext`. This is already in `TacticContext.banner_planted`, just needs to flow into the spatial queries constructor.

3. **Update `MockSpatialQueries`** tests if any rely on the 30-ft-only assumption. Quick scan of Checkpoint 1 test scenarios: all Rook/Dalai/Erisen positions are within 30 ft, so behavior is unchanged. But document this in a test comment so future changes don't silently break.

4. **Add a regression test** to `tests/test_grid_spatial.py`:

```python
def test_planted_banner_extends_aura_to_40ft(self):
    """A planted banner's aura reaches 40 ft, not 30 ft."""
    # Build a scenario with an ally at exactly 35 ft diagonal from banner
    # (5 diagonal squares = 5+10+5+10+5 = 35 ft)
    # Under 30-ft emanation: OUT
    # Under 40-ft burst: IN
    ...
```

Flag this fix in the CHANGELOG under "Correctness fixes."

### C.2 Rook has two separate reaction pools

Your architectural plan assumes Rook's guardian reaction (Intercept Attack) doesn't compete with his general reaction (tactic responses like Strike Hard). This is correct per AoN — the Guardian's "Ever Ready" technique grants an additional reaction that can only be used for guardian feats or class features.

Required: add tracking for Rook's guardian-specific reaction on `CombatantState`. The existing `reactions_available: int` and `drilled_reaction_available: bool` cover general and tactic-granted reactions. Add:

```python
# CombatantState additions
guardian_reaction_available: bool = False
```

Default `False`. Set to `True` for Rook specifically in `make_rook_combat_state()` (and in any future Guardian character factory). The Intercept Attack evaluator checks this flag independently of the general `reactions_available`.

Update the Phase B plan to reflect this: Intercept Attack consumes `guardian_reaction_available`, not `reactions_available`. They are tracked and decremented separately.

This lets Checkpoint 5's turn evaluator correctly count Rook as able to do BOTH a tactic response AND an Intercept Attack in the same round.

### C.3 Verify whether Aetregan's banner is attached to his whip

Plant Banner has a constraint I want verified before Pass 3: "If your banner is attached to a weapon, you cannot wield that weapon while your banner is planted."

Aetregan's current build has a whip as his equipped melee weapon. Where is his banner attached? Three options per AoN:

1. Attached to a weapon (like his whip) — then Plant Banner prevents whip use while planted
2. On a simple pole held in one hand — competes with shield use (Aetregan carries a steel shield)
3. Worn affixed to a pole alongside his backpack — no weapon interaction

Option 3 is the most flexible: Aetregan can wield whip AND steel shield AND plant banner without conflict. This is almost certainly the intended build.

For Pass 3:

- **Confirm Option 3** is Aetregan's banner attachment in `sim/party.py`. If not documented, add a comment clarifying the attachment method.
- If Option 1 (attached to whip), the Plant Banner evaluator must account for Aetregan losing whip access while planted. Not currently in scope but flag for future.

Request user confirmation if the answer isn't obvious from the existing character build.

### C.4 Intercept Attack requires Step-to-adjacency, which needs spatial validation

Your plan's Intercept Attack EV doesn't validate whether Rook can actually reach the triggering ally. The reaction says:

- Trigger: ally within 10 ft takes physical damage
- Effect: Rook Steps (5 ft) and must end adjacent to the ally
- Special: If triggered by Rook's taunted enemy, extends to 15 ft range and Stride instead of Step

Required: the Intercept Attack evaluator must check:

1. Ally is within 10 ft of Rook (or 15 ft if Rook's taunted enemy is attacking)
2. There exists an unoccupied square adjacent to the ally that Rook can Step to (5 ft Step, or Stride up to Rook's Speed for taunted case)

This is spatial validation similar to `can_reach_with_stride()` but with the target square constraint being "adjacent to ally" rather than "adjacent to enemy." Propose how to reuse or extend the existing BFS pathfinding for this check.

For Checkpoint 4, assume no taunted enemy (Taunt is Checkpoint 5 territory). Use the 10-ft trigger range and 5-ft Step constraint.

If Rook has no legal Step-to-adjacent position (e.g., all squares around the ally are occupied), Intercept Attack is ineligible. Model this case explicitly.

### C.5 Verify `map_penalty()` exists in the codebase

Your `expected_incoming_damage` sketch calls `map_penalty(attack_number, agile=False)`. I don't remember seeing this function in `pf2e/combat_math.py`. Before Pass 3 implementation, read the combat_math module and confirm:

- **Option A**: `map_penalty` already exists and takes these arguments → use as-is.
- **Option B**: A different helper exists that does this computation (e.g., inline MAP math in `expected_strike_damage`) → reuse whatever pattern is there.
- **Option C**: Neither exists → add a new `map_penalty(attack_number: int, weapon: Weapon | None = None) -> int` helper. Note that PF2e uses -5 for the second attack and -10 for the third, or -4/-8 for agile weapons.

Surface the finding in Pass 2 output. The implementation choice affects the Pass 3 brief.

### C.6 `expected_incoming_damage` should take `CombatantState`, not just `target_ac`

Your sketch is:

```python
def expected_incoming_damage(
    attacker: EnemyState, target_ac: int, attack_number: int = 1,
) -> float: ...
```

This prevents accounting for the target's:

- Raised shield (+2 AC circumstance bonus)
- Off-guard condition (-2 AC circumstance penalty)
- Other conditions (prone = -2 attack bonus for attacker)
- Guardian's Armor resistance (for Rook)

Better signature:

```python
def expected_incoming_damage(
    attacker: EnemyState,
    target: CombatantState,
    attack_number: int = 1,
) -> float:
    """Expected damage from one enemy Strike against a specific target.
    
    Accounts for target's effective AC (including raised shield, off-guard),
    target's damage resistances (Guardian's Armor for Guardians in medium/
    heavy armor), and attacker's MAP for the given attack number.
    """
    ac = armor_class(target)  # already accounts for raised shield, off-guard
    # Apply MAP
    ...
    # Compute base expected damage
    ...
    # Apply Guardian's Armor resistance if target is a Guardian in armor
    if _has_guardians_armor(target.character):
        resistance = guardians_armor_resistance(target.character.level)
        # Reduce expected damage per hit by resistance (but not below 0)
        ...
    return ev
```

Sketch the helper `_has_guardians_armor(character) -> bool` that checks whether the character has the Guardian class feature active (wearing medium/heavy armor). For our party, only Rook qualifies.

### C.7 Temp HP doesn't stack — use highest

PF2e's temp HP rule: "If you already have temporary Hit Points, compare the new temporary Hit Points to the ones you already have; you gain whichever amount is higher and lose the lower amount." (AoN: https://2e.aonprd.com/Rules.aspx?ID=2321)

Your `temp_hp_ev()` function treats temp HP as additive per tactic use. For Checkpoint 4's single-tactic evaluation that's fine (no stacking question comes up). But flag for Checkpoint 5's turn evaluator:

- If Aetregan plants the banner AND some other effect (say Hymn of Healing at higher levels) grants temp HP, allies get the highest, not the sum.
- For Plant Banner alone (our current case), allies get exactly 4 temp HP per round when banner is planted and they're in burst. No stacking concern.

Add a comment to `plant_banner_temp_hp()` noting this, but no functional change needed for Checkpoint 4.

### C.8 Minor: add `damage_prevented_sources` as a structured breakdown

Your proposal to add this dict is good. Clarify the keys. Propose a stable vocabulary:

```python
damage_prevented_sources: dict[str, float]
# Canonical keys:
#   "plant_banner_temp_hp"       — from Plant Banner feat
#   "guardians_armor_resistance" — from Rook's Guardian class feature
#   "intercept_attack_savings"   — from Rook using Intercept
#   "gather_reposition"          — from Gather to Me! pulling ally out of reach
#   "defensive_retreat_steps"    — from Defensive Retreat Steps out of reach
#   "shield_block"               — (Checkpoint 5)
#   "raise_shield_ac"            — (Checkpoint 5)
```

Using canonical keys makes Checkpoint 6's formatter easier to build — it can group by source and present a breakdown like:

```
Gather to Me! → defensive EV 15.5
  - 8.0 from banner temp HP (2 allies entering aura)
  - 7.5 from repositioning 1 ally out of goblin melee reach
```

## Confirmed as-is from Pass 1

- Phase A inventory: Plant Banner (IN SCOPE), Intercept Attack (IN SCOPE), Guardian's Armor (IN SCOPE), everything else either out of scope for C4 or deferred to C5+
- Enemy attack profile fields on EnemyState (attack_bonus, damage_dice, damage_bonus, num_attacks_per_turn)
- Scenario file format extension for enemy offensive stats (atk=, dmg=, dmg_bonus=, attacks=)
- Target selection heuristic: "attacks nearest reachable PC" for Checkpoint 4
- `plant_banner_temp_hp(level)` formula `4 * (1 + level // 4)` — verified correct
- `guardians_armor_resistance(level)` formula `1 + level // 2` — verified correct
- Conservative Intercept Attack EV model: saves `guardian_resistance` per intercept (1 at L1). The "preventing crits on squishy allies" value is real but unmodelable without HP tracking; floor model is acceptable.
- Gather to Me defensive evaluation: temp HP entry + damage prevented by leaving reach
- Defensive Retreat defensive evaluation: sum of prevented damage from 3 Steps away
- AoE friendly-fire deferred to Checkpoint 5
- Courageous Anthem defensive component (fear save +1) out of scope
- TacticResult `damage_prevented_sources` breakdown field
- Module structure: extend `pf2e/combat_math.py` and `pf2e/tactics.py`, no new modules
- Integration test scope (A-E)

## Open Questions for Pass 2 (resolved inline above)

- Q1 (enemy attack profile optional): YES, default empty = 0 defensive EV
- Q2 (reaction competition): RESOLVED via C.2 — separate pools
- Q3 (AoE friendly fire): DEFERRED to Checkpoint 5
- Q4 (temp HP renewal model): 4 temp HP per round per ally in aura, simplified
- Q5 (target selection): "nearest reachable PC" heuristic for Checkpoint 4
- Q6 (Guardian's Armor rounding): VERIFIED — `1 + level // 2` is correct Python math

## New Open Question for Pass 3

- How to model Intercept Attack's "which ally to protect" decision? For Checkpoint 4, propose: "intercept the attack on the ally with the lowest AC who is within 10 ft." Squishy targets (Dalai, Erisen) benefit most. Flag smarter target selection for Checkpoint 5.

## Output Format

Produce a compact Pass 2 plan with:

1. **Corrections applied** — C.1 through C.8 with updated values
2. **Updated Section 1** — EnemyState field additions (confirm)
3. **Updated Section 2 (expected_incoming_damage)** — new signature taking CombatantState, with resistance handling
4. **Updated Section 4 (Intercept Attack)** — spatial validation for Step-to-adjacency
5. **Updated Section 6 (Gather to Me)** — use aura-aware helpers (40 ft planted, 30 ft carried)
6. **New Section 13: Foundation changes** — `GridSpatialQueries.is_in_banner_aura` update, `CombatantState.guardian_reaction_available` field, banner_planted propagation
7. **Map penalty verification finding** — whether function exists and where
8. **Unchanged from Pass 1** — one-line summary

Aim for 3-4 pages. This is a meaningful update (aura fix, reaction pools, signature change) but still surgical.

Cite AoN URLs for every mechanical claim. Any remaining UNVERIFIED items must be flagged as blockers for Pass 3.

## What Happens Next

1. You produce this Pass 2 plan.
2. I review and confirm.
3. We move to Pass 3 implementation.
4. Code lands with tests passing, Checkpoint 4 closes.
5. We move to Checkpoint 5: turn evaluator (which will combine offensive + defensive EV across action sequences).
