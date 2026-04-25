# CP5.2 — Pass 2 Brief: Corrections and Refinements

## Purpose

This brief applies corrections to the Pass 1 plan. Read Pass 1 alongside this
document. Where Pass 2 contradicts Pass 1, Pass 2 wins.

---

## Correction 1: Rallying Anthem / Inspire Defense — Deferred

Dalai does not have the Inspire Defense feat at L1. Rallying Anthem is not
available to her. Both are out of scope for CP5.2 entirely — no stub, no
ineligible evaluator, no ActionType entry.

**Revised scope: 4 features, not 5.**

- Dalai: ANTHEM, SOOTHE
- Erisen: MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH
- Rook: TAUNT, INTERCEPT_ATTACK extension

---

## Correction 2: Mortar Action Order — AIM → LOAD → LAUNCH

The Pass 1 brief said LOAD → AIM → FIRE. AoN says AIM → LOAD → LAUNCH.
The corrected state machine is:

```
(mortar_deployed) --[MORTAR_AIM]--> "mortar_aimed"
"mortar_aimed" --[MORTAR_LOAD]--> "mortar_aimed", "mortar_loaded"
"mortar_aimed", "mortar_loaded" --[MORTAR_LAUNCH]--> (mortar_deployed)
```

**Deploy assumption:** Auto-deploy at combat start for any character with
`has_light_mortar`. No MORTAR_DEPLOY action needed in CP5.2. Erisen's
`CombatantSnapshot` is initialized with `"mortar_deployed"` in her conditions
frozenset by `from_combatant_state()` when the character has `has_light_mortar`.

**Movement restriction:** Per AoN, no explicit movement restriction between AIM
and LOAD or LAUNCH. Removing the movement-clears-aimed rule from the Pass 1
design. The state machine persists cleanly within a turn.

**Cross-turn state:** Scenario file can pre-set mortar state via a new
`[combatant_state]` section (see Correction 4).

---

## Correction 3: Composition Conflict — Simplified

With Inspire Defense deferred, there is no composition conflict to model in
CP5.2. Anthem is the only composition Dalai has. No `active_composition` field
needed on `RoundState` for this checkpoint.

Add a comment in the ANTHEM evaluator:
```python
# Only one composition can be active at a time. Anthem is Dalai's only
# composition at L1. Composition conflict handling deferred to CP5.3+.
# (AoN: https://2e.aonprd.com/Traits.aspx — Composition)
```

---

## Correction 4: Scenario Parser — [combatant_state] Section

Add minimal support for pre-set mortar state. Format:

```ini
[combatant_state]
Erisen = mortar_deployed, mortar_aimed
```

Parser reads this section and sets the listed condition tags into the named
combatant's initial `conditions` frozenset at scenario load time. No other
combatant_state keys needed for CP5.2.

The section is optional — if absent, defaults apply (mortar auto-deployed via
`has_light_mortar` flag, nothing else pre-set).

---

## Confirmed: Design Question Resolutions

All design questions from Pass 1 are resolved as follows:

**Q1 — Rallying Anthem:** Deferred (see Correction 1).

**Q2 — STRIKE knowing Anthem is active mid-round:** Option A confirmed. Add
`_effective_status_bonus_attack(actor, state)` helper that returns
`max(actor.status_bonus_attack, 1 if state.anthem_active else 0)`. Same pattern
for damage: `_effective_status_bonus_damage(actor, state)`. Both helpers used
inside the existing STRIKE evaluator. Flag for CP6 multi-buff refactor.

**Q3 — Anthem state propagation:** Special-case in `apply_outcome_to_state`. If
`"anthem_active"` appears in `conditions_applied` for any actor, set
`state.anthem_active = True` via `replace()` on the RoundState. One-line
addition.

**Q4 — Composition conflict:** No conflict to model (see Correction 3).

**Q5 — Mortar deploy:** Auto-deploy confirmed (see Correction 2).

**Q6 — Mortar action order:** AIM → LOAD → LAUNCH confirmed (see Correction 2).

**Q7 — Soothe slot tracking:** `"soothe_used"` in Dalai's conditions frozenset.
One cast per encounter at L1. Evaluator checks this before marking eligible.

**Q8 — Scenario [combatant_state]:** Confirmed (see Correction 4).

**Q9 — Taunt + Intercept extension:** Confirmed. `evaluate_intercept_attack`
checks the attacking enemy's conditions for `"taunted_by_rook"`. If present,
extends range from 10 ft to 15 ft and allows Stride instead of Step to reach
the ally.

---

## Refined Feature Specifications

### Feature 1: ANTHEM

AoN: https://2e.aonprd.com/Spells.aspx — Courageous Anthem

- 1 action, 60-ft emanation, 1 round duration
- +1 status bonus to attack rolls, damage rolls, and saves vs fear for all
  allies in aura

**Eligibility:**
- `actor.character.has_courageous_anthem`
- `not state.anthem_active` (already active = no benefit to re-cast this turn)
- `actions_remaining >= 1`

**Score delta:**

```python
anthem_ev = 0.0
for ally_name, ally_snap in state.pcs.items():
    if ally_name == actor_name:
        continue
    if not spatial.is_within_distance(actor_pos, ally_pos, 60):
        continue
    remaining_strikes = min(ally_snap.actions_remaining, 2)
    hit_prob = _estimate_hit_probability(ally_snap, state)
    avg_dmg = _estimate_avg_damage(ally_snap)
    # +1 attack: 5% more hits × full damage
    # +1 damage: existing hit probability × 1 more damage per hit
    anthem_ev += remaining_strikes * (0.05 * avg_dmg + hit_prob * 1.0)
```

Flag `remaining_strikes` estimation as CP6 calibration target in docstring.

**State delta:** `conditions_applied = {actor_name: ("anthem_active",)}`.
`apply_outcome_to_state` picks this up and sets `state.anthem_active = True`.

**One outcome:** probability=1.0 (casting always succeeds for a cantrip).

### Feature 2: SOOTHE

AoN: https://2e.aonprd.com/Spells.aspx — Soothe

- 2 actions, 30-ft range, 1 willing creature
- Heals 1d10+4 HP at L1 (average 9.5)

**Eligibility:**
- `actor.character.has_soothe`
- `"soothe_used"` not in `actor_snap.conditions`
- `actor_snap.actions_remaining >= 2`
- At least one ally with `current_hp < max_hp` within 30 ft

**Score delta:**

```python
# For each eligible wounded ally, compute heal EV
avg_heal = 9.5  # die_average("d10") + 4
for ally_name, ally_snap in state.pcs.items():
    if ally_snap.current_hp >= ally_snap.max_hp:
        continue
    if not spatial.is_within_distance(actor_pos, ally_pos, 30):
        continue
    effective_heal = min(avg_heal, ally_snap.max_hp - ally_snap.current_hp)
    wound_factor = 1.0 + (1.0 - ally_snap.current_hp / ally_snap.max_hp)
    role_mult = 2.0 if ally_name == "Dalai Alpaca" else 1.0  # support role
    soothe_ev = effective_heal * wound_factor * role_mult
```

Target: the ally with highest soothe_ev. Generate one ActionOutcome for that
target. Flag role_mult hardcoding as CP6 refactor target (same non-decision as
existing Dalai drop_cost multiplier).

**State delta:**
- `hp_changes = {target_name: +9.5}`
- `conditions_applied = {actor_name: ("soothe_used",)}`

### Feature 3: MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH

AoN: https://2e.aonprd.com/Innovations.aspx?ID=4

**MORTAR_AIM:**
- Eligible: `"mortar_deployed"` in conditions, `not "mortar_aimed"` in conditions
- Requires valid target point with at least one enemy within 10-ft burst at
  120-ft range
- State delta: `conditions_applied = {actor_name: ("mortar_aimed",)}`
- Score delta: 0.0 (setup action — value realized at LAUNCH)
- Candidate generation: one AIM action per distinct enemy cluster within range

**MORTAR_LOAD:**
- Eligible: `"mortar_aimed"` in conditions, `not "mortar_loaded"` in conditions
- State delta: `conditions_applied = {actor_name: ("mortar_loaded",)}`
- Score delta: 0.0 (setup action)

**MORTAR_LAUNCH:**
- Eligible: `"mortar_aimed"` and `"mortar_loaded"` in conditions
- Calls `expected_aoe_damage()` from `combat_math.py`
- Constructs SiegeWeapon:
  ```python
  SiegeWeapon(
      name="Light Mortar",
      damage_die="d6",
      base_damage_dice=2,
      damage_type=DamageType.BLUDGEONING,
      save_type=SaveType.REFLEX,
      aoe_shape="burst",
      aoe_radius_ft=10,
      range_increment=120,
  )
  ```
- Score delta: `expected_aoe_damage(actor.character, mortar, enemy_targets)`
- State delta: clears `"mortar_aimed"` and `"mortar_loaded"` from conditions
- Kill branching: apply D14 threshold (5%) per enemy in burst
- MAP: MORTAR_LAUNCH has the attack trait — increments `map_count` by 1

**Note:** AIM and LOAD score 0.0 individually. The beam search must look ahead
3 actions deep to find the LAUNCH payoff. With beam depth=3 and K=50 at depth 1,
the full AIM → LOAD → LAUNCH sequence is within search range. Confirm this holds
when reviewing Pass 3 output.

### Feature 4: TAUNT

AoN: https://2e.aonprd.com/Actions.aspx?ID=3304

- 1 action, 30-ft range, automatic (no check required)

**Eligibility:**
- `actor.character.has_taunt`
- Target enemy within 30 ft and alive
- `actor_snap.actions_remaining >= 1`

**Score delta:**

```python
num_pcs_in_enemy_reach = max(1, _count_pcs_in_enemy_reach(enemy, state, spatial))
p_targets_ally = 1.0 - (1.0 / num_pcs_in_enemy_reach)
taunt_ev = p_targets_ally * (
    expected_enemy_damage * 0.05       # -1 circumstance ≈ 5% fewer hits
    + off_guard_ev_for_one_action      # off-guard until enemy's next turn
)
```

`off_guard_ev_for_one_action`: EV of off-guard against the enemy's remaining
attacks this round. Off-guard grants +2 to attack rolls against the enemy, so
EV ≈ num_remaining_attacks × 0.10 × ally_avg_damage_per_hit.

**State delta:**
- `conditions_applied = {enemy_name: ("taunted_by_rook",)}`
- `conditions_applied = {actor_name: ("taunting_" + enemy_name,)}`

One Taunt active at a time. If Rook already has a `"taunting_*"` condition,
TAUNT is ineligible for a new target.

### Feature 5: INTERCEPT_ATTACK Extension

Modify existing `evaluate_intercept_attack` in `pf2e/actions.py`:

```python
# Check if attacking enemy is Rook's taunted enemy
attacking_enemy_taunted = "taunted_by_rook" in attacking_enemy.conditions
intercept_range = 15 if attacking_enemy_taunted else 10
can_use_stride = attacking_enemy_taunted  # can Stride instead of Step

# Replace hardcoded 10-ft check:
if not spatial.is_within_distance(actor_pos, ally_pos, intercept_range):
    return ActionResult(action=action, eligible=False, ...)
```

No other changes to the INTERCEPT_ATTACK evaluator.

---

## New ActionType Entries (5, not 7)

```python
ANTHEM          = auto()
SOOTHE          = auto()
MORTAR_AIM      = auto()
MORTAR_LOAD     = auto()
MORTAR_LAUNCH   = auto()
TAUNT           = auto()
```

RALLYING_ANTHEM and MORTAR_DEPLOY are not added in this checkpoint.

---

## New Character Flags (4, not 5)

Add to `pf2e/character.py` and corresponding factory functions in `sim/party.py`:

```python
has_courageous_anthem: bool = False    # Dalai: True
has_soothe: bool = False               # Dalai: True
has_light_mortar: bool = False         # Erisen: True
has_taunt: bool = False                # Rook: True
```

---

## New STRIKE Helper Functions

Add to `pf2e/actions.py` (used inside existing STRIKE evaluator):

```python
def _effective_status_bonus_attack(actor: CombatantSnapshot, state: RoundState) -> int:
    """Return the effective status bonus to attack, accounting for mid-round Anthem.
    (AoN: https://2e.aonprd.com/Spells.aspx — Courageous Anthem)
    Flagged for CP6 multi-buff refactor.
    """
    return max(actor.status_bonus_attack, 1 if state.anthem_active else 0)

def _effective_status_bonus_damage(actor: CombatantSnapshot, state: RoundState) -> int:
    """Return the effective status bonus to damage, accounting for mid-round Anthem."""
    return max(actor.status_bonus_damage, 1 if state.anthem_active else 0)
```

Update STRIKE to call these instead of reading `actor.status_bonus_attack`
directly.

---

## Test Strategy

Expected range: 361 → 400–415 (40–55 new tests).

| Evaluator | Required tests |
|---|---|
| ANTHEM | Eligible for Dalai only; score_delta > 0 with allies in aura; score_delta = 0 with no allies in aura; ineligible if already active |
| SOOTHE | Eligible when ally below max HP; ineligible when soothe_used; ineligible when actions < 2; score scales with wound severity |
| MORTAR_AIM | Eligible when deployed, not aimed; ineligible when aimed |
| MORTAR_LOAD | Eligible when aimed, not loaded; ineligible when not aimed |
| MORTAR_LAUNCH | Eligible when aimed and loaded; score_delta matches expected_aoe_damage; clears aimed+loaded conditions |
| Mortar state machine | Full AIM → LOAD → LAUNCH sequence transitions correctly |
| TAUNT | Guardian only; -1 penalty EV applied; ineligible if already taunting |
| INTERCEPT_ATTACK ext. | 15-ft range when taunted enemy attacks; 10-ft range otherwise |
| STRIKE helpers | _effective_status_bonus_attack returns 1 when anthem active; 0 otherwise |
| Scenario parser | [combatant_state] section sets mortar conditions correctly |

Plus: Strike Hard EV 8.55 from disk (9th verification).

---

## Pass 3 Implementation Order

1. Add 6 new ActionType entries to `pf2e/types.py`
2. Add 4 new Character flags to `pf2e/character.py`
3. Update `sim/party.py` factory functions with new flags
4. Add mortar auto-deploy to `CombatantSnapshot` initialization
5. Add `[combatant_state]` section to scenario parser
6. Add `_effective_status_bonus_attack/damage` helpers; update STRIKE to use them
7. Add `apply_outcome_to_state` special case for `"anthem_active"` condition
8. Implement ANTHEM evaluator
9. Implement SOOTHE evaluator
10. Implement MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH evaluators
11. Implement TAUNT evaluator
12. Extend INTERCEPT_ATTACK for taunted-enemy range
13. Register all new evaluators in `_ACTION_EVALUATORS` dispatcher
14. Update `generate_candidates()` to generate new action types
15. Write tests
16. `pytest tests/ -v` — all tests pass
17. Strike Hard EV 8.55 (9th verification)
18. Run CLI against canonical scenario, confirm improved Dalai/Erisen output
19. CHANGELOG + current_state.md update

---

## Rules Citations

| Rule | URL | Status |
|---|---|---|
| Courageous Anthem | https://2e.aonprd.com/Spells.aspx — Courageous Anthem | Verified |
| Soothe | https://2e.aonprd.com/Spells.aspx — Soothe | Verified |
| Light Mortar innovation | https://2e.aonprd.com/Innovations.aspx?ID=4 | Verified |
| Taunt | https://2e.aonprd.com/Actions.aspx?ID=3304 | Verified |
| Intercept Attack | https://2e.aonprd.com/Actions.aspx?ID=3305 | Verified |
| Rallying Anthem / Inspire Defense | — | Deferred — Dalai L1 ineligible |