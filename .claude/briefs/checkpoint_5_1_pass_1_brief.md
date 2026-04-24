# Checkpoint 5.1 Pass 1: Full-Round Turn Evaluator — Architecture

## Goal

Build a full-round combat simulator that takes a scenario and produces a recommendation for the best sequence of actions for every PC in initiative order, accounting for enemy responses, with the objective of maximizing expected combat victory probability.

The output is: "Here's what your party should do this round, turn by turn, with justifications."

## Scope (CP5.1)

This is the foundational checkpoint for the turn evaluator. It establishes:
- Architecture for the search algorithm
- Data model for HP, skills, actions, round state
- Core action set: ~16 action types (below)
- Scoring function for party preservation weighted with enemy kills
- Beam search with bounded depth and state threading
- Damage composition pipeline (strict PF2e rules order)

CP5.2 adds class features (Dalai's compositions/spells, Erisen's mortar, Rook's Intercept/Taunt, etc.).
CP5.3 adds general skill actions (Aid, Recall Knowledge, more skill feat variants).

### Core actions in CP5.1

| Action | Cost | Who | Notes |
|---|---|---|---|
| Stride | 1 | All | Movement up to Speed |
| Step | 1 | All | 5-ft move, no AoO |
| Strike (melee/ranged/thrown) | 1 | All with weapon | With MAP tracking |
| Raise Shield | 1 | Shield wielders | +2 AC to start of next turn |
| End Turn | 0 | All | Forfeit remaining actions |
| Plant Banner | 2 | Aetregan (L2+) | Stub for now — she'll have it at L2 |
| Activate Strike Hard! | 2 | Aetregan | Existing evaluator |
| Activate Gather to Me! | 1 | Aetregan | Existing evaluator |
| Activate Tactical Takedown | 2 | Aetregan | Existing evaluator |
| Activate Mountaineering Training | 1 | Aetregan | Existing evaluator |
| Shield Block | R | Shield wielders | Reaction, composed into damage pipeline |
| Demoralize | 1 | All with Int (even untrained) | Intimidation check; Aetregan untrained = bad |
| Taunt | 1 | Rook | Guardian class feature |
| Create a Diversion | 1 | All with Deception | Aetregan uses Warfare Lore via Deceptive Tactics |
| Feint | 1 | All with Deception | Aetregan uses Warfare Lore via Deceptive Tactics |
| Trip | 1 | Whip, Athletics, or weapon w/ Trip trait | Aetregan uses Scorpion Whip |
| Disarm | 1 | Whip, Athletics, or weapon w/ Disarm trait | Aetregan uses Scorpion Whip |

## Architectural pillars

These are the eight big design decisions we reached during scoping. Each has rationale.

### 1. Full-round evaluation with per-turn beam search

The evaluator simulates an entire combat round from initiative position 1 to N. Each character's turn is optimized independently via beam search (K=50/20/10, depth 3). State threads forward between turns.

**Rationale:** Full joint optimization across all characters' turns is computationally infeasible. Per-turn beam search is how chess engines work — optimize current position assuming reasonable play continues. For our branching factor and turn structure, this is tractable (seconds per round) and near-optimal.

### 2. Party-preservation weighted scoring with kill/drop discontinuities

The scoring function is:

```
score = Σ_enemy P(killed) × kill_value(enemy)
      − Σ_pc P(dropped) × drop_cost(pc)
      + damage_dealt_EV
      − 0.5 × damage_taken_EV

where:
  kill_value(enemy) = enemy.max_hp + 20 × enemy.num_attacks_per_turn
  drop_cost(pc) = pc.max_hp + 20 × pc.support_multiplier
  support_multiplier = 2 for Dalai (Anthem buff), 1 for others
```

**Rationale:** "Probability of combat victory" is the gold-standard objective. We can't compute it exactly without multi-round simulation, so we use a single-round proxy: kills end combat (weighted high), drops lose combat (weighted high), damage is intermediate currency. Threat-weighted kills and support-weighted drops capture that "kill the boss" > "kill a minion" and "save the Bard" > "save the tanky Guardian."

### 3. Outcome-bucket damage distributions

Each Strike produces three outcome buckets: `miss` (probability m, damage 0), `hit` (probability h, expected damage d_hit), `crit` (probability c, expected damage 2 × d_hit). Multi-Strike turns compose as probability trees with low-probability pruning.

**Rationale:** Captures the "crit changes the kill outcome" variance without the compute cost of full damage PMFs. PF2e damage is severely non-Gaussian (bimodal: miss-spike at 0 and hit/crit spikes at 7-14), so normal approximation would be wrong at the tails (where P(kill) lives). Outcome buckets preserve the shape where it matters.

### 4. Hybrid state threading (expectimax at kill/drop, EV collapse elsewhere)

Between actions in the search tree:
- If an action's outcome could cross a kill or drop threshold: branch the tree into "crosses" and "doesn't cross" worlds, weighted by probability. Evaluate subsequent actions in each world.
- Otherwise: use EV-collapsed state (expected HP remaining).

**Rationale:** Kill/drop events fundamentally change what subsequent actions can do (can't attack a dead enemy, Bard dropping loses Anthem for the rest of the turn). A 4-damage vs 9-damage hit doesn't change much. Branching only at the critical transitions keeps the search tree to ~4-16 branches per sequence instead of 10^6+.

### 5. Strict PF2e damage composition pipeline

Each incoming Strike resolves in the order the rules specify:
1. **Attack roll**: attacker bonus + d20 vs target's effective AC (with Raise Shield, off-guard, frightened applied)
2. **Damage roll** (on hit/crit): compute damage with modifiers
3. **Reaction phase**:
   - **Intercept Attack** (Rook) — if eligible, redirect attack to Rook; restart resolution with Rook as target
   - **Shield Block** — if eligible, absorb damage up to shield hardness
4. **Resistance**: apply Guardian's Armor (physical damage) or other resistances
5. **Temp HP**: absorb remaining damage against temp HP pool before HP

**Rationale:** Correctness. Each mitigation source has a defined place in the sequence. Independent attribution or priority cascade would double-count or miss edge cases. The ~200-line pipeline is worth it.

### 6. Adversarial enemies with single-best-response

During PC-turn evaluation, when the search tree imagines "what will the enemy do next turn?", it computes the enemy's single best action sequence (K=20, depth 3) against the current PC strategy. Enemies don't also search over *multiple* hypothetical PC strategies.

**Rationale:** Full two-sided minimax with uncertainty over both sides' strategies is exponentially expensive. Single-best-response captures most of the adversarial signal ("enemies will focus fire the weakest target") without blowing up compute. Future upgrade (CP6): expectimax over enemy's top-3 plans.

### 7. Initiative from Perception, fixed at scenario load

Each PC and enemy rolls Perception at scenario load (seeded for reproducibility). Turn order is fixed for the round. Scenario file can override with explicit ordering if needed.

**Rationale:** Standard PF2e rule. Fixed order makes the simulation deterministic and debuggable. Random initiative per run would fight our desire for regression tests.

### 8. Kitchen-sink scoping, staged over 5.1/5.2/5.3

CP5.1 implements the 16 core actions listed above. CP5.2 adds class features. CP5.3 adds more skill actions. Each substage is validated independently before moving on.

**Rationale:** "Kitchen sink" is the endpoint, not the starting point. Staged delivery lets us validate architecture early and catch issues before they compound.

## Data model additions

### Character extensions

```python
@dataclass(frozen=True)
class Character:
    # ... existing fields ...
    
    # HP (added in CP4.5)
    ancestry_hp: int = 0
    class_hp: int = 0
    
    # NEW in CP5.1: Skill proficiencies
    skill_proficiencies: dict[Skill, ProficiencyRank] = field(default_factory=dict)
    # Lores tracked separately — each lore is a specific trained skill
    lores: dict[str, ProficiencyRank] = field(default_factory=dict)
    # Class-specific feature flags
    has_plant_banner: bool = False   # Aetregan at L2, not L1
    has_deceptive_tactics: bool = False  # Aetregan: True
    has_lengthy_diversion: bool = False  # Aetregan: True
```

The `Skill` enum enumerates all PF2e skills (Acrobatics, Arcana, Athletics, Crafting, Deception, Diplomacy, Intimidation, Medicine, Nature, Occultism, Performance, Religion, Society, Stealth, Survival, Thievery).

Lores are string-keyed because players can have any lore (Warfare Lore, Deity Lore, Alkenstar Lore, etc.).

### CombatantState extensions

```python
@dataclass
class CombatantState:
    # ... existing fields ...
    
    # NEW in CP5.1: HP tracking
    current_hp: int | None = None  # None = full (computed from max_hp)
    temp_hp: int = 0
    
    # Reaction pool (already had reactions_available from CP1)
    # Clarification: drilled_reaction_available = Commander feature, renews each round
    # guardian_reactions_available = Guardian feature, renews each round
    
    # Action economy for the current turn
    actions_remaining: int = 3  # resets at start of each turn
```

HP defaults to `None` meaning "full HP" computed from character's max_hp. Scenario override can set an explicit `current_hp` value for "wounded" scenarios.

### EnemyState extensions

```python
@dataclass
class EnemyState:
    # ... existing fields ...
    
    # NEW in CP5.1: HP tracking
    max_hp: int = 20  # default plausible L1 bandit; scenario override required for bosses
    current_hp: int | None = None
    
    # NEW in CP5.1: Skill proficiencies (for Create a Diversion / Feint target DCs)
    perception_dc: int = 13  # 10 + Perception bonus
    
    # Action economy
    actions_remaining: int = 3
```

### New types

```python
# pf2e/actions.py (new module)

class ActionType(Enum):
    STRIDE = auto()
    STEP = auto()
    STRIKE = auto()
    RAISE_SHIELD = auto()
    END_TURN = auto()
    PLANT_BANNER = auto()
    ACTIVATE_TACTIC = auto()
    SHIELD_BLOCK = auto()  # reaction
    DEMORALIZE = auto()
    TAUNT = auto()
    CREATE_A_DIVERSION = auto()
    FEINT = auto()
    TRIP = auto()
    DISARM = auto()

@dataclass(frozen=True)
class Action:
    type: ActionType
    actor_name: str
    action_cost: int
    target_name: str = ""  # e.g., enemy name for Strike, ally name for Aid
    target_position: tuple[int, int] | None = None  # e.g., Stride destination
    weapon_name: str = ""  # for Strike variants
    tactic_name: str = ""  # for ACTIVATE_TACTIC
    # More specialized fields as needed
```

Actions are frozen dataclasses that are fully self-describing. The evaluator never uses unstructured dicts.

```python
@dataclass(frozen=True)
class ActionOutcome:
    """One branch of an action's probability tree."""
    probability: float
    # State changes this branch applies
    hp_changes: dict[str, float]  # combatant_name -> delta (negative = damage)
    position_changes: dict[str, tuple[int, int]]
    conditions_applied: dict[str, list[str]]  # combatant_name -> ["prone", "off_guard"]
    conditions_removed: dict[str, list[str]]
    reactions_consumed: dict[str, int]  # combatant_name -> count
    # Summary
    description: str  # for debug output

@dataclass(frozen=True)
class ActionResult:
    action: Action
    outcomes: list[ActionOutcome]  # sum of probabilities = 1.0
    
    @property
    def expected_damage_dealt(self) -> float:
        return sum(
            o.probability * -sum(min(0, delta) for delta in o.hp_changes.values())
            for o in self.outcomes
        )
    # ... similar properties for dealt/taken/conditions
```

```python
# sim/round_state.py (new module)

@dataclass
class RoundState:
    """State of combat at a given instant.
    
    Mutable — modified by the search as actions are hypothetically applied.
    Clone before branching.
    """
    scenario: Scenario
    commander: CombatantState
    squadmates: list[CombatantState]
    enemies: list[EnemyState]
    initiative_order: list[str]  # list of combatant names
    current_turn_idx: int  # index into initiative_order
    round_number: int
    # Per-combatant tracking
    hp_state: dict[str, float]  # combatant_name -> current HP (float for EV-collapse)
    condition_state: dict[str, set[str]]  # combatant_name -> {"off_guard", "prone"}
    reaction_pool: dict[str, int]  # combatant_name -> reactions left
    shield_state: dict[str, ShieldStatus]  # combatant_name -> shield info
    # Hybrid state threading metadata
    is_branch: bool = False  # True if this state is inside a kill/drop branch
    branch_probability: float = 1.0  # Probability of this branch being "real"
    
    def clone(self) -> "RoundState":
        """Deep clone for branching."""
        ...
    
    def apply_action(self, action: Action, outcome: ActionOutcome) -> "RoundState":
        """Return a new state with the outcome applied."""
        ...
```

```python
# sim/search.py (new module)

@dataclass
class SearchConfig:
    beam_k_depths: tuple[int, int, int] = (50, 20, 10)  # K at depth 1, 2, 3
    max_depth: int = 3
    low_prob_prune_threshold: float = 0.001
    kill_drop_branch_threshold: float = 0.05  # min probability to branch at
    debug: bool = False

@dataclass(frozen=True)
class TurnRecommendation:
    character_name: str
    action_sequence: list[Action]
    expected_score: float
    justification: str
    alternate_plans: list["TurnRecommendation"] = field(default_factory=list)  # top-3

@dataclass(frozen=True)
class RoundRecommendation:
    scenario_name: str
    initiative_order: list[str]
    turn_recommendations: list[TurnRecommendation]  # one per combatant in order
    final_score: float
    summary: str
```

## Action taxonomy and evaluator design

Each action type has an evaluator module/function. Following the pattern from CP1's tactic dispatcher:

```python
# pf2e/actions.py

_ACTION_EVALUATORS: dict[ActionType, Callable] = {
    ActionType.STRIDE: _evaluate_stride,
    ActionType.STRIKE: _evaluate_strike,
    # ... etc
}

def evaluate_action(action: Action, state: RoundState) -> ActionResult:
    evaluator = _ACTION_EVALUATORS[action.type]
    return evaluator(action, state)
```

Each evaluator:
1. Validates legality (returns `ActionResult` with 0 outcomes if invalid)
2. Computes outcome probabilities (typically 2-3 branches: success/fail or miss/hit/crit)
3. For each branch, computes state deltas (HP changes, conditions, movement, etc.)
4. Returns the full `ActionResult`

Some evaluators defer to existing code:
- `Strike` evaluator wraps `expected_strike_damage()` from `combat_math.py`, breaks it into outcome buckets
- `ActivateTactic` evaluator wraps the existing `evaluate_tactic()` function from `tactics.py`
- `Demoralize` evaluator uses `enumerate_d20_outcomes()` against target's Will DC (10 + Will save + level)

### Specific evaluator notes

**Stride destinations:** rather than enumerating every reachable square (hundreds), enumerate only *tactically meaningful* destinations:
- Squares adjacent to enemies (for attacks)
- Squares within banner aura (for support)
- Squares that would leave enemy reach (for defense)
- Squares that would flank with an ally
- The commander's position (to benefit from banner)

For a given Stride action, we commit to a specific destination. The search enumerates *candidate* destinations and picks the highest-scoring one. Typical: 5-10 destinations per character per turn.

**Strike targeting:** similarly, enumerate Strikes only against enemies in reach with the current weapon. Each Strike specifies target + weapon. A 2-handed fighter with two Strikes gets ~2 × num_reachable_enemies options.

**Tactic activation:** already-implemented evaluators. New wrapper translates between `evaluate_tactic()` output and `ActionResult`.

**Demoralize:** 
- Roll: Intimidation check (attacker Cha + proficiency) vs target's Will DC
- Success: target frightened 1
- Critical success: target frightened 2
- Fail: no effect
- Critical fail: target immune to demoralize from this source for 10 min (not modeled in single-round sim)

Aetregan is untrained in Intimidation (Cha 10, untrained 0). Her Demoralize check is +0. Unlikely to succeed against anything with Will save +2+. This action will rarely be picked for Aetregan by the scorer, but will be considered.

**Create a Diversion with Deceptive Tactics:**
- Aetregan: Warfare Lore check (Int +4 + trained +3 + level 1 = +8) vs target's Perception DC
- Can target up to two creatures within 30 ft (based on skill rules)
- Success: targets off-guard to next melee attack
- Critical success: targets off-guard to all attacks until end of next turn
- **Lengthy Diversion (Aetregan has it)**: duration extends from "your next turn" to "target's next turn"

This is ~+8 vs Perception DC ~12-14 for L1 bandits. High success rate. Strong combo with subsequent Strike (or allied Strike, though off-guard is specific to attacker).

**Trip / Disarm via Scorpion Whip:**
- Whip has Trip and Disarm traits — can use weapon directly instead of Athletics
- Trip: roll Athletics (Aetregan: Str +0, untrained = +0 — terrible) OR use weapon for a weapon-based Trip
- Actually the whip trait just lets you Trip "using the whip" which I believe still uses your Athletics modifier but doesn't require free hand
- For simplicity in CP5.1: Aetregan's Athletics-based Trip/Disarm will rarely be picked due to low modifier. We'll implement correctly but they'll be dominated by other actions.

**Feint with Deceptive Tactics:**
- Same as Create a Diversion but 1 target, melee range only
- Target becomes off-guard to next melee attack (Aetregan's own or ally's)
- Warfare Lore +8 vs target Perception DC

**Plant Banner:** For CP5.1, we add the action type and evaluator. Aetregan doesn't have the feat yet, so the action is always ineligible for her. When she takes Plant Banner at L2, `has_plant_banner=True` flips and the action becomes available.

## Scoring function specification

### Per-turn score

After a character's turn, we score the resulting state:

```python
def score_turn(state_before: RoundState, state_after: RoundState) -> float:
    """Score the outcome of a character's 3-action turn.
    
    Positive = good for party. Negative = bad.
    """
    # Kill score: P(each enemy killed) × kill_value
    kill_score = 0.0
    for enemy in state_after.enemies:
        hp_before = state_before.hp_state[enemy.name]
        hp_after = state_after.hp_state[enemy.name]
        if hp_after <= 0:
            kill_score += kill_value(enemy)
        # Partial-kill via distribution: P(dead) × kill_value
        # In hybrid threading, this is handled at branch points
    
    # Drop score: P(any PC dropped)
    drop_score = 0.0
    for pc in [state_after.commander] + state_after.squadmates:
        hp_before = state_before.hp_state[pc.character.name]
        hp_after = state_after.hp_state[pc.character.name]
        if hp_after <= 0:
            drop_score -= drop_cost(pc)
    
    # Damage tiebreaker
    damage_dealt = sum(
        max(0, state_before.hp_state[e.name] - state_after.hp_state[e.name])
        for e in state_after.enemies
    )
    damage_taken = sum(
        max(0, state_before.hp_state[pc.character.name] - state_after.hp_state[pc.character.name])
        for pc in [state_after.commander] + state_after.squadmates
    )
    damage_score = damage_dealt - 0.5 * damage_taken
    
    return kill_score + drop_score + damage_score
```

### Round score

The round score is the sum of all turn scores. The evaluator maximizes the TOTAL over all PC turns while the enemy turns are modeled as adversarial (minimizing party score).

### Kill value and drop cost

```python
def kill_value(enemy: EnemyState) -> float:
    """Value of killing this enemy this round.
    
    Base: enemy's full HP (damage we stop having to deal with).
    Boss multiplier: enemies with multiple attacks per turn are worth more.
    """
    return enemy.max_hp + 20 * enemy.num_attacks_per_turn


def drop_cost(pc: CombatantState) -> float:
    """Cost of dropping this PC this round.
    
    Base: pc's full HP.
    Role multiplier: support/caster PCs dropping is strictly worse for the party.
    """
    base = pc.character.ancestry_hp + (pc.character.class_hp + pc.character.abilities.mod(Ability.CON)) * pc.character.level
    role_multiplier = 2 if _is_support_class(pc) else 1
    return base + 20 * role_multiplier


def _is_support_class(pc: CombatantState) -> bool:
    """Heuristic: support if provides significant buffs to allies."""
    # Dalai (Bard) with Anthem is support; others aren't at L1
    return pc.character.name == "Dalai Alpaca"
```

Hard-coding "Dalai is support" is ugly; a cleaner system would tag classes or characters with a support trait. For CP5.1, we keep it simple.

## Search algorithm specification

### Beam search with widening-at-root

```python
def beam_search_turn(
    character: CombatantState,
    state: RoundState,
    config: SearchConfig,
) -> TurnRecommendation:
    """Find the best 3-action sequence for this character."""
    beam: list[PartialSequence] = [PartialSequence(actions=[], state=state, score=0.0)]
    
    for depth in range(config.max_depth):
        next_beam: list[PartialSequence] = []
        k_at_depth = config.beam_k_depths[depth]
        
        for partial in beam:
            if partial.is_complete or partial.actions_remaining == 0:
                next_beam.append(partial)  # carried forward
                continue
            
            # Enumerate all legal actions from partial's state
            candidates = enumerate_legal_actions(character, partial.state)
            
            # Expand each candidate
            for action in candidates:
                result = evaluate_action(action, partial.state)
                for outcome in result.outcomes:
                    if outcome.probability < config.low_prob_prune_threshold:
                        continue
                    # Apply outcome to state
                    new_state = partial.state.apply_action(action, outcome)
                    # Score the new state
                    turn_score = score_partial(new_state, partial, action, outcome)
                    # Multiply score by outcome probability
                    weighted_score = partial.score + outcome.probability * turn_score
                    next_beam.append(PartialSequence(
                        actions=partial.actions + [action],
                        state=new_state,
                        score=weighted_score,
                        probability=partial.probability * outcome.probability,
                    ))
        
        # Keep top K
        next_beam.sort(key=lambda p: p.score, reverse=True)
        beam = next_beam[:k_at_depth]
    
    # Best sequence at full depth
    best = max(beam, key=lambda p: p.score)
    return TurnRecommendation(
        character_name=character.character.name,
        action_sequence=best.actions,
        expected_score=best.score,
        justification=generate_justification(best),
        alternate_plans=[...]  # next 2 from beam
    )
```

### State threading with hybrid kill/drop branching

The `apply_action` method needs to handle both EV-collapse and branching. Conceptually:

```python
def apply_action(state: RoundState, action: Action, outcome: ActionOutcome) -> list[RoundState]:
    """Return 1 state (EV collapse) or 2+ states (branching at kill/drop)."""
    # Check if this outcome crosses a kill or drop threshold
    will_kill, kill_prob = _crosses_kill_threshold(state, outcome)
    will_drop, drop_prob = _crosses_drop_threshold(state, outcome)
    
    if will_kill or will_drop:
        # Branch: create two states, one where the event happens, one where it doesn't
        happens_state = state.clone()
        happens_state.apply_outcome_with_event(outcome, event=("kill" if will_kill else "drop"))
        happens_state.branch_probability = state.branch_probability * kill_prob
        
        not_happens_state = state.clone()
        not_happens_state.apply_outcome_without_event(outcome)
        not_happens_state.branch_probability = state.branch_probability * (1 - kill_prob)
        
        return [happens_state, not_happens_state]
    else:
        # EV collapse
        new_state = state.clone()
        new_state.apply_outcome_ev(outcome)
        return [new_state]
```

When the beam search encounters multiple states from one action, it expands each in the next iteration, keeping track of branch probabilities. Final scores multiply by branch probability.

### Adversarial enemy turns

When the search tree is inside the PC search and encounters an enemy's turn (in initiative order), it runs a *sub-search* for the enemy's best 3 actions. The enemy's search uses a smaller beam (K=20, depth 3) and its objective is *minimizing party score*. The enemy's chosen plan is then applied to the state, and the PC search continues.

This is single-best-response. In CP5.1 we don't explore multiple enemy plans.

## Damage pipeline specification

A new module `pf2e/damage_pipeline.py` implements the strict PF2e resolution order. The key function:

```python
def resolve_strike(
    attacker: Attacker,
    target: CombatantState,
    state: RoundState,
    attack_number: int = 1,
) -> list[StrikeOutcome]:
    """Resolve a single Strike through the full PF2e pipeline.
    
    Returns probability-weighted outcomes:
    [(prob, hp_damage_to_target_or_redirected, conditions, ...), ...]
    """
    # Step 1: Attack roll with full context
    effective_ac = compute_effective_ac(target, state)
    outcomes = enumerate_d20_outcomes(attacker.bonus, effective_ac)
    
    results = []
    
    # Step 2: For each outcome bucket, compute damage
    for outcome_type in [CRIT_SUCCESS, SUCCESS, FAILURE, CRIT_FAILURE]:
        prob = outcomes[outcome_type] / 20
        if prob < CONFIG.low_prob_prune_threshold:
            continue
        
        if outcome_type in (FAILURE, CRIT_FAILURE):
            results.append(StrikeOutcome(prob, damage=0, target=target.name))
            continue
        
        base_damage = compute_damage(attacker, weapon, crit=(outcome_type == CRIT_SUCCESS))
        
        # Step 3: Reaction phase — can Intercept redirect?
        if _can_intercept(state, target):
            # Branch: intercept happens or doesn't
            p_intercept = _intercept_policy(state, target, base_damage)
            if p_intercept > 0:
                # Intercepted: restart pipeline with Rook as target
                rook = state.get_guardian()
                rook_damage = _apply_mitigation_chain(base_damage, rook, state)
                results.append(StrikeOutcome(prob * p_intercept, rook_damage, rook.character.name))
            # Not intercepted
            target_damage = _apply_mitigation_chain(base_damage, target, state)
            results.append(StrikeOutcome(prob * (1 - p_intercept), target_damage, target.name))
        else:
            target_damage = _apply_mitigation_chain(base_damage, target, state)
            results.append(StrikeOutcome(prob, target_damage, target.name))
    
    return results


def _apply_mitigation_chain(damage: float, target: CombatantState, state: RoundState) -> float:
    """Apply Shield Block → Resistance → Temp HP in order."""
    # Shield Block
    if _shield_block_available(state, target):
        if _shield_block_policy(target, damage):
            shield = state.shield_state[target.character.name]
            damage = max(0, damage - shield.hardness)
            shield.hp_remaining -= min(damage, shield.hardness)
    
    # Resistance
    if has_guardians_armor(target.character):
        damage = max(0, damage - guardians_armor_resistance(target.character.level))
    
    # Temp HP pool handles the rest at HP-application time
    return damage
```

Reaction policies (`_intercept_policy`, `_shield_block_policy`) are configurable heuristics:
- **Intercept Attack**: use if expected damage to ally > resistance savings
- **Shield Block**: use if expected damage to self > hardness (basically always when available)

Both policies are greedy; optimal reaction timing requires full lookahead, deferred to CP6.

## Initiative system

At scenario load:
1. Each combatant rolls Perception + modifiers + d20 (seeded for reproducibility)
2. Order by total descending (ties broken by: PC > NPC, then by listed order)
3. Store in `Scenario.initiative_order: list[str]`

The scenario file can override:

```
[initiative]
# Explicit ordering, highest to lowest. Omit = compute from Perception rolls
Aetregan = 18
Bandit1 = 12
Rook = 10
Dalai = 8
Erisen = 6
```

Or with a random seed:

```
[initiative]
seed = 42
# initiatives rolled from each combatant's Perception bonus
```

## Output format

The evaluator produces a `RoundRecommendation` that can be formatted as text:

```
Round 1 — Strike Hard Validation Scenario
Initiative: Aetregan (+6), Bandit1 (+4), Rook (+6), Dalai (+3), Erisen (+7)

Turn 1: Aetregan (Commander)
  Action 1 (1-cost): Create a Diversion vs Bandit1 (+8 Warfare Lore vs DC 13)
    → 85% chance Bandit1 off-guard until end of their next turn
  Action 2 (2-cost): Activate Strike Hard! (signals Rook)
    → Rook reaction Strike at Bandit1 (off-guard, +8 vs AC 13 effective)
    → Expected damage: 11.34 (vs 8.55 without off-guard)
  Remaining: 0 actions

Turn 2: Bandit1 (Enemy)
  [adversarial best-response]
  Action 1: Stride 25 ft toward Rook (avoiding Aetregan's whip reach)
  Action 2: Strike Rook (+7 vs AC 19)
  Action 3: Strike Rook (+2 MAP)
  Expected damage to Rook: 5.62

...

Round Summary:
  Damage dealt: 11.34 to Bandit1 (66% of max HP — ~34% chance of kill)
  Damage taken: 5.62 (Rook)
  No PCs dropped.
  Score: 22.4
```

## Test strategy

### Unit tests per evaluator

Each action type gets unit tests for:
1. Legality checks (can't Stride a wall, can't Strike without weapon, etc.)
2. Outcome probabilities (sum to 1.0)
3. State deltas correct

### Integration tests

1. **Full round on Strike Hard scenario**: produces a `RoundRecommendation` with non-empty turn recommendations.
2. **Aetregan recommendation**: Aetregan's best turn includes Strike Hard activation (should be high EV).
3. **Rook's turn**: Rook's best action with a reachable enemy is a Strike.
4. **Deterministic with seed**: same scenario + same seed = same output.

### Regression: EV 8.55 still holds

In the simulated round, Strike Hard activation (called as part of Aetregan's turn) produces 8.55 EV for Rook's reaction Strike. This is the 6th time we validate this number across checkpoints.

### Expected test count

CP5.1 is large: probably 80-120 new tests. Target total: 290-325.

## Risks and open questions

1. **Stride destination enumeration**: "5-10 tactically meaningful destinations" is a heuristic. Might miss clever plays. Empirical validation in CP7 will show if the heuristic is too restrictive.

2. **Enemy AI is single-best-response**: enemies will always do their locally-best action. Could miss cooperation between enemies (two bandits flanking). Flagged as CP6 upgrade.

3. **Scoring weights are hand-tuned**: `kill_value = max_hp + 20 × attacks` is a reasonable-looking formula, not a validated one. Different weights might produce different recommendations. Hard to know without running many scenarios. Plan: ship with these defaults, revise in CP7 if recommendations feel off.

4. **Reaction policy greediness**: Intercept and Shield Block use greedy heuristics. Optimal timing sometimes matters (save Shield Block for bigger hit later). Deferred to CP6.

5. **"Support multiplier" is hardcoded to Dalai**: ugly but pragmatic for CP5.1. A cleaner design uses a role tag or a config-driven support_factor.

6. **Compute budget not measured yet**: I estimated <5 seconds per round evaluation, but actual numbers TBD. If it's 30 seconds, we revise beam sizes.

7. **Multi-round simulation not yet supported**: CP5.1 simulates one round. "Run 3 rounds and see who wins" requires CP5.4 or later.

## Pass 2 / Pass 3 outline

### Pass 2 (refinements after this review)

Expected refinement topics:
- Exact Skill enum membership
- Exact squadmate HP/skill data values
- Initiative modifier sources (Perception + what else?)
- Stride destination enumeration heuristics tightening
- Scoring weight calibration scenarios
- File/module layout decisions
- Scenario file schema changes

### Pass 3 (implementation brief)

- Step-by-step implementation order (probably ~15-20 steps)
- Exact code skeletons for each new class/function
- Exact test list with expected values
- Validation checklist matching Pass 1 architecture decisions
- Common pitfalls

## What comes after CP5.1

**CP5.2 — Class features and reactions**
- Dalai: Courageous Anthem composition, Soothe spell, Inspire Defense composition
- Erisen: Light Mortar siege action, Overdrive Inventor feature
- Rook: Intercept Attack (proper full evaluator), Taunt, Ever Ready reaction
- Healing actions
- Composition/cantrip/spell action types

**CP5.3 — General skill actions**
- Aid action (pre-declare + roll + bonus)
- Recall Knowledge (per-skill variants)
- Seek, Hide, Sneak (stealth)
- More skill feat variants

**CP6 — Multi-round and refinements**
- Multi-round simulation ("run 3 rounds")
- Expectimax enemy search (top-3 plans)
- Full optimal reaction timing
- Scoring weight calibration from CP7 feedback

**CP7 — Validation sweep**
- Validate against original Python prototype's recommendations
- Sanity checks across Outlaws of Alkenstar AP scenarios
- Tune anything that feels wrong

**CP8 — L5 forward compatibility**
- Character advancement (L2, L3, etc.)
- Feat progression
- Class DC scaling

**CP9 — Real AP scenarios**
- Encode actual Outlaws of Alkenstar encounters
- Produce recommendations for the user's next session

---

## Review asks

Before I write Pass 2 (let alone Pass 3), I want your reaction to:

1. **The action taxonomy** — 16 action types, categorized. Anything missing that feels foundational? Anything that should be deferred to CP5.2/5.3?

2. **The scoring formula** — `kill_value = max_hp + 20 × attacks`, `drop_cost = max_hp + 20 × support_multiplier`. The 20 factor is the amount of damage "saved" or "dealt" that a kill/drop is worth. Intuitively: "killing an enemy is worth ~20 damage to your party per round of combat it would have continued." Does that multiplier feel right?

3. **The state threading cutoff** — kill/drop branching at threshold 5% probability (actions less likely than this don't branch). Too aggressive? Too conservative?

4. **The Dalai support multiplier** — hardcoded 2x drop_cost for her because of Anthem. Feels right in theory (lose Anthem = significant party damage). Does it feel right in practice?

5. **Stride destination heuristic** — enumerate only tactically-meaningful destinations, not every reachable square. Concern: might miss plays the heuristic doesn't recognize. Acceptable for CP5.1?

6. **Enemy AI is single-best-response** — enemies pick their locally-best action, not a distribution. Acceptable for CP5.1?

7. **Test count 80-120 new tests** — is that scope OK for one checkpoint?

8. **Scope cut lines** — is there anything in CP5.1 that should actually be deferred to CP5.2/5.3?

Once you've reacted to these, I'll write Pass 2 incorporating your feedback, then Pass 3 as the concrete implementation brief.
