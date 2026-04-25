# CP5.2 — Pass 1 Brief: Class Features

## Context

This is a **Pass 1 architectural planning brief**. Do not write production code.
Read the existing codebase, research AoN rules, surface design questions and
conflicts, and report findings before proposing implementations.

**State at handoff:**

- 361+ tests passing (post-CP5.1.3c bugfix commit)
- Killer regression: Strike Hard EV 8.55 (8th verification)
- Single-round beam search working end-to-end
- CLI producing recommendations for full party

---

## Pre-Implementation Reading List

Read these files before writing anything:

```
pf2e/actions.py              — existing evaluators and dispatcher
pf2e/combat_math.py          — existing math helpers
pf2e/tactics.py              — TacticContext, TacticResult, evaluate_tactic()
pf2e/character.py            — Character fields and flags
pf2e/types.py                — Skill enum, ActionType enum
sim/round_state.py           — RoundState, CombatantSnapshot, EnemySnapshot
sim/search.py                — beam_search_turn(), simulate_round()
sim/candidates.py            — generate_candidates()
sim/party.py                 — make_dalai(), make_erisen(), make_rook()
sim/scenario.py              — Scenario, parse_scenario(), scenario file format
tests/test_evaluators.py     — existing evaluator tests
```

After reading, report:
- Whether Taunt has any existing implementation or stub in the codebase
- Whether `RoundState` or `CombatantSnapshot` has any mechanism for carrying
  state from a prior turn (for Light Mortar pre-load/pre-aim)
- What flags currently exist on `Character` for class features
  (e.g., `has_commander_banner`, `has_deceptive_tactics`)
- Whether `ActionType` enum already includes entries for the new actions
  (ANTHEM, INSPIRE_DEFENSE, SOOTHE, MORTAR_LOAD, MORTAR_AIM, MORTAR_FIRE, TAUNT)

---

## Scope

Deliver the following in this checkpoint:

1. **Dalai:** ANTHEM evaluator (Option B ripple EV), INSPIRE_DEFENSE evaluator,
   SOOTHE evaluator
2. **Erisen:** MORTAR_LOAD, MORTAR_AIM, MORTAR_FIRE evaluators with state
   persistence across the 3-action sequence
3. **Rook:** TAUNT evaluator, INTERCEPT_ATTACK full evaluator (if currently a stub)
4. New `ActionType` entries for all new actions
5. Tests for all new evaluators
6. Strike Hard EV 8.55 regression (9th verification)

**Out of scope:** Multi-round simulation, Aid action, Recall Knowledge, Seek,
Hide, Sneak (CP5.3).

---

## Feature 1: Dalai — Courageous Anthem (ANTHEM)

AoN lookup required: https://2e.aonprd.com/Spells.aspx — search "Courageous Anthem"
Confirm: exact aura range, exact bonus (+1 attack and +1 damage?), action cost
to cast/maintain, composition trait rules.

**Design (Option B — locked in, D21):**

Dalai spends 1 action to cast or maintain Anthem. The evaluator scores the
full-round ripple effect: the EV gain from +1 attack and +1 damage across all
expected ally strikes remaining this round.

```
anthem_ev = Σ_ally_in_aura Σ_expected_remaining_strikes (
    Δhit_probability × avg_damage + hit_probability × Δdamage
)
```

Where:
- `Δhit_probability ≈ 0.05` (+1 on d20 = 5% more hits)
- `Δdamage = +1` per hit
- `expected_remaining_strikes` = `floor(ally.actions_remaining / 1)` capped at 2
  (simplification — flag as CP6 calibration target)

**Aura:** Anthem is a composition with an aura. Confirm range on AoN. Allies
must be within range of Dalai to benefit.

**Composition rules:** A character can only maintain one composition at a time.
If Dalai casts Inspire Defense, Anthem ends, and vice versa. The evaluator must
check whether a composition is already active and model the tradeoff.

**Eligibility:** Dalai is a Bard. Check for `character_class == "Bard"` or a
new `has_courageous_anthem` flag on `Character`. Recommend the flag approach for
consistency with existing pattern (D18).

**Score delta:** `anthem_ev` as computed above.

**State delta:** `{"anthem_active": True, "anthem_caster": "Dalai Alpaca"}` —
this condition propagates to ally snapshots so STRIKE evaluators can apply the
+1 bonus when scoring.

**Design question for Pass 2:** How does the STRIKE evaluator know Anthem is
active? Two options:
- A: STRIKE reads `state.anthem_active` and adjusts its bonus inline
- B: Anthem applies a persistent modifier to `CombatantSnapshot.attack_bonus`
  when it activates, so STRIKE picks it up automatically

Option A is simpler. Option B is more correct for multi-buff scenarios (CP6).
Recommend A for CP5.2 and flag for CP6 refactor. Surface as design question.

---

## Feature 2: Dalai — Inspire Defense (INSPIRE_DEFENSE)

AoN lookup required: https://2e.aonprd.com/Spells.aspx — search "Inspire Defense"
Confirm: exact bonus (saving throw bonus? AC bonus?), aura range, action cost,
composition trait.

**Design:** Same Option B pattern as Anthem. Dalai spends 1 action. Evaluator
scores ripple EV of the defensive bonus across all allies in aura for the
remainder of the round.

```
inspire_defense_ev = Σ_ally_in_aura (
    expected_incoming_damage(ally) × Δmitigation_probability
)
```

Where `Δmitigation_probability` is derived from the specific bonus (confirm on
AoN — likely +1 to AC or saves).

**Composition conflict:** Casting Inspire Defense ends Anthem (and vice versa).
The evaluator must score both compositions and recommend the higher-EV option.
The `ACTIVATE_COMPOSITION` action type could wrap both — surface as design
question.

**Eligibility:** Flag `has_inspire_defense` on `Character`. Set `True` for Dalai.

---

## Feature 3: Dalai — Soothe (SOOTHE)

AoN lookup required: https://2e.aonprd.com/Spells.aspx — search "Soothe"
Confirm: healing amount, action cost, range, whether it requires a spell slot
at L1, target restrictions.

**Design:** Dalai spends actions to cast Soothe on a wounded ally. Score delta
= EV of healing, weighted by the drop_cost risk of the target.

```
soothe_ev = healing_amount × (1 - target.current_hp / target.max_hp)
            × role_multiplier(target)
```

Where `role_multiplier` is the same support-role weight used in drop_cost scoring
(Dalai = 2x, others = 1x per D12).

**Eligibility:** Target must be a living ally with `current_hp < max_hp`. Dalai
must have spell slots remaining (for CP5.2, assume 1 Soothe slot per round —
track with a `spell_slots_remaining` field or a `"soothe_used"` condition flag).

**Design question for Pass 2:** Spell slot tracking. Two options:
- A: Add `soothe_slots: int` to `CombatantSnapshot` (hardcoded for Dalai at L1)
- B: Use `"soothe_used"` in the `conditions` frozenset

Option B is consistent with the existing conditions pattern. Recommend B.

---

## Feature 4: Erisen — Light Mortar (MORTAR_LOAD, MORTAR_AIM, MORTAR_FIRE)

AoN lookup required: https://2e.aonprd.com/Innovations.aspx?ID=4
Confirm: exact action costs for each step, exact damage (2d6 bludgeoning per
CHARACTERS.md), save type (Reflex vs class DC per CHARACTERS.md), burst size
(10-ft), range (120-ft), exact conditions on aim/fire (no movement, target
stationarity).

**The state persistence problem:**

The mortar requires 3 sequential actions: LOAD → AIM → FIRE. These can span
turns. This creates a state problem the simulator hasn't faced before — carry-
over state from a prior turn.

Two cases for single-round simulation:

**Case A — All 3 actions in one turn:**
Erisen uses all 3 actions (LOAD, AIM, FIRE) in sequence on her single turn.
This is the common case. No cross-turn state needed.

**Case B — Pre-loaded/pre-aimed from prior round:**
Scenario file encodes that Erisen entered this round with the mortar already
loaded or aimed. She can skip LOAD and/or AIM and go straight to AIM or FIRE.

For CP5.2, implement both cases. Case B requires a scenario file extension:

```ini
[combatant_state]
erisen_mortar = loaded        # or "aimed" or "ready" (loaded+aimed)
```

This sets an initial condition on Erisen's `CombatantSnapshot.conditions`
frozenset: `"mortar_loaded"` and/or `"mortar_aimed"`.

**State machine:**

```
(none) --[MORTAR_LOAD]--> "mortar_loaded"
"mortar_loaded" --[MORTAR_AIM]--> "mortar_aimed"
"mortar_aimed" --[MORTAR_FIRE]--> (none) + AoE damage applied
```

Movement constraint: if Erisen moves after AIM (STRIDE or STEP), `"mortar_aimed"`
is cleared. Apply this in `apply_outcome_to_state` — any movement action clears
`"mortar_aimed"`. MORTAR_FIRE eligibility checks `"mortar_aimed"` in conditions.

Target stationarity constraint: if the target moves after AIM, FIRE is
ineligible against that target. For CP5.2 simplification: assume targets don't
move after being aimed at (single-round, enemy moves before Erisen in most
initiative orders). Flag as CP6 edge case.

**MORTAR_FIRE evaluator:**

Uses existing `expected_aoe_damage()` and `siege_save_dc()` from `combat_math.py`
(already implemented per ARCHITECTURE.md). Confirm these functions exist and
their signatures before writing the evaluator.

Score delta = `expected_aoe_damage(enemies_in_burst, save_dc, damage_dice)`.

Kill branching applies if P(kill) >= 5% for any enemy in burst (D14).

**Eligibility summary:**
- MORTAR_LOAD: `"mortar_loaded"` not in conditions, Erisen has `has_light_mortar`
- MORTAR_AIM: `"mortar_loaded"` in conditions, valid target in range
- MORTAR_FIRE: `"mortar_aimed"` in conditions, target hasn't moved

---

## Feature 5: Rook — Taunt (TAUNT)

AoN lookup required: https://2e.aonprd.com/Classes.aspx?ID=67 — Guardian, Taunt
Confirm: exact action cost, range (30 ft per CHARACTERS.md), exact mechanical
effect (-1 circumstance to attacks/DCs against allies, off-guard until next turn
if attacking ally), duration, whether it requires a check or is automatic.

**Design:** Rook spends 1 action to Taunt an enemy within 30 ft. Effect: if the
taunted enemy takes a hostile action that includes an ally but not Rook, they
take -1 circumstance penalty to attacks/DCs and become off-guard until their
next turn.

Score delta: EV of the penalty × expected enemy actions targeting allies this
round. This requires estimating whether the enemy will target allies or Rook.
For CP5.2 simplification: assume enemy targets the lowest-HP ally (consistent
with the adversarial sub-search behavior). If that target is not Rook, Taunt
provides its full penalty.

```
taunt_ev = P(enemy_targets_ally) × (
    expected_enemy_damage × Δhit_probability_from_penalty
    + EV_of_off_guard_for_one_action
)
```

Where `Δhit_probability_from_penalty ≈ 0.05` (-1 on d20 = 5% fewer hits).

**Eligibility:** `character_class == "Guardian"` (or `has_taunt` flag). One
Taunt active at a time per Rook — the `"taunted_enemy"` condition tracks which
enemy is currently taunted.

**State delta:** `{"taunted_enemy": enemy_name}` on Rook's snapshot.
`{"taunted_by": "Rook"}` on the enemy snapshot (for INTERCEPT_ATTACK's 15-ft
extension rule).

**INTERCEPT_ATTACK interaction:** Per AoN, Rook can intercept attacks from his
taunted enemy from up to 15 ft (instead of the normal 10 ft). The INTERCEPT_ATTACK
evaluator should check `"taunted_by"` on the enemy to apply the extended range.
Confirm whether INTERCEPT_ATTACK is currently a stub or fully implemented by
reading the codebase.

---

## New ActionType Entries Required

The agent must confirm which of these are already in `pf2e/types.py` and add
any that are missing:

```python
ANTHEM              # Dalai composition
INSPIRE_DEFENSE     # Dalai composition
SOOTHE              # Dalai spell
MORTAR_LOAD         # Erisen siege weapon
MORTAR_AIM          # Erisen siege weapon
MORTAR_FIRE         # Erisen siege weapon
TAUNT               # Rook class feature
```

---

## New Character Flags Required

The agent must confirm which of these are already on `Character` and add missing
ones to `pf2e/character.py` and the relevant factory functions in `sim/party.py`:

```python
has_courageous_anthem: bool = False    # Dalai: True
has_inspire_defense: bool = False      # Dalai: True
has_soothe: bool = False               # Dalai: True
has_light_mortar: bool = False         # Erisen: True
has_taunt: bool = False                # Rook: True
```

---

## Test Strategy

Expected range: 361 → 400–420 (40–60 new tests).

| Evaluator | Required tests |
|---|---|
| ANTHEM | Eligible for Dalai only; score_delta > 0 with allies in aura; score_delta = 0 with no allies in aura; Anthem ends when Inspire Defense cast |
| INSPIRE_DEFENSE | Same pattern as Anthem; composition conflict |
| SOOTHE | Eligible only when ally below max HP; score scales with wound severity; ineligible when slot used |
| MORTAR_LOAD | Eligible when not loaded; ineligible when loaded |
| MORTAR_AIM | Eligible only when loaded and target in range |
| MORTAR_FIRE | Eligible only when aimed; clears on movement; AoE damage correct |
| MORTAR state | Movement clears aimed state; 3-action sequence produces correct state transitions |
| TAUNT | Guardian only; -1 penalty applied to enemy; off-guard on ally-targeting; taunted_enemy condition set |
| INTERCEPT_ATTACK | Extended 15-ft range when taunted enemy attacks |

Plus: Strike Hard EV 8.55 from disk (9th verification).

---

## Design Questions to Surface After Reading

After reading the codebase, report on these before proposing implementations:

1. Does Taunt have any existing implementation or stub?
2. Do `expected_aoe_damage()` and `siege_save_dc()` exist in `combat_math.py`
   with usable signatures?
3. Is `INTERCEPT_ATTACK` fully implemented or a stub?
4. Does `RoundState` have any existing cross-turn state mechanism, or is the
   `conditions` frozenset the only carry-over vehicle?
5. Does the scenario file parser support a `[combatant_state]` section for
   pre-loaded mortar state? If not, what is the least-invasive extension?
6. How should composition conflicts (Anthem vs Inspire Defense) be modeled —
   shared `active_composition` field on Dalai's snapshot, or a condition tag?

Surface each as a design question with a recommendation.

---

## AoN Lookups Required (Agent Must Verify)

The agent must look up and verify these before finalizing the plan. Mark each
VERIFIED or flag discrepancies:

| Rule | URL |
|---|---|
| Courageous Anthem | https://2e.aonprd.com/Spells.aspx — search Courageous Anthem |
| Inspire Defense | https://2e.aonprd.com/Spells.aspx — search Inspire Defense |
| Soothe | https://2e.aonprd.com/Spells.aspx — search Soothe |
| Light Mortar (Inventor innovation) | https://2e.aonprd.com/Innovations.aspx?ID=4 |
| Taunt (Guardian class feature) | https://2e.aonprd.com/Classes.aspx?ID=67 |
| Intercept Attack (extended range with Taunt) | https://2e.aonprd.com/Actions.aspx?ID=3305 |
| Composition trait rules | https://2e.aonprd.com/Traits.aspx — search Composition |