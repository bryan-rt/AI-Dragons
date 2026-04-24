# Checkpoint 5.1 Pass 2: Architectural Refinements

## Decisions consolidated from Pass 1 review

The user pushed back on two agent-recommended scope cuts and accepted the rest. Final scope:

| Decision | Resolution |
|---|---|
| Action count | **15 actions** (drop Taunt only; keep Trip and Disarm) |
| Kill/drop multiplier | **10** (not 20) |
| Dalai support multiplier | **2×** |
| Stride destination heuristic | **5 categories** |
| Enemy AI | **Full adversarial sub-search** (user push back: architectural correctness over simplicity) |
| State threading | **Hybrid expectimax with kill/drop branching** (user push back: core to tactical correctness) |
| Branch probability threshold | **5%** |
| Plant Banner | **Stub only** (Aetregan doesn't have it at L1) |
| Module layout | **4 modules**: `pf2e/actions.py`, `pf2e/damage_pipeline.py`, `sim/round_state.py`, `sim/search.py` |
| Skill enum | **16 core skills + lores dict**, confirmed against AoN |
| Initiative | **Perception roll at scenario load, seeded** |
| `RoundState` clone cost | **Shallow copies with frozenset conditions** (agent's optimization accepted) |

## Scope reality check

Full-scope CP5.1 is the largest checkpoint by a wide margin. Rough estimates:
- ~2,000-2,500 lines of new production code
- ~150-200 new tests
- 4 new modules + extensions to 3 existing modules
- 3-5 new scenario fixtures

Compared to previous checkpoints:
- CP1 / CP2 / CP3 / CP4 / CP4.5: each ~200-400 lines, 20-50 tests
- CP5.1: ~5-10× any previous checkpoint

Given this size, I'm recommending we split Pass 3 (implementation) into three sub-phases. Each ships and is validated before the next begins. This protects against catastrophic "everything breaks and we can't tell what caused it" failure modes.

See Pass 3 structure proposal at the end of this document.

## Architectural refinements

### 1. RoundState structural sharing

The naive approach deep-clones the entire `RoundState` at every branch/beam expansion. With K=50 and depth 3, that's potentially 125,000 clones per character turn. Profiling would likely show clone time dominates evaluation time.

**Revised design:**

```python
@dataclass
class RoundState:
    """Mutable combat state. Clone shallow; mutate through delta methods."""
    
    # Immutable reference data (never mutated, shared across clones)
    scenario: Scenario  # frozen
    initiative_order: tuple[str, ...]  # frozen tuple
    
    # Mutable per-state data (shallow-copied on clone)
    hp_state: dict[str, float]
    condition_state: dict[str, frozenset[str]]  # frozenset is immutable; cheap to share
    reaction_pool: dict[str, int]
    shield_state: dict[str, ShieldStatus]
    position_state: dict[str, tuple[int, int]]
    
    # Turn progression
    current_turn_idx: int
    actions_remaining: int
    
    # Branch tracking
    branch_probability: float = 1.0
    parent_branch: "RoundState | None" = None  # linked list for branch lineage
    
    def clone(self) -> "RoundState":
        """Shallow-copy mutable dicts. Frozensets are shared by reference.
        
        Structural sharing: conditions dicts are typically small (0-5 keys per
        combatant), so shallow dict.copy() is O(num_combatants).
        """
        return RoundState(
            scenario=self.scenario,
            initiative_order=self.initiative_order,
            hp_state=self.hp_state.copy(),
            condition_state=self.condition_state.copy(),
            reaction_pool=self.reaction_pool.copy(),
            shield_state=self.shield_state.copy(),
            position_state=self.position_state.copy(),
            current_turn_idx=self.current_turn_idx,
            actions_remaining=self.actions_remaining,
            branch_probability=self.branch_probability,
            parent_branch=self.parent_branch,
        )
    
    def apply_condition(self, target: str, condition: str) -> None:
        """Add a condition. O(1) due to frozenset sharing."""
        current = self.condition_state.get(target, frozenset())
        self.condition_state[target] = current | {condition}
    
    def remove_condition(self, target: str, condition: str) -> None:
        current = self.condition_state.get(target, frozenset())
        self.condition_state[target] = current - {condition}
```

Benchmark expectation: single clone <100μs, total clone cost per round <100ms. Acceptable.

### 2. Adversarial enemy sub-search architecture

User required full adversarial in CP5.1. Here's the structure.

When the beam search reaches an enemy's turn during PC-turn evaluation, it calls:

```python
def adversarial_enemy_turn(
    enemy: EnemyState,
    state: RoundState,
    config: SearchConfig,
) -> tuple[list[Action], RoundState]:
    """Find the enemy's best single turn plan.
    
    Enemy's objective: minimize PC expected score.
    Uses reduced beam (K=20) and depth 3.
    Returns (action sequence, resulting state).
    """
    enemy_config = replace(
        config,
        beam_k_depths=(20, 10, 5),  # smaller beam than party's
        max_depth=3,
    )
    
    # Score sign flip: enemies want to minimize party score
    enemy_score = lambda before, after: -score_turn(before, after)
    
    beam = beam_search_turn(
        combatant=enemy,  # protocol: both CombatantState and EnemyState work
        state=state,
        config=enemy_config,
        score_fn=enemy_score,
    )
    
    # Apply the enemy's chosen actions to the state
    final_state = state.clone()
    for action in beam.action_sequence:
        result = evaluate_action(action, final_state)
        # For the enemy turn inside a PC search, we collapse to EV
        # (we're already inside a PC search branch)
        final_state = final_state.apply_action_ev(action, result)
    
    return beam.action_sequence, final_state
```

Key insight: the enemy sub-search runs *inside* the PC search. When the PC search is considering its full 3-action plan, and the beam's current state is "just after action 2", the next step through the initiative cycle might be an enemy turn. The PC search pauses, runs the enemy sub-search to completion, gets back the resulting state, and resumes with action 3.

**Cost:** adversarial sub-search multiplies per-round compute by the enemy sub-search cost × number of enemy turns per round. For a 4-PC, 2-enemy scenario, that's 2 enemy sub-searches per round. Each costs roughly 20×15 + 10×15 + 5×15 = 525 action evaluations. Total: ~1000 extra evaluations. Acceptable given our budget.

**Simplification to preserve:** even with full adversarial search, enemies still use single-best-response at each depth level (they don't search over PC counter-strategies recursively). This is standard expectimax against a fixed policy — the "minimax cap" that keeps compute tractable.

### 3. Hybrid state threading with kill/drop branching

When to branch vs collapse. The rule:

**Branch when**: an action outcome has P(crosses kill/drop threshold) between 5% and 95%. Outside that range, branching is wasteful:
- P < 5%: the event is unlikely enough to ignore (pruned)
- P > 95%: the event is near-certain; treat it as deterministic

```python
def apply_action(
    state: RoundState,
    action: Action,
    outcome: ActionOutcome,
    config: SearchConfig,
) -> list[tuple[RoundState, float]]:
    """Apply an action outcome, returning (state, probability) list.
    
    Returns 1 state for EV-collapse path, 2 states when branching.
    """
    # Check for kill events — is any enemy's HP going to threshold?
    kill_events = detect_kill_crossings(state, outcome)
    # Check for drop events — is any PC's HP going to threshold?
    drop_events = detect_drop_crossings(state, outcome)
    
    significant_events = kill_events + drop_events
    if not significant_events:
        # EV-collapse: apply the outcome's expected values to current state
        new_state = state.clone()
        new_state.apply_outcome_ev(outcome)
        return [(new_state, 1.0)]
    
    # Branch: for each significant event, create two worlds
    # (Note: multiple simultaneous events compose multiplicatively)
    branches: list[tuple[RoundState, float]] = [(state.clone(), 1.0)]
    
    for event in significant_events:
        new_branches: list[tuple[RoundState, float]] = []
        for branch_state, branch_prob in branches:
            event_prob = event.probability
            if event_prob < config.kill_drop_branch_threshold:
                # Near-zero: assume event doesn't happen
                s_no = branch_state.clone()
                s_no.apply_outcome_without_event(outcome, event)
                new_branches.append((s_no, branch_prob))
            elif event_prob > (1 - config.kill_drop_branch_threshold):
                # Near-certain: assume event happens
                s_yes = branch_state.clone()
                s_yes.apply_outcome_with_event(outcome, event)
                new_branches.append((s_yes, branch_prob))
            else:
                # Fork
                s_yes = branch_state.clone()
                s_yes.apply_outcome_with_event(outcome, event)
                s_no = branch_state.clone()
                s_no.apply_outcome_without_event(outcome, event)
                new_branches.append((s_yes, branch_prob * event_prob))
                new_branches.append((s_no, branch_prob * (1 - event_prob)))
        branches = new_branches
    
    return branches
```

**Branch budget:** typical round has 1-3 significant kill/drop events. 2^3 = 8 branches worst case per search node. With beam width 50, total branches per turn ≤ 400. Tractable.

**Branch lineage:** the `parent_branch` field on `RoundState` lets us reconstruct the full branch path for debug output ("Aetregan Strike Hard → 65% chance Bandit1 killed → action 3 evaluates in both worlds").

### 4. Skill enum and character skill data

Confirmed via Aetregan's JSON and AoN cross-reference: 16 skills in Remaster, unchanged from Core Rulebook.

```python
# pf2e/types.py

class Skill(Enum):
    """The sixteen standard skills. (AoN: https://2e.aonprd.com/Skills.aspx)"""
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

Each skill has an associated key ability; we embed this as a lookup:

```python
# pf2e/skill_abilities.py or inline in types.py

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

Skill bonus derivation:

```python
# pf2e/combat_math.py

def skill_bonus(character: Character, skill: Skill) -> int:
    """Total skill bonus = ability mod + proficiency.
    
    Returns ability mod alone if untrained (proficiency = 0).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2136)
    """
    ability = SKILL_ABILITY[skill]
    ability_mod = character.abilities.mod(ability)
    rank = character.skill_proficiencies.get(skill, ProficiencyRank.UNTRAINED)
    prof = proficiency_bonus(rank, character.level)
    return ability_mod + prof


def lore_bonus(character: Character, lore_name: str) -> int:
    """Total lore bonus. Lores always use Int.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=47 — Lore skill)
    """
    ability_mod = character.abilities.mod(Ability.INT)
    rank = character.lores.get(lore_name, ProficiencyRank.UNTRAINED)
    prof = proficiency_bonus(rank, character.level)
    return ability_mod + prof
```

### 5. Character skill proficiencies per PC

Populated from JSON (Aetregan) and grounded defaults (others), following the user's guidance. All values from the character's actual build or plausible defaults:

**Aetregan** (from JSON):
```python
skill_proficiencies={
    Skill.ACROBATICS: ProficiencyRank.TRAINED,
    Skill.ARCANA: ProficiencyRank.TRAINED,
    Skill.ATHLETICS: ProficiencyRank.UNTRAINED,
    Skill.CRAFTING: ProficiencyRank.TRAINED,
    Skill.DECEPTION: ProficiencyRank.UNTRAINED,
    Skill.DIPLOMACY: ProficiencyRank.UNTRAINED,
    Skill.INTIMIDATION: ProficiencyRank.UNTRAINED,
    Skill.MEDICINE: ProficiencyRank.UNTRAINED,
    Skill.NATURE: ProficiencyRank.TRAINED,
    Skill.OCCULTISM: ProficiencyRank.TRAINED,
    Skill.PERFORMANCE: ProficiencyRank.UNTRAINED,
    Skill.RELIGION: ProficiencyRank.TRAINED,
    Skill.SOCIETY: ProficiencyRank.TRAINED,
    Skill.STEALTH: ProficiencyRank.TRAINED,
    Skill.SURVIVAL: ProficiencyRank.TRAINED,
    Skill.THIEVERY: ProficiencyRank.TRAINED,
},
lores={
    "Warfare": ProficiencyRank.TRAINED,
    "Deity": ProficiencyRank.TRAINED,
},
has_deceptive_tactics=True,
has_lengthy_diversion=True,
```

**Rook** (Automaton Guardian — grounded defaults):
```python
skill_proficiencies={
    Skill.ATHLETICS: ProficiencyRank.TRAINED,   # Guardian gets Athletics
    Skill.INTIMIDATION: ProficiencyRank.TRAINED,  # Intimidating tank
    Skill.SOCIETY: ProficiencyRank.TRAINED,     # Automaton: knowledge of self
    Skill.CRAFTING: ProficiencyRank.TRAINED,    # Automaton affinity
    Skill.PERCEPTION: already in perception_rank,
},
ancestry_hp=10,  # Automaton
class_hp=10,     # Guardian
```

**Dalai** (Human Bard Warrior Muse):
```python
skill_proficiencies={
    Skill.OCCULTISM: ProficiencyRank.TRAINED,    # Bard spellcasting
    Skill.PERFORMANCE: ProficiencyRank.TRAINED,  # Bard signature
    Skill.DIPLOMACY: ProficiencyRank.TRAINED,
    Skill.INTIMIDATION: ProficiencyRank.TRAINED, # Warrior Muse
    Skill.ATHLETICS: ProficiencyRank.TRAINED,    # Warrior Muse
    Skill.ACROBATICS: ProficiencyRank.TRAINED,
},
lores={
    "Bardic": ProficiencyRank.TRAINED,
    "Warfare": ProficiencyRank.TRAINED,  # Shelyn follower with warrior muse
},
ancestry_hp=8,
class_hp=8,
```

**Erisen** (Elf Inventor Munitions Master):
```python
skill_proficiencies={
    Skill.CRAFTING: ProficiencyRank.EXPERT,     # Inventor class feature
    Skill.ARCANA: ProficiencyRank.TRAINED,
    Skill.SOCIETY: ProficiencyRank.TRAINED,
    Skill.ATHLETICS: ProficiencyRank.TRAINED,
    Skill.NATURE: ProficiencyRank.TRAINED,      # Elf background
},
lores={
    "Engineering": ProficiencyRank.TRAINED,
    "Alkenstar": ProficiencyRank.TRAINED,
},
ancestry_hp=6,
class_hp=8,
```

All squadmate entries will include a docstring note: "HP and skill data are grounded defaults; verify against character sheets when available."

### 6. Create a Diversion and Feint under Deceptive Tactics

Aetregan's signature non-tactic actions. Both use Warfare Lore per her feat:

```python
# pf2e/actions.py (evaluator functions)

def _evaluate_create_a_diversion(
    action: Action, state: RoundState,
) -> ActionResult:
    """Create a Diversion — Deception (or Warfare Lore via Deceptive Tactics).
    
    Roll vs target's Perception DC. Success: target off-guard to your
    next melee attack (extended to target's next turn if Lengthy Diversion).
    Targets: up to 2 creatures within 30 ft.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=38&Redirected=1 — Deception)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7794 — Deceptive Tactics)
    """
    actor = state.get_combatant(action.actor_name)
    targets = [state.get_enemy(name) for name in action.target_names]
    
    # Determine skill: use Warfare Lore if Aetregan has Deceptive Tactics, else Deception
    if actor.character.has_deceptive_tactics:
        bonus = lore_bonus(actor.character, "Warfare")
    else:
        bonus = skill_bonus(actor.character, Skill.DECEPTION)
    
    outcomes = []
    for target in targets:
        perception_dc = target.perception_dc  # 10 + Perception bonus
        d20_out = enumerate_d20_outcomes(bonus, perception_dc)
        # Success grants off-guard to the actor's next melee Strike (or all attacks on crit)
        # If actor has Lengthy Diversion, duration extends
        duration_turns = 2 if actor.character.has_lengthy_diversion else 1
        
        # Build per-target probability tree
        # ... complete evaluator logic ...
    
    return ActionResult(action=action, outcomes=outcomes)


def _evaluate_feint(
    action: Action, state: RoundState,
) -> ActionResult:
    """Feint — single target, melee range only, Deception (or Warfare Lore).
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=38 — Feint subskill)
    """
    # Similar structure to Create a Diversion but single-target, adjacent only
```

The scoring implication: these actions produce the off-guard condition on an enemy for 1-2 turns. The scoring function needs to account for the expected damage increase from subsequent off-guard-aware Strikes. In CP5.1 this manifests as: when scoring a search state where an enemy has off-guard, their effective AC drops by 2, raising expected damage from future Strikes.

### 7. Action type taxonomy (15 actions — final list)

| # | ActionType | Cost | Actor | Eligibility | Key Notes |
|---|---|---|---|---|---|
| 1 | STRIDE | 1 | any | has movement | Up to Speed ft |
| 2 | STEP | 1 | any | not in difficult terrain | 5 ft, no AoO |
| 3 | STRIKE | 1 | any w/ weapon | target in reach/range | MAP applies |
| 4 | RAISE_SHIELD | 1 | shield wielders | shield not broken | +2 AC |
| 5 | END_TURN | 0 | any | always | forfeit remaining actions |
| 6 | PLANT_BANNER | 2 | Aetregan | `has_plant_banner=True` (L2+) | stub returns ineligible at L1 |
| 7 | ACTIVATE_TACTIC | (varies) | Aetregan | tactic prepared + prereqs | wraps existing evaluators |
| 8 | SHIELD_BLOCK | R | shield wielders | reaction, triggered | damage pipeline handles |
| 9 | DEMORALIZE | 1 | any | target within 30 ft, Int-audible | Intimidation vs Will DC |
| 10 | CREATE_A_DIVERSION | 1 | any | target within 30 ft | Deception/Warfare Lore vs Perception DC |
| 11 | FEINT | 1 | any | target adjacent | Deception/Warfare Lore vs Perception DC |
| 12 | TRIP | 1 | any | target in reach, weapon has Trip trait or athletics | Athletics vs Reflex DC |
| 13 | DISARM | 1 | any | target in reach, weapon has Disarm trait or athletics | Athletics vs Reflex DC |
| 14 | INTERCEPT_ATTACK | R | Guardian | triggered by ally taking damage | damage pipeline handles |
| 15 | EVER_READY | R | Guardian | once/turn reset | meta-reaction, refreshes Intercept |

Note: I'm keeping Intercept Attack and Ever Ready as action types even though they're reactions, not turn actions. They're handled by the damage pipeline and the state machine, but having them in the ActionType enum makes the system cleaner.

Mountaineering Training is Aetregan's 5th folio tactic but it's a passive buff (climb speed), not a typical combat action. Still gets an evaluator via ACTIVATE_TACTIC.

### 8. Scoring function with offense/defense balance

Final formula (multiplier 10 per user):

```python
def score_state_transition(
    state_before: RoundState,
    state_after: RoundState,
    character_scope: str,  # which character's turn we're scoring
) -> float:
    """Score the effect of a state transition.
    
    Positive = better for party. Negative = worse.
    Used for both PC turns (maximized) and enemy turns (minimized).
    """
    kill_score = 0.0
    drop_score = 0.0
    
    # Kill score: threat-weighted enemy eliminations
    for enemy_name, enemy in state_after.iter_enemies():
        hp_before = state_before.hp_state[enemy_name]
        hp_after = state_after.hp_state[enemy_name]
        
        # P(enemy killed) = transition of hp from >0 to ≤0
        # In branch states, this is deterministic (either happened or didn't)
        # In EV states, we estimate via P(total damage ≥ hp_before)
        p_killed = _compute_p_killed(hp_before, hp_after, state_after.branch_probability)
        
        kill_value = enemy.max_hp + 10 * enemy.num_attacks_per_turn
        kill_score += p_killed * kill_value
    
    # Drop score: role-weighted PC drops
    for pc_name, pc in state_after.iter_party():
        hp_before = state_before.hp_state[pc_name]
        hp_after = state_after.hp_state[pc_name]
        
        p_dropped = _compute_p_dropped(hp_before, hp_after, state_after.branch_probability)
        
        role_multiplier = 2 if _is_support(pc) else 1
        drop_cost = max_hp(pc.character) + 10 * role_multiplier
        drop_score -= p_dropped * drop_cost
    
    # Damage tiebreaker (symmetric for offense/defense)
    damage_dealt = sum(
        max(0, state_before.hp_state[e] - state_after.hp_state[e])
        for e in state_after.iter_enemy_names()
    )
    damage_taken = sum(
        max(0, state_before.hp_state[pc] - state_after.hp_state[pc])
        for pc in state_after.iter_party_names()
    )
    damage_score = damage_dealt - 0.5 * damage_taken
    
    return kill_score + drop_score + damage_score


def score_enemy_turn(state_before, state_after, enemy_name) -> float:
    """Enemies minimize party score (sign-flipped)."""
    return -score_state_transition(state_before, state_after, enemy_name)
```

The `_is_support` check is hardcoded to Dalai for CP5.1:

```python
def _is_support(pc: CombatantState) -> bool:
    """Does this PC provide party-wide buffs that matter?
    
    CP5.1 heuristic: support if character provides Anthem or equivalent.
    CP6 cleanup: add a role_weight field on Character.
    """
    return pc.character.name == "Dalai Alpaca"
```

Ugly but pragmatic. Flagged for CP6 refactor.

### 9. Damage pipeline (strict PF2e order)

The full pipeline module `pf2e/damage_pipeline.py` implements:

```
Attack roll (with AC modifiers: shield, off-guard, frightened, cover)
  ↓
Damage roll (on hit/crit)
  ↓
Reaction phase:
  - Intercept Attack (Guardian, redirects damage to self)
  - Shield Block (any shield, absorbs up to hardness)
  ↓
Resistance application (Guardian's Armor, etc.)
  ↓
Temp HP absorption (Plant Banner temp HP, etc.)
  ↓
Current HP reduction (final damage)
```

Returns a probability-weighted list of `StrikeOutcome` records:

```python
@dataclass(frozen=True)
class StrikeOutcome:
    probability: float
    final_target: str           # may differ from original_target due to Intercept
    damage_dealt: float         # after all mitigation
    damage_blocked_by_shield: float
    damage_reduced_by_resistance: float
    damage_absorbed_by_temp_hp: float
    was_critical: bool
    breakdown: dict[str, float]  # for debug output
```

The search uses `damage_dealt` for scoring. The `breakdown` is for user-facing output.

### 10. Initiative system

```python
# sim/initiative.py (new module)

def roll_initiative(
    scenario: Scenario,
    seed: int = 0,
) -> list[str]:
    """Roll Perception + d20 for each combatant, seeded for reproducibility.
    
    Returns combatant names in initiative order (highest first).
    Ties broken by: PC > NPC, then by listed order in scenario.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2127)
    """
    rng = random.Random(seed)
    rolls: list[tuple[str, int, bool]] = []  # (name, total, is_pc)
    
    # Commander
    c = scenario.commander
    bonus = perception_bonus(c.character)
    rolls.append((c.character.name, rng.randint(1, 20) + bonus, True))
    
    # Squadmates
    for sq in scenario.squadmates:
        bonus = perception_bonus(sq.character)
        rolls.append((sq.character.name, rng.randint(1, 20) + bonus, True))
    
    # Enemies
    for e in scenario.enemies:
        # Enemies have perception bonus on EnemyState (derived or explicit)
        bonus = e.perception_bonus
        rolls.append((e.name, rng.randint(1, 20) + bonus, False))
    
    # Sort: highest first, PC > NPC on ties
    rolls.sort(key=lambda x: (-x[1], not x[2]))
    return [name for name, _, _ in rolls]


def load_initiative_from_scenario(scenario_file: ScenarioFile) -> list[str]:
    """If scenario file specifies [initiative], use that; else roll."""
    if scenario_file.has_initiative_section:
        return scenario_file.initiative_order
    return roll_initiative(scenario_file.build_scenario(), seed=42)
```

Scenario file schema for explicit initiative:

```
[initiative]
seed = 42
# OR explicit ordering:
# Aetregan = 18
# Bandit1 = 12
# Rook = 10
```

### 11. Output formatting

The final `RoundRecommendation` renders to a structured text block:

```
Round 1 — Strike Hard Validation
Initiative order:
  1. Aetregan (Perception 18)
  2. Erisen (Perception 15)
  3. Bandit1 (Perception 13)
  4. Rook (Perception 11)
  5. Dalai (Perception 8)

Final expected round score: +18.4
  - Enemy damage: 11.0 (Bandit1 → 4/15 HP remaining)
  - P(kills): 22% chance Bandit1 dies this round
  - Party damage taken: 4.8 (Rook)
  - No PCs dropped

Turn plans:

▶ Aetregan (Commander) — score +14.2
  Action 1: Create a Diversion vs Bandit1 (Warfare Lore +8 vs Perception DC 13)
    → 85% success → Bandit1 off-guard to Aetregan's next melee attack
    → 15% success → Bandit1 off-guard to all Aetregan's attacks until end of target's next turn (crit)
  Action 2-3: Activate Strike Hard! (signal Rook)
    → Rook reaction Strike with longsword at +8 vs AC 13 (off-guard)
    → Expected damage: 11.34
    → 18% chance kills Bandit1 outright (crit + high roll)

▶ Erisen (Inventor) — score -0.2
  [Erisen's best plan here]

▶ Bandit1 (Enemy) — score -2.3 against party
  [enemy's best plan — single-best-response]

... etc
```

### 12. Module layout (final)

```
pf2e/
├── actions.py          # ActionType, Action, ActionResult, per-action evaluators
├── damage_pipeline.py  # StrikeOutcome, resolve_strike with full mitigation chain
├── tactics.py          # existing, extended for skill-check integration
├── character.py        # existing, extended with skill_proficiencies, lores
├── combat_math.py      # existing, extended with skill_bonus, lore_bonus
├── abilities.py        # existing
├── equipment.py        # existing
├── proficiency.py      # existing
├── types.py            # existing, adds Skill enum

sim/
├── round_state.py      # RoundState with hybrid branching semantics
├── search.py           # Beam search, adversarial sub-search
├── initiative.py       # Initiative rolling and ordering
├── scenario.py         # existing, extended for [initiative] section
├── grid.py             # existing
├── grid_spatial.py     # existing
├── party.py            # existing, extended with skill data for all PCs

tests/
├── test_actions.py     # per-action evaluator tests
├── test_damage_pipeline.py  # pipeline tests with full mitigation
├── test_search.py      # beam search tests
├── test_round_state.py # state threading tests (EV + branching)
├── test_initiative.py  # initiative order tests
├── test_scoring.py     # scoring function tests
├── test_round_integration.py  # end-to-end full round tests
├── (existing test files)
```

## Pass 3 structure: split into three sub-briefs

Given the scope, Pass 3 is split into three implementation phases. Each is a separate brief, delivered and reviewed sequentially.

### Pass 3a: Foundation

- `Skill` enum + `SKILL_ABILITY` lookup
- `Character.skill_proficiencies`, `Character.lores`, `Character.has_*` feat flags
- `skill_bonus()`, `lore_bonus()` helpers
- Populate squadmate HP data (ancestry_hp, class_hp for all four PCs)
- Populate squadmate skill data (grounded defaults)
- `ActionType` enum, `Action` dataclass, `ActionResult` dataclass
- `ActionOutcome` dataclass
- Scenario parser: initiative section support
- `EnemyState` extension: `max_hp`, `current_hp`, `perception_bonus`, `perception_dc`

~30-40 tests. Deliverable: data model and types ready for algorithm work.

### Pass 3b: Algorithms

- `RoundState` with shallow-clone + frozenset conditions
- Hybrid state threading (`apply_action` with branching)
- `sim/search.py`: beam search with K=50/20/10
- Adversarial enemy sub-search
- Scoring function
- Initiative rolling
- Damage pipeline (strict PF2e order)

~40-60 tests. Deliverable: search infrastructure ready to call evaluators.

### Pass 3c: Actions and integration

- 15 action evaluators (per the taxonomy table)
- Tactic activation wrapper (calls existing `evaluate_tactic`)
- Output formatter for `RoundRecommendation`
- End-to-end integration tests
- Regression: Strike Hard EV 8.55 survives (for the 7th time)
- Killer test: load scenario, run full round, produce recommendation

~50-70 tests. Deliverable: working full-round simulator.

**Total CP5.1:** ~120-170 tests, well within the 150-200 estimate.

Each sub-brief is reviewed after implementation. If 3a has issues, we fix before 3b starts. This keeps the feedback loop tight.

## Open questions before Pass 3a

1. **Squadmate skill data confidence.** The skill proficiencies I proposed for Rook/Dalai/Erisen are grounded defaults. If you'd like to provide Pathbuilder JSONs for them, we use real data. Otherwise, we ship with defaults and note them as "subject to verification."

2. **Scoring function tuning.** Multiplier 10 is conservative; we revisit in CP7. Are you OK shipping CP5.1 with recommendations that may feel slightly "too cautious" compared to your table experience?

3. **Stride destination heuristic**. The 5 categories I proposed (adjacent-to-enemy, in-aura, leave-reach, flank, commander-position) are tactical but not exhaustive. Any categories you want added? (Cover is flagged for CP5.2.)

4. **Debug/trace output for the search tree**. For tuning and debugging, it's useful to dump the top-K partial sequences at each depth. Want this as a CLI flag (`--debug-search`) in CP5.1, or defer to CP6?

Once you answer these, I write Pass 3a and we begin.
