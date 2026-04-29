"""Action types, data structures, evaluators, and dispatcher.

Actions are the atomic choices a character makes during combat. Each
ActionType has an associated evaluator that computes the outcome
distribution for a given (action, state) pair.

Pass 3a: types only. Pass 3c: 14 evaluators + dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pf2e.combat_math import (
    armor_class,
    attack_bonus,
    damage_avg,
    die_average,
    enumerate_d20_outcomes,
    expected_enemy_turn_damage,
    guardians_armor_resistance,
    lore_bonus,
    map_penalty,
    max_hp,
    melee_reach_ft,
    skill_bonus,
)
from pf2e.types import SaveType, Skill

if TYPE_CHECKING:
    from pf2e.tactics import SpatialQueries
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


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
    # CP5.2: class features
    ANTHEM = auto()           # Dalai: Courageous Anthem composition
    SOOTHE = auto()           # Dalai: Soothe occult spell
    MORTAR_AIM = auto()       # Erisen: Light Mortar aim
    MORTAR_LOAD = auto()      # Erisen: Light Mortar load
    MORTAR_LAUNCH = auto()    # Erisen: Light Mortar fire
    TAUNT = auto()            # Rook: Guardian Taunt
    # CP5.3: skill actions
    RECALL_KNOWLEDGE = auto()  # Identify enemy W/R
    HIDE = auto()              # Stealth → Hidden condition
    SNEAK = auto()             # Move while Hidden (half Speed)
    SEEK = auto()              # Perception → reveal Hidden enemies
    AID = auto()               # Prepare to aid an ally (next-round bonus)
    STAND = auto()             # Stand up from Prone (1 action)
    # CP5.4: spell chassis
    CAST_SPELL = auto()        # Generic spell cast; slug in tactic_name
    # CP7.2: hand state
    INTERACT = auto()          # Draw/stow weapon (1 action)
    RELEASE = auto()           # Release held item (free action, 0 cost)
    # CP10.4.2: auto-state actions
    DROP_PRONE = auto()        # Drop Prone (1 action)
    TAKE_COVER = auto()        # Take Cover (1 action)


@dataclass(frozen=True)
class Action:
    """A specific instance of an action, fully parameterized.

    Example:
        Action(type=ActionType.STRIDE, actor_name="Rook",
               action_cost=1, target_position=(5, 8))
        Action(type=ActionType.STRIKE, actor_name="Aetregan",
               action_cost=1, target_name="Bandit1",
               weapon_name="Scorpion Whip")
        Action(type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
               action_cost=2, tactic_name="Strike Hard!")

    Unused fields stay at their defaults (empty string or None).
    The evaluator for each ActionType knows which fields are meaningful.
    """
    type: ActionType
    actor_name: str
    action_cost: int
    target_name: str = ""
    target_position: tuple[int, int] | None = None
    target_names: tuple[str, ...] = ()
    weapon_name: str = ""
    tactic_name: str = ""


@dataclass(frozen=True)
class ActionOutcome:
    """One branch of an action's probability tree.

    Each outcome is a complete state-delta specification: what HP changes,
    what positions move, what conditions are applied or removed.

    All dicts are convention-immutable after construction.
    """
    probability: float
    hp_changes: dict[str, float] = field(default_factory=dict)
    position_changes: dict[str, tuple[int, int]] = field(default_factory=dict)
    conditions_applied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    conditions_removed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reactions_consumed: dict[str, int] = field(default_factory=dict)
    score_delta: float = 0.0  # EV from conditions/effects not captured in hp_changes
    description: str = ""
    # Resource changes (spell slots, consumables). Maps resource_key → delta.
    resource_changes: dict[str, int] = field(default_factory=dict)
    # PC whose resources to update (empty = no resource change).
    actor_name: str = ""
    # Hand state changes for INTERACT/RELEASE actions.
    held_weapons_add: tuple[str, ...] = ()     # Items drawn into hands
    held_weapons_remove: tuple[str, ...] = ()  # Items released from hands


@dataclass(frozen=True)
class ActionResult:
    """The evaluator's output for a single (action, state) pair.

    If eligible is False, outcomes is empty and ineligibility_reason explains.
    If eligible is True, outcomes probabilities sum to ~1.0.
    """
    action: Action
    outcomes: tuple[ActionOutcome, ...] = ()
    eligible: bool = True
    ineligibility_reason: str = ""

    @property
    def expected_damage_dealt(self) -> float:
        """Expected damage TO enemies across all outcomes.

        Negative hp_changes values represent damage dealt.
        """
        total = 0.0
        for outcome in self.outcomes:
            for delta in outcome.hp_changes.values():
                if delta < 0:
                    total += outcome.probability * (-delta)
        return total

    def verify_probability_sum(self, tolerance: float = 1e-6) -> bool:
        """Sanity check: outcome probabilities sum to ~1.0 for eligible actions."""
        if not self.eligible:
            return len(self.outcomes) == 0
        total = sum(o.probability for o in self.outcomes)
        return abs(total - 1.0) < tolerance


# ---------------------------------------------------------------------------
# Private geometry helpers (pure math, no sim/ imports)
# ---------------------------------------------------------------------------

def _grid_distance_ft(a: tuple[int, int], b: tuple[int, int]) -> int:
    """PF2e grid distance with 5/10 diagonal alternation.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2357)
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    diag = min(dr, dc)
    straight = abs(dr - dc)
    return (diag // 2) * 10 + ((diag + 1) // 2) * 5 + straight * 5


def _chebyshev_squares(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _is_within_weapon_reach(
    attacker_pos: tuple[int, int],
    target_pos: tuple[int, int],
    reach_ft: int,
) -> bool:
    """Check if target is within weapon reach.
    10-ft reach uses Chebyshev special case.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)
    """
    if reach_ft == 10:
        return 0 < _chebyshev_squares(attacker_pos, target_pos) <= 2
    return 0 < _grid_distance_ft(attacker_pos, target_pos) <= reach_ft


# ---------------------------------------------------------------------------
# Private evaluator helpers
# ---------------------------------------------------------------------------

def _count_pcs_in_enemy_reach(
    enemy: EnemySnapshot, state: RoundState,
) -> int:
    """Count living PCs within standard melee reach (5 ft) of an enemy."""
    count = 0
    for pc in state.pcs.values():
        if pc.current_hp > 0 and _grid_distance_ft(enemy.position, pc.position) <= 5:
            count += 1
    return count


def _find_weapon(
    actor_snap: CombatantSnapshot, weapon_name: str,
) -> object | None:
    """Find an EquippedWeapon by name. Falls back to first weapon."""
    for eq in actor_snap.character.equipped_weapons:
        if eq.weapon.name == weapon_name:
            return eq
    if actor_snap.character.equipped_weapons:
        return actor_snap.character.equipped_weapons[0]
    return None


def _has_recalled(actor_snap: CombatantSnapshot, enemy_name: str) -> bool:
    """Return True if actor has successfully used Recall Knowledge on this enemy.

    Controls whether weakness/resistance modifiers apply in damage evaluation.
    Tag format: "recalled_<enemy_name_lowercased_underscores>"
    """
    tag = "recalled_" + enemy_name.lower().replace(" ", "_")
    return tag in actor_snap.conditions


def _d20_success_probability(bonus: int, dc: int) -> float:
    """Probability of meeting DC on a d20 roll + bonus. Clamps to [0.05, 0.95]."""
    hits = 20 - max(0, dc - bonus - 1)
    return max(0.05, min(0.95, hits / 20))


def _d20_crit_success_probability(bonus: int, dc: int) -> float:
    """Probability of exceeding DC by 10+ on a d20."""
    crits = 20 - max(0, dc + 10 - bonus - 1)
    return max(0.0, min(1.0, crits / 20))


def _d20_crit_fail_probability(bonus: int, dc: int) -> float:
    """Probability of failing DC by 10+ on a d20."""
    crit_fails = max(0, dc - 10 - bonus)
    return max(0.0, min(1.0, crit_fails / 20))


def _build_mock_spatial(
    commander_name: str, state: RoundState,
) -> SpatialQueries:
    """Build MockSpatialQueries from RoundState for tactic evaluation.

    Approximates spatial relationships from snapshot positions.
    BFS pathfinding is replaced by straight-line distance.
    """
    from pf2e.tactics import MockSpatialQueries

    # Banner aura
    if state.banner_planted and state.banner_position is not None:
        center = state.banner_position
        radius = 40
    else:
        center = state.pcs[commander_name].position if commander_name in state.pcs else None
        radius = 30

    in_aura: dict[str, bool] = {}
    for name, pc in state.pcs.items():
        if center is not None:
            in_aura[name] = _grid_distance_ft(pc.position, center) <= radius
        else:
            in_aura[name] = False

    reachable: dict[str, list[str]] = {}
    for pc_name, pc in state.pcs.items():
        reach = melee_reach_ft(pc.character)
        reachable[pc_name] = [
            en_name for en_name, en in state.enemies.items()
            if en.current_hp > 0
            and _is_within_weapon_reach(pc.position, en.position, reach)
        ]

    adjacencies: set[tuple[str, str]] = set()
    distances: dict[tuple[str, str], int] = {}
    all_entries = [(n, p.position) for n, p in state.pcs.items()]
    all_entries += [(n, e.position) for n, e in state.enemies.items()]
    for i, (n1, p1) in enumerate(all_entries):
        for n2, p2 in all_entries[i + 1:]:
            d = _grid_distance_ft(p1, p2)
            distances[(n1, n2)] = d
            if d <= 5:
                adjacencies.add((n1, n2))

    return MockSpatialQueries(
        in_aura=in_aura,
        reachable_enemies=reachable,
        adjacencies=adjacencies,
        distances=distances,
    )


def _build_tactic_context(
    actor_name: str, state: RoundState, spatial: SpatialQueries,
) -> object:
    """Build a TacticContext from RoundState snapshots (duck-typed)."""
    from pf2e.tactics import TacticContext

    commander_snap = state.pcs[actor_name]
    squadmate_snaps = [
        pc for name, pc in state.pcs.items()
        if name != actor_name and pc.current_hp > 0
    ]
    enemy_list = [e for e in state.enemies.values() if e.current_hp > 0]
    return TacticContext(
        commander=commander_snap,          # type: ignore[arg-type]
        squadmates=squadmate_snaps,        # type: ignore[arg-type]
        enemies=enemy_list,                # type: ignore[arg-type]
        banner_position=state.banner_position,
        banner_planted=state.banner_planted,
        spatial=spatial,
        anthem_active=state.anthem_active,
    )


# ---------------------------------------------------------------------------
# 4-A: END_TURN
# ---------------------------------------------------------------------------

def evaluate_end_turn(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Always eligible. No state changes."""
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(probability=1.0, description="End turn"),),
    )


# ---------------------------------------------------------------------------
# 4-B: PLANT_BANNER
# ---------------------------------------------------------------------------

def evaluate_plant_banner(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Eligible iff actor has Plant Banner feat. Aetregan does not at L1.
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or not actor.character.has_plant_banner:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason="Plant Banner feat not present",
        )
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            description="Plant banner at current position",
        ),),
    )


# ---------------------------------------------------------------------------
# 4-C: RAISE_SHIELD
# ---------------------------------------------------------------------------

def evaluate_raise_shield(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Raise Shield for +2 AC. Danger-weighted EV.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
    CP6 calibration target: danger estimation is approximate.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not found as PC")
    if actor.character.shield is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No shield equipped")
    if actor.shield_raised:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Shield already raised")
    # Must be holding the shield to raise it (CP7.2 hand state)
    if actor.character.shield.name not in actor.held_weapons:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Shield not held — use INTERACT to draw")

    # Threat-estimated danger: all living enemies within one Stride (30 ft)
    # can potentially target this actor. +2 AC ≈ 10% hit reduction.
    danger = 0.0
    for enemy in state.enemies.values():
        if enemy.current_hp <= 0 or not enemy.damage_dice:
            continue
        # Count all living PCs as potentially threatened (conservative)
        num_threatened = max(1, sum(1 for p in state.pcs.values() if p.current_hp > 0))
        p_targets_actor = 1.0 / num_threatened
        dmg = expected_enemy_turn_damage(enemy, actor)  # type: ignore[arg-type]
        danger += dmg * p_targets_actor
    shield_ev = danger * 0.10  # +2 AC ≈ 10% hit reduction

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={action.actor_name: ("shield_raised",)},
            score_delta=shield_ev,
            description=f"Raise Shield (+2 AC, EV {shield_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# 4-D: STEP
# ---------------------------------------------------------------------------

def evaluate_step(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Step 5 ft to target_position. Always eligible if position set.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2321)
    """
    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No target position specified")
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            position_changes={action.actor_name: action.target_position},
            description=f"Step to {action.target_position}",
        ),),
    )


# ---------------------------------------------------------------------------
# 4-E: STRIDE
# ---------------------------------------------------------------------------

def evaluate_stride(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Stride to target_position. Always eligible if position set.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
    """
    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No target position specified")
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            position_changes={action.actor_name: action.target_position},
            description=f"Stride to {action.target_position}",
        ),),
    )


# ---------------------------------------------------------------------------
# 4-F: STRIKE
# ---------------------------------------------------------------------------

def evaluate_strike(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Strike with a weapon. Uses MAP from actor's map_count.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2322)
    (AoN MAP: https://2e.aonprd.com/Rules.aspx?ID=220)
    """
    # Handle PC Strike
    pc_actor = state.pcs.get(action.actor_name)
    if pc_actor is not None:
        return _evaluate_pc_strike(action, state, pc_actor)

    # Handle enemy Strike
    enemy_actor = state.enemies.get(action.actor_name)
    if enemy_actor is not None:
        return _evaluate_enemy_strike(action, state, enemy_actor)

    return ActionResult(action=action, eligible=False,
                       ineligibility_reason="Actor not found")


def _effective_status_bonus_attack(
    actor: CombatantSnapshot, state: RoundState,
) -> int:
    """Effective status bonus to attack rolls, accounting for mid-round Anthem.

    If Anthem was cast earlier this turn, it may not yet be reflected on the
    actor's snapshot. This helper ensures STRIKE sees the bonus.
    (AoN: https://2e.aonprd.com/Spells.aspx — Courageous Anthem)
    Flagged for CP6 multi-buff refactor.
    """
    return max(actor.status_bonus_attack, 1 if state.anthem_active else 0)


def _effective_status_bonus_damage(
    actor: CombatantSnapshot, state: RoundState,
) -> int:
    """Effective status bonus to damage, accounting for mid-round Anthem."""
    return max(actor.status_bonus_damage, 1 if state.anthem_active else 0)


def _evaluate_pc_strike(
    action: Action, state: RoundState, actor: CombatantSnapshot,
) -> ActionResult:
    """PC Strike against an enemy target."""
    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    equipped = _find_weapon(actor, action.weapon_name)
    if equipped is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No weapon found")

    reach = melee_reach_ft(actor.character)
    if not _is_within_weapon_reach(actor.position, target.position, reach):
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target out of weapon reach")

    # MAP: map_count tracks attacks already taken (0-indexed)
    # map_penalty expects 1-indexed attack_number
    penalty = map_penalty(actor.map_count + 1, equipped.weapon.is_agile)
    bonus = attack_bonus(actor, equipped, penalty)  # type: ignore[arg-type]
    # Apply mid-round Anthem bonus if not already on snapshot
    anthem_atk_delta = _effective_status_bonus_attack(actor, state) - actor.status_bonus_attack
    bonus += anthem_atk_delta
    # Hidden strike: +2 circumstance bonus to attack (AoN: Hidden condition)
    hidden_bonus = 2 if "hidden" in actor.conditions else 0
    bonus += hidden_bonus

    # Effective AC: off-guard from condition OR prone
    effective_off_guard = target.off_guard or target.prone
    effective_ac = target.ac - (2 if effective_off_guard else 0)

    outcomes_d20 = enumerate_d20_outcomes(bonus, effective_ac)

    hit_dmg = damage_avg(actor, equipped)  # type: ignore[arg-type]

    # Two-hand damage die upgrade: if weapon has two_hand_dN trait and is the
    # only item in held_weapons (no shield/second weapon), use the larger die.
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=718)
    for trait in equipped.weapon.traits:
        if trait.startswith("two_hand_"):
            two_hand_die = trait.split("_", 2)[2]  # "d10" from "two_hand_d10"
            if (equipped.weapon.name in actor.held_weapons
                    and len(actor.held_weapons) == 1):
                # Upgrade: replace base die average with two-hand die average
                base_avg = die_average(equipped.weapon.damage_die)
                upgraded_avg = die_average(two_hand_die)
                hit_dmg += (upgraded_avg - base_avg) * equipped.total_damage_dice
            break

    # Apply mid-round Anthem damage bonus
    anthem_dmg_delta = _effective_status_bonus_damage(actor, state) - actor.status_bonus_damage
    hit_dmg += anthem_dmg_delta

    # Apply weakness/resistance if actor has Recalled Knowledge on target.
    # Versatile trait: choose the best damage type per attack.
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=724 — "You choose each time you attack")
    if _has_recalled(actor, action.target_name):
        base_type = equipped.weapon.damage_type.name.lower()
        # Collect all available damage types (base + versatile alternatives)
        available_types = [base_type]
        for trait in equipped.weapon.traits:
            if trait.startswith("versatile_"):
                alt = trait[len("versatile_"):]
                type_map = {"p": "piercing", "s": "slashing", "b": "bludgeoning"}
                if alt in type_map:
                    available_types.append(type_map[alt])
        # Pick the damage type with the best W/R outcome
        best_wr_adjustment = None
        for dt in available_types:
            adj = target.weaknesses.get(dt, 0) - target.resistances.get(dt, 0)
            if best_wr_adjustment is None or adj > best_wr_adjustment:
                best_wr_adjustment = adj
        hit_dmg = max(0.0, hit_dmg + (best_wr_adjustment or 0))

    deadly = equipped.weapon.deadly_die
    deadly_extra = die_average(deadly) if deadly else 0.0
    crit_dmg = hit_dmg * 2 + deadly_extra

    miss_prob = (outcomes_d20.failure + outcomes_d20.critical_failure) / 20
    hit_prob = outcomes_d20.success / 20
    crit_prob = outcomes_d20.critical_success / 20

    outcomes: list[ActionOutcome] = []
    if miss_prob > 0:
        outcomes.append(ActionOutcome(
            probability=miss_prob,
            description=f"Miss ({miss_prob:.0%})",
        ))
    if hit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=hit_prob,
            hp_changes={action.target_name: -hit_dmg},
            description=f"Hit for {hit_dmg:.1f} ({hit_prob:.0%})",
        ))
    if crit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=crit_prob,
            hp_changes={action.target_name: -crit_dmg},
            description=f"Crit for {crit_dmg:.1f} ({crit_prob:.0%})",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    # Focus fire bonus: extra value for concentrating on a wounded enemy.
    # A kill removes all future enemy actions — worth more than spreading damage.
    focus_bonus = 0.0
    if actor.map_count > 0:
        hp_frac = target.current_hp / max(1, target.max_hp)
        if hp_frac < 0.5 and target.damage_dice and "d" in target.damage_dice:
            parts = target.damage_dice.split("d", 1)
            avg_enemy_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
            kill_proximity = 1.0 - hp_frac
            focus_bonus = kill_proximity * avg_enemy_dmg * target.num_attacks_per_turn * 0.3

    # CP7.1 weapon_switch_penalty removed — superseded by INTERACT action cost (CP7.2)

    if focus_bonus > 0:
        outcomes = [
            ActionOutcome(
                probability=o.probability,
                hp_changes=o.hp_changes,
                position_changes=o.position_changes,
                conditions_applied=o.conditions_applied,
                conditions_removed=o.conditions_removed,
                reactions_consumed=o.reactions_consumed,
                score_delta=o.score_delta + focus_bonus,
                description=o.description,
            )
            for o in outcomes
        ]

    # Striking clears Hidden (AoN: Hidden condition — any action except Hide/Sneak/Step).
    # Subtract defensive value of Hidden being lost — beam search weighs whether
    # this Strike is worth giving up the flat check defense.
    if "hidden" in actor.conditions:
        hidden_penalty = _hidden_defensive_value(state)
        outcomes = [
            ActionOutcome(
                probability=o.probability,
                hp_changes=o.hp_changes,
                position_changes=o.position_changes,
                conditions_applied=o.conditions_applied,
                conditions_removed={**o.conditions_removed, action.actor_name: ("hidden",)},
                reactions_consumed=o.reactions_consumed,
                score_delta=o.score_delta - hidden_penalty,
                description=o.description,
            )
            for o in outcomes
        ]

    return ActionResult(action=action, outcomes=tuple(outcomes))


def _evaluate_enemy_strike(
    action: Action, state: RoundState, actor: EnemySnapshot,
) -> ActionResult:
    """Enemy Strike against a PC target.

    Simplification: enemy MAP not tracked per snapshot. Each Strike
    uses raw attack_bonus. This overestimates enemy damage (conservative).
    """
    target = state.pcs.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    if _grid_distance_ft(actor.position, target.position) > 5:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target out of reach")

    if not actor.damage_dice:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Enemy has no modeled offense")

    target_ac = armor_class(target)  # type: ignore[arg-type]
    outcomes_d20 = enumerate_d20_outcomes(actor.attack_bonus, target_ac)

    # Parse damage
    if "d" in actor.damage_dice:
        parts = actor.damage_dice.split("d", 1)
        num_dice = int(parts[0])
        hit_dmg = num_dice * die_average(f"d{parts[1]}") + actor.damage_bonus
    else:
        hit_dmg = float(actor.damage_bonus)
    crit_dmg = hit_dmg * 2

    miss_prob = (outcomes_d20.failure + outcomes_d20.critical_failure) / 20
    hit_prob = outcomes_d20.success / 20
    crit_prob = outcomes_d20.critical_success / 20

    outcomes: list[ActionOutcome] = []
    if miss_prob > 0:
        outcomes.append(ActionOutcome(probability=miss_prob))
    if hit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=hit_prob,
            hp_changes={action.target_name: -hit_dmg},
        ))
    if crit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=crit_prob,
            hp_changes={action.target_name: -crit_dmg},
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-G: TRIP
# ---------------------------------------------------------------------------

def evaluate_trip(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Trip: Athletics check vs Reflex DC. Has attack trait (uses MAP).
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2309)
    (AoN Prone: https://2e.aonprd.com/Conditions.aspx?ID=88)
    Prone value is a CP6 calibration target.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    reach = melee_reach_ft(actor.character)
    if not _is_within_weapon_reach(actor.position, target.position, reach):
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target out of melee reach")

    athletics = skill_bonus(actor.character, Skill.ATHLETICS)
    penalty = map_penalty(actor.map_count + 1, agile=False)
    frightened_pen = -actor.frightened
    effective_bonus = athletics + penalty + frightened_pen

    reflex_dc = 10 + target.saves[SaveType.REFLEX]
    outcomes_d20 = enumerate_d20_outcomes(effective_bonus, reflex_dc)

    crit_s = outcomes_d20.critical_success / 20
    success = outcomes_d20.success / 20
    failure = outcomes_d20.failure / 20
    crit_f = outcomes_d20.critical_failure / 20

    outcomes: list[ActionOutcome] = []
    # Crit success: prone (same as success for Trip)
    if crit_s > 0:
        outcomes.append(ActionOutcome(
            probability=crit_s,
            conditions_applied={action.target_name: ("prone", "off_guard")},
            description=f"Crit success: {action.target_name} prone",
        ))
    if success > 0:
        outcomes.append(ActionOutcome(
            probability=success,
            conditions_applied={action.target_name: ("prone", "off_guard")},
            description=f"Success: {action.target_name} prone",
        ))
    if failure > 0:
        outcomes.append(ActionOutcome(
            probability=failure,
            description="Failure: no effect",
        ))
    if crit_f > 0:
        outcomes.append(ActionOutcome(
            probability=crit_f,
            conditions_applied={action.actor_name: ("prone",)},
            description=f"Crit failure: {action.actor_name} prone",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-H: DISARM
# ---------------------------------------------------------------------------

def evaluate_disarm(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Disarm: Athletics vs Reflex DC. Has attack trait (uses MAP).
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)
    Crit success: -2 penalty approximation (item drop deferred to CP6).
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    reach = melee_reach_ft(actor.character)
    if not _is_within_weapon_reach(actor.position, target.position, reach):
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target out of melee reach")

    athletics = skill_bonus(actor.character, Skill.ATHLETICS)
    penalty = map_penalty(actor.map_count + 1, agile=False)
    frightened_pen = -actor.frightened
    effective_bonus = athletics + penalty + frightened_pen

    reflex_dc = 10 + target.saves[SaveType.REFLEX]
    outcomes_d20 = enumerate_d20_outcomes(effective_bonus, reflex_dc)

    crit_s = outcomes_d20.critical_success / 20
    success = outcomes_d20.success / 20
    failure = outcomes_d20.failure / 20
    crit_f = outcomes_d20.critical_failure / 20

    outcomes: list[ActionOutcome] = []
    if crit_s > 0:
        outcomes.append(ActionOutcome(
            probability=crit_s,
            conditions_applied={action.target_name: ("disarmed",)},
            description=f"Crit success: {action.target_name} disarmed (-2 atk)",
        ))
    if success > 0:
        outcomes.append(ActionOutcome(
            probability=success,
            conditions_applied={action.target_name: ("disarmed",)},
            description=f"Success: {action.target_name} -2 attack penalty",
        ))
    if failure > 0:
        outcomes.append(ActionOutcome(
            probability=failure,
            description="Failure: no effect",
        ))
    if crit_f > 0:
        outcomes.append(ActionOutcome(
            probability=crit_f,
            conditions_applied={action.actor_name: ("off_guard",)},
            description=f"Crit failure: {action.actor_name} off-guard",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-I: DEMORALIZE
# ---------------------------------------------------------------------------

def evaluate_demoralize(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Demoralize: Intimidation vs Will DC. NOT affected by Deceptive Tactics.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2304)
    (AoN Frightened: https://2e.aonprd.com/Conditions.aspx?ID=42)
    LoS simplified: assume LoS if within 30 ft.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    if "demoralize_immune" in target.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"{action.target_name} is immune to Demoralize")

    dist = _grid_distance_ft(actor.position, target.position)
    if dist > 30:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target beyond 30 ft")

    # Always use Intimidation (Deceptive Tactics does NOT apply to Demoralize)
    bonus = skill_bonus(actor.character, Skill.INTIMIDATION) - actor.frightened
    will_dc = 10 + target.saves[SaveType.WILL]
    outcomes_d20 = enumerate_d20_outcomes(bonus, will_dc)

    crit_s = outcomes_d20.critical_success / 20
    success = outcomes_d20.success / 20
    failure = outcomes_d20.failure / 20
    crit_f = outcomes_d20.critical_failure / 20

    # Frightened EV: -N to all enemy rolls × remaining attacks × avg_damage × 0.05
    # Account for existing frightened level — only the IMPROVEMENT matters.
    if target.damage_dice and "d" in target.damage_dice:
        parts = target.damage_dice.split("d", 1)
        avg_enemy_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
    else:
        avg_enemy_dmg = float(target.damage_bonus)
    per_level_ev = target.num_attacks_per_turn * avg_enemy_dmg * 0.05

    # Current frightened level on the target
    current_frightened = max(
        (int(c.split("_")[1]) for c in target.conditions
         if c.startswith("frightened_")),
        default=0,
    )
    # Only the increase over current level has value
    frightened_1_gain = max(0, 1 - current_frightened) * per_level_ev
    frightened_2_gain = max(0, 2 - current_frightened) * per_level_ev

    outcomes: list[ActionOutcome] = []
    if crit_s > 0:
        outcomes.append(ActionOutcome(
            probability=crit_s,
            conditions_applied={action.target_name: ("frightened_2",)},
            score_delta=frightened_2_gain,
            description=f"Crit success: {action.target_name} Frightened 2",
        ))
    if success > 0:
        outcomes.append(ActionOutcome(
            probability=success,
            conditions_applied={action.target_name: ("frightened_1",)},
            score_delta=frightened_1_gain,
            description=f"Success: {action.target_name} Frightened 1",
        ))
    if failure > 0:
        outcomes.append(ActionOutcome(
            probability=failure,
            conditions_applied={action.target_name: ("demoralize_immune",)},
            description=f"Failure: {action.target_name} immune to further Demoralize",
        ))
    if crit_f > 0:
        outcomes.append(ActionOutcome(
            probability=crit_f,
            conditions_applied={
                action.target_name: ("demoralize_immune",),
                action.actor_name: ("frightened_1",),
            },
            score_delta=-per_level_ev,  # actor gets frightened = negative
            description=f"Crit failure: immune + {action.actor_name} Frightened 1",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-J: CREATE_A_DIVERSION
# ---------------------------------------------------------------------------

def evaluate_create_a_diversion(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Create a Diversion: Deception (or Warfare Lore via Deceptive Tactics)
    vs Perception DC. On success: target off-guard vs actor.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
    (AoN Deceptive Tactics: https://2e.aonprd.com/Feats.aspx?ID=7794)
    Next-turn carry-over not scored — CP6 calibration target.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    if "diversion_immune" in target.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"{action.target_name} immune to Create a Diversion")

    # Deceptive Tactics: use Warfare Lore instead of Deception
    if actor.character.has_deceptive_tactics:
        bonus = lore_bonus(actor.character, "Warfare")
    else:
        bonus = skill_bonus(actor.character, Skill.DECEPTION)
    bonus -= actor.frightened

    perception_dc = 10 + target.perception_bonus
    outcomes_d20 = enumerate_d20_outcomes(bonus, perception_dc)

    # Create a Diversion uses success/failure only (no crit success/crit failure effects)
    success_faces = outcomes_d20.critical_success + outcomes_d20.success
    failure_faces = outcomes_d20.failure + outcomes_d20.critical_failure
    success_prob = success_faces / 20
    failure_prob = failure_faces / 20

    # Off-guard EV: +2 to ally attacks ≈ 10% more hits × avg ally damage
    # Estimate 2 remaining ally strikes this round
    off_guard_ev = 2 * 0.10 * 5.0  # rough avg ally damage

    outcomes: list[ActionOutcome] = []
    if success_prob > 0:
        outcomes.append(ActionOutcome(
            probability=success_prob,
            conditions_applied={action.target_name: ("off_guard",)},
            score_delta=off_guard_ev,
            description=f"Success: {action.target_name} off-guard vs {action.actor_name}",
        ))
    if failure_prob > 0:
        outcomes.append(ActionOutcome(
            probability=failure_prob,
            conditions_applied={action.target_name: ("diversion_immune",)},
            description=f"Failure: {action.target_name} immune to further Diversion",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-K: FEINT
# ---------------------------------------------------------------------------

def evaluate_feint(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Feint: Deception (or Warfare Lore via Deceptive Tactics) vs Perception DC.
    Requires melee reach and at least 2 actions remaining.
    No immunity on failure.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    if actor.actions_remaining < 2:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Feint requires at least 2 actions remaining")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Target {action.target_name!r} not found or dead")

    reach = melee_reach_ft(actor.character)
    if not _is_within_weapon_reach(actor.position, target.position, reach):
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target out of melee reach")

    # Deceptive Tactics
    if actor.character.has_deceptive_tactics:
        bonus = lore_bonus(actor.character, "Warfare")
    else:
        bonus = skill_bonus(actor.character, Skill.DECEPTION)
    bonus -= actor.frightened

    perception_dc = 10 + target.perception_bonus
    outcomes_d20 = enumerate_d20_outcomes(bonus, perception_dc)

    crit_s = outcomes_d20.critical_success / 20
    success = outcomes_d20.success / 20
    failure = outcomes_d20.failure / 20
    crit_f = outcomes_d20.critical_failure / 20

    # Off-guard EV for Feint: benefits the actor's next Strike
    feint_ev = 0.10 * 5.0  # +2 attack ≈ 10% more hits × rough avg damage

    outcomes: list[ActionOutcome] = []
    if crit_s > 0:
        outcomes.append(ActionOutcome(
            probability=crit_s,
            conditions_applied={action.target_name: ("off_guard",)},
            score_delta=feint_ev * 2,  # crit: lasts longer
            description=f"Crit success: {action.target_name} off-guard until next turn",
        ))
    if success > 0:
        outcomes.append(ActionOutcome(
            probability=success,
            conditions_applied={action.target_name: ("off_guard",)},
            score_delta=feint_ev,
            description=f"Success: {action.target_name} off-guard vs next attack",
        ))
    if failure > 0:
        outcomes.append(ActionOutcome(
            probability=failure,
            description="Failure: no effect (no immunity)",
        ))
    if crit_f > 0:
        outcomes.append(ActionOutcome(
            probability=crit_f,
            conditions_applied={action.actor_name: ("off_guard",)},
            score_delta=-feint_ev,  # actor gets off-guard = negative
            description=f"Crit failure: {action.actor_name} off-guard vs target",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# 4-L: SHIELD_BLOCK (reaction)
# ---------------------------------------------------------------------------

def evaluate_shield_block(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Shield Block: absorb damage up to shield hardness. C1 greedy policy.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
    (AoN Steel Shield hardness 5: https://2e.aonprd.com/Shields.aspx?ID=3)
    Shield breakage out of scope for CP5.1.3c.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")
    if not actor.shield_raised:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Shield not raised")
    if actor.character.shield is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No shield equipped")
    if not actor.character.has_shield_block:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No Shield Block feat")

    hardness = actor.character.shield.hardness
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            description=f"Shield Block absorbs up to {hardness} damage",
            reactions_consumed={action.actor_name: 1},
        ),),
    )


# ---------------------------------------------------------------------------
# 4-M: INTERCEPT_ATTACK (reaction)
# ---------------------------------------------------------------------------

def evaluate_intercept_attack(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Intercept Attack: Guardian redirects attack to self. C1 greedy policy.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or actor.character.guardian_reactions == 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Not a Guardian")
    if actor.guardian_reactions_available <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No guardian reactions available")

    target_ally = state.pcs.get(action.target_name)
    if target_ally is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target ally not found")

    # Extended range when attacking enemy is Rook's taunted target.
    # (AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)
    taunted_key = f"taunted_by_{action.actor_name.lower().replace(' ', '_')}"
    attacking_enemy = state.enemies.get(action.target_names[0]) if action.target_names else None
    taunted = attacking_enemy is not None and taunted_key in attacking_enemy.conditions
    intercept_range = 15 if taunted else 10

    if _grid_distance_ft(actor.position, target_ally.position) > intercept_range:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Ally not within {intercept_range} ft")

    resistance = guardians_armor_resistance(actor.character.level)
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            description=f"Intercept Attack: {resistance} physical resistance",
            reactions_consumed={action.actor_name: 1},
        ),),
    )


# ---------------------------------------------------------------------------
# 4-N: ACTIVATE_TACTIC
# ---------------------------------------------------------------------------

def evaluate_activate_tactic(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Activate a prepared commander tactic.
    Wraps evaluate_tactic() from pf2e/tactics.py.
    (AoN: https://2e.aonprd.com/Tactics.aspx)
    """
    from pf2e.tactics import FOLIO_TACTICS, PREPARED_TACTICS, evaluate_tactic

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    # Look up tactic definition by display name
    tactic_key = next(
        (k for k, d in FOLIO_TACTICS.items() if d.name == action.tactic_name),
        None,
    )
    if tactic_key is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Unknown tactic: {action.tactic_name!r}")
    if tactic_key not in PREPARED_TACTICS:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Tactic {action.tactic_name!r} not prepared")

    defn = FOLIO_TACTICS[tactic_key]
    if actor.actions_remaining < defn.action_cost:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=(
                               f"{action.tactic_name} costs {defn.action_cost} actions, "
                               f"only {actor.actions_remaining} remaining"
                           ))

    # Build spatial and context
    if spatial is None:
        spatial = _build_mock_spatial(action.actor_name, state)
    ctx = _build_tactic_context(action.actor_name, state, spatial)

    result = evaluate_tactic(defn, ctx)
    if not result.eligible:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=result.ineligibility_reason)

    # Convert TacticResult to ActionResult outcomes
    outcomes: list[ActionOutcome] = []

    if result.expected_damage_dealt > 0 and result.best_target_enemy:
        # Strike Hard! style: EV-folded damage
        outcomes.append(ActionOutcome(
            probability=1.0,
            hp_changes={result.best_target_enemy: -result.expected_damage_dealt},
            description=result.justification,
        ))
    elif result.condition_probabilities:
        # Tactical Takedown style: prone probability
        for target_name, cond_probs in result.condition_probabilities.items():
            for cond, prob in cond_probs.items():
                if prob > 0:
                    outcomes.append(ActionOutcome(
                        probability=prob,
                        conditions_applied={target_name: (cond,)},
                        description=f"{result.justification}",
                    ))
                if 1 - prob > 0:
                    outcomes.append(ActionOutcome(
                        probability=1 - prob,
                        description=f"{action.tactic_name}: {cond} resisted",
                    ))
                break  # One condition per target for now
            break  # One target for now
    else:
        # Defensive tactics (Gather to Me!) — no direct state changes
        outcomes.append(ActionOutcome(
            probability=1.0,
            description=result.justification,
        ))

    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0, description=result.justification))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# CP5.2: ANTHEM
# ---------------------------------------------------------------------------

def _estimate_hit_probability(actor: CombatantSnapshot, state: RoundState) -> float:
    """Rough hit probability for this actor's primary weapon vs average enemy AC."""
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    avg_ac = sum(e.ac for e in living_enemies) / max(1, len(living_enemies)) if living_enemies else 15.0
    # Compute a rough attack bonus from character data
    if actor.character.equipped_weapons:
        eq = actor.character.equipped_weapons[0]
        bonus = attack_bonus(actor, eq, 0)  # type: ignore[arg-type]
    else:
        bonus = 0
    bonus += _effective_status_bonus_attack(actor, state) - actor.status_bonus_attack
    hit_range = 20 - max(0, int(avg_ac) - bonus - 1)
    return max(0.05, min(0.95, hit_range / 20))


def _estimate_avg_strike_damage(actor: CombatantSnapshot, state: RoundState) -> float:
    """Rough average damage per hit for this actor's primary weapon."""
    if actor.character.equipped_weapons:
        eq = actor.character.equipped_weapons[0]
        dmg = damage_avg(actor, eq)  # type: ignore[arg-type]
        dmg += _effective_status_bonus_damage(actor, state) - actor.status_bonus_damage
        return dmg
    return 5.0


def evaluate_anthem(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Cast Courageous Anthem: +1 status to attack, damage, saves vs fear.

    Score = ripple EV across expected ally strikes remaining this round.
    Only one composition can be active at a time. Anthem is Dalai's only
    composition at L1. Composition conflict handling deferred to CP5.3+.
    (AoN: https://2e.aonprd.com/Spells.aspx — Courageous Anthem)
    (AoN: https://2e.aonprd.com/Traits.aspx — Composition)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or not actor.character.has_courageous_anthem:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No Courageous Anthem")
    if state.anthem_active:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Anthem already active")

    anthem_ev = 0.0
    for ally_name, ally_snap in state.pcs.items():
        if ally_name == action.actor_name or ally_snap.current_hp <= 0:
            continue
        # 60-ft emanation range
        if _grid_distance_ft(actor.position, ally_snap.position) > 60:
            continue
        remaining_strikes = min(ally_snap.actions_remaining, 2)
        if remaining_strikes <= 0:
            continue
        hit_prob = _estimate_hit_probability(ally_snap, state)
        avg_dmg = _estimate_avg_strike_damage(ally_snap, state)
        # +1 attack: ~5% more hits × full damage
        # +1 damage: existing hit prob × 1 more per hit
        # CP6 calibration target: remaining_strikes estimation.
        anthem_ev += remaining_strikes * (0.05 * avg_dmg + hit_prob * 1.0)

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={action.actor_name: ("anthem_active",)},
            score_delta=anthem_ev,
            description=f"Cast Courageous Anthem (EV +{anthem_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.2: SOOTHE
# ---------------------------------------------------------------------------

def evaluate_soothe(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Cast Soothe on the most wounded ally. 2 actions, 1d10+4 HP (avg 9.5).

    One cast per encounter at L1 (tracked via 'soothe_used' condition).
    (AoN: https://2e.aonprd.com/Spells.aspx — Soothe)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or not actor.character.has_soothe:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No Soothe spell")
    if "soothe_used" in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Soothe already used this encounter")
    if actor.actions_remaining < 2:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Soothe requires 2 actions")

    avg_heal = die_average("d10") + 4  # 9.5
    best_target: str = ""
    best_ev = 0.0

    for ally_name, ally_snap in state.pcs.items():
        if ally_snap.current_hp <= 0:
            continue
        ally_max = max_hp(ally_snap.character)
        if ally_max <= 0 or ally_snap.current_hp >= ally_max:
            continue
        if _grid_distance_ft(actor.position, ally_snap.position) > 30:
            continue
        effective_heal = min(avg_heal, ally_max - ally_snap.current_hp)
        wound_factor = 1.0 + (1.0 - ally_snap.current_hp / ally_max)
        # Support-role multiplier. CP6 refactor target: use role_weight.
        from sim.search import role_multiplier
        ev = effective_heal * wound_factor * role_multiplier(ally_name)
        if ev > best_ev:
            best_ev = ev
            best_target = ally_name

    if not best_target:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No wounded allies in range")

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            hp_changes={best_target: avg_heal},
            conditions_applied={action.actor_name: ("soothe_used",)},
            description=f"Soothe {best_target} (heals ~{avg_heal:.1f} HP)",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.2: MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH
# ---------------------------------------------------------------------------

def evaluate_mortar_aim(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Aim Light Mortar at target. Requires mortar deployed.
    (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or not actor.character.has_light_mortar:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No Light Mortar")
    if "mortar_deployed" not in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Mortar not deployed")
    if "mortar_aimed" in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Mortar already aimed")

    # Chain credit: estimate LAUNCH payoff so beam doesn't prune mortar line.
    # Discount 0.3 (additive accumulation — avoid inflating total).
    # CP7 calibration target.
    from pf2e.combat_math import SiegeWeapon, expected_aoe_damage, EnemyTarget
    from pf2e.types import DamageType
    mortar = SiegeWeapon(name="Light Mortar", damage_die="d6", base_damage_dice=2,
                         damage_type=DamageType.BLUDGEONING, save_type=SaveType.REFLEX,
                         aoe_shape="burst", aoe_radius_ft=10, range_increment=120)
    enemy_targets = [
        EnemyTarget(name=e.name, ac=e.ac, saves=e.saves)
        for e in state.enemies.values() if e.current_hp > 0
    ]
    chain_credit = expected_aoe_damage(actor.character, mortar, enemy_targets) * 0.3 if enemy_targets else 0.0

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={action.actor_name: ("mortar_aimed",)},
            score_delta=chain_credit,
            description=f"Aim Light Mortar (chain credit {chain_credit:.2f})",
        ),),
    )


def evaluate_mortar_load(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Load Light Mortar. Requires mortar aimed.
    (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not found")
    if "mortar_aimed" not in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Must aim before loading")
    if "mortar_loaded" in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Mortar already loaded")

    # Chain credit: one step closer to LAUNCH. Higher discount than AIM.
    from pf2e.combat_math import SiegeWeapon, expected_aoe_damage, EnemyTarget
    from pf2e.types import DamageType
    mortar = SiegeWeapon(name="Light Mortar", damage_die="d6", base_damage_dice=2,
                         damage_type=DamageType.BLUDGEONING, save_type=SaveType.REFLEX,
                         aoe_shape="burst", aoe_radius_ft=10, range_increment=120)
    enemy_targets = [
        EnemyTarget(name=e.name, ac=e.ac, saves=e.saves)
        for e in state.enemies.values() if e.current_hp > 0
    ]
    chain_credit = expected_aoe_damage(actor.character, mortar, enemy_targets) * 0.35 if enemy_targets else 0.0

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={action.actor_name: ("mortar_loaded",)},
            score_delta=chain_credit,
            description=f"Load Light Mortar (chain credit {chain_credit:.2f})",
        ),),
    )


def evaluate_mortar_launch(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Fire Light Mortar. 2d6 bludgeoning in 10-ft burst, Reflex vs class DC.
    Clears aimed+loaded conditions. Has attack trait (increments MAP).
    (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
    """
    from pf2e.combat_math import SiegeWeapon, expected_aoe_damage, EnemyTarget
    from pf2e.types import DamageType

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not found")
    if "mortar_aimed" not in actor.conditions or "mortar_loaded" not in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Mortar not aimed and loaded")

    mortar = SiegeWeapon(
        name="Light Mortar",
        damage_die="d6",
        base_damage_dice=2,
        damage_type=DamageType.BLUDGEONING,
        save_type=SaveType.REFLEX,
        aoe_shape="burst",
        aoe_radius_ft=10,
        range_increment=120,
    )

    # --- Math delegated to save_damage.py (CP10.4.4) ---
    from pf2e.save_damage import aoe_enemy_ev, aoe_friendly_fire_ev
    from pf2e.combat_math import class_dc as _class_dc

    dc = _class_dc(actor.character)
    dice = mortar.dice_at_level(actor.character.level)
    base_dmg = dice * die_average(mortar.damage_die)

    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    if not living_enemies:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No living enemies")

    enemy_score = aoe_enemy_ev(dc, mortar.save_type, base_dmg, living_enemies)

    # Friendly fire: PF2e AoE hits allies within the burst.
    # Proximity proxy: ally within 5 ft of any living enemy = in burst.
    # Burst geometry deferred to CP10.6.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2384 — AoE hits all creatures)
    allies_in_burst: list = []
    for ally_name, ally_snap in state.pcs.items():
        if ally_snap.current_hp <= 0 or ally_name == action.actor_name:
            continue
        for enemy in state.enemies.values():
            if (enemy.current_hp > 0
                    and _grid_distance_ft(ally_snap.position, enemy.position) <= 5):
                allies_in_burst.append(ally_snap)
                break  # count each ally once

    ff_penalty = aoe_friendly_fire_ev(
        dc, mortar.save_type, base_dmg, allies_in_burst)
    score = enemy_score - ff_penalty
    if score <= 0.0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Friendly fire exceeds enemy damage")

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            hp_changes={e.name: -enemy_score / len(living_enemies)
                        for e in living_enemies},
            conditions_removed={action.actor_name: ("mortar_aimed", "mortar_loaded")},
            description=f"Launch Mortar (EV {score:.2f}, FF {ff_penalty:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.2: TAUNT
# ---------------------------------------------------------------------------

def evaluate_taunt(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Taunt an enemy. Automatic, no check. -1 circumstance if enemy targets
    allies without targeting Rook, plus off-guard until their next turn.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=3304)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None or not actor.character.has_taunt:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No Taunt class feature")
    if any(c.startswith("taunting_") for c in actor.conditions):
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Already taunting an enemy")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Invalid or dead target")
    if _grid_distance_ft(actor.position, target.position) > 30:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Target beyond 30 ft")

    # Score: EV of -1 circumstance + off-guard when enemy targets allies
    # Use all living PCs as potentially threatened (not just adjacent)
    num_pcs = max(1, sum(1 for p in state.pcs.values() if p.current_hp > 0))
    p_targets_ally = 1.0 - (1.0 / num_pcs)
    remaining_attacks = target.num_attacks_per_turn

    # Rough enemy damage per attack
    if target.damage_dice and "d" in target.damage_dice:
        parts = target.damage_dice.split("d", 1)
        avg_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
    else:
        avg_dmg = float(target.damage_bonus)

    # -1 circumstance ≈ 5% fewer hits
    penalty_ev = p_targets_ally * remaining_attacks * avg_dmg * 0.05
    # Off-guard ≈ +10% hit chance for allies × rough ally damage
    off_guard_ev = p_targets_ally * remaining_attacks * 0.10 * 5.0
    taunt_ev = penalty_ev + off_guard_ev

    taunted_key = f"taunted_by_{action.actor_name.lower().replace(' ', '_')}"
    taunting_key = f"taunting_{action.target_name}"

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={
                action.target_name: (taunted_key,),
                action.actor_name: (taunting_key,),
            },
            score_delta=taunt_ev,
            description=f"Taunt {action.target_name} (EV +{taunt_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.3: RECALL_KNOWLEDGE
# ---------------------------------------------------------------------------

RECALL_KNOWLEDGE_DC = 15  # CP5.3 simplification. CP6: use creature-level DC table.


def evaluate_recall_knowledge(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Recall Knowledge about an enemy to reveal weaknesses/resistances.

    Society for humanoids. On success, actor gains recalled tag enabling
    W/R-adjusted damage in subsequent STRIKE evaluations.
    (AoN: https://2e.aonprd.com/Skills.aspx — Recall Knowledge)
    DC 15 flat for CP5.3. CP6: creature-level DC table.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Invalid or dead target")

    tag = "recalled_" + action.target_name.lower().replace(" ", "_")
    if tag in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=f"Already recalled {action.target_name}")

    # Society for humanoids (bandits). CP6: route by creature type.
    rk_bonus = skill_bonus(actor.character, Skill.SOCIETY)
    p_success = _d20_success_probability(rk_bonus, RECALL_KNOWLEDGE_DC)

    # Score = EV gain from W/R insight on remaining PARTY strikes.
    # Two components:
    #   weakness_ev: bonus damage from hitting weaknesses
    #   avoidance_ev: damage saved by switching away from resisted weapons
    if not target.weaknesses and not target.resistances:
        recall_ev = 0.0
    else:
        weakness_ev = 0.0
        avoidance_ev = 0.0

        for pc_name, pc_snap in state.pcs.items():
            if pc_snap.current_hp <= 0:
                continue
            remaining_strikes = min(pc_snap.actions_remaining, 2)
            if remaining_strikes <= 0:
                continue

            melee_weapons = [eq for eq in pc_snap.character.equipped_weapons
                             if eq.weapon.is_melee]
            if not melee_weapons:
                continue

            # Find the primary weapon (first in tuple — actively held)
            primary = melee_weapons[0]
            primary_type = primary.weapon.damage_type.name.lower()
            primary_dmg = die_average(primary.weapon.damage_die) + 0.0

            # Weakness EV: bonus from exploiting weakness with best weapon
            for eq in melee_weapons:
                dmg_type = eq.weapon.damage_type.name.lower()
                advantage = target.weaknesses.get(dmg_type, 0) - target.resistances.get(dmg_type, 0)
                if advantage > 0:
                    weakness_ev += advantage * remaining_strikes

            # Avoidance EV: knowing about resistance lets the search make
            # better decisions — either switching to a non-resisted weapon
            # or redirecting attacks to other enemies/actions.
            # Value = resistance amount × remaining strikes for any PC
            # whose primary weapon type is resisted.
            primary_resistance = target.resistances.get(primary_type, 0)
            if primary_resistance > 0:
                # Check if PC has a non-resisted alternative weapon
                best_alt_dmg = 0.0
                for eq in melee_weapons:
                    alt_type = eq.weapon.damage_type.name.lower()
                    if target.resistances.get(alt_type, 0) == 0:
                        best_alt_dmg = max(best_alt_dmg, die_average(eq.weapon.damage_die))
                # Also consider spells as alternatives
                for slug in pc_snap.character.known_spells:
                    from pf2e.spells import SPELL_REGISTRY
                    defn = SPELL_REGISTRY.get(slug)
                    if defn and defn.damage_type:
                        spell_type = defn.damage_type.name.lower()
                        if target.resistances.get(spell_type, 0) == 0:
                            spell_dmg = defn.damage_dice * die_average(defn.damage_die) + defn.damage_bonus
                            best_alt_dmg = max(best_alt_dmg, spell_dmg)

                if best_alt_dmg > 0:
                    # Can switch: gain = alt_dmg - (primary_dmg - resistance)
                    resisted_dmg = max(0.0, primary_dmg - primary_resistance)
                    avoidance_ev += max(0.0, best_alt_dmg - resisted_dmg) * remaining_strikes
                else:
                    # No non-resisted alternative: info still valuable for
                    # redirecting attacks to other enemies. Value = resistance
                    # amount (the search will deprioritize this target).
                    avoidance_ev += primary_resistance * remaining_strikes

        # Also check mortar (bludgeoning) for weakness
        mortar_advantage = target.weaknesses.get("bludgeoning", 0) - target.resistances.get("bludgeoning", 0)
        if mortar_advantage > 0:
            weakness_ev += mortar_advantage

        # Time value: weight by enemy HP fraction. High HP = more future turns
        # to act on the information. Range: 1.0 (near dead) to 3.0 (full HP).
        hp_fraction = target.current_hp / max(1, target.max_hp)
        future_turns_weight = max(1.0, 1.0 + hp_fraction * 2.0)

        recall_ev = p_success * (weakness_ev + avoidance_ev) * future_turns_weight

    # Share knowledge with ALL living party members — in PF2e, the recalling
    # character communicates what they learn to allies (standard table play).
    # Each PC gets the recalled tag so their Strike evaluators apply W/R.
    all_pc_tags: dict[str, tuple[str, ...]] = {}
    for pc_name, pc_snap in state.pcs.items():
        if pc_snap.current_hp > 0:
            all_pc_tags[pc_name] = (tag,)

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied=all_pc_tags,
            score_delta=recall_ev,
            description=f"Recall Knowledge: {action.target_name} (EV {recall_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.3: HIDE
# ---------------------------------------------------------------------------

def _hidden_defensive_value(state: RoundState) -> float:
    """Compute the defensive EV of being Hidden for one character.

    Hidden imposes a DC 11 flat check (~45% miss) on enemy attacks.
    Value = (attacks targeting this PC) × 0.45 × avg damage per attack.
    Approximation: enemies spread attacks evenly across living PCs.
    """
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    if not living_enemies:
        return 0.0
    living_pcs = sum(1 for pc in state.pcs.values() if pc.current_hp > 0)
    if living_pcs <= 0:
        return 0.0

    total_attacks = sum(e.num_attacks_per_turn for e in living_enemies)
    attacks_on_me = total_attacks / living_pcs

    avg_dmg_per_attack = 0.0
    for e in living_enemies:
        if e.damage_dice and "d" in e.damage_dice:
            parts = e.damage_dice.split("d", 1)
            avg_dmg_per_attack += (
                int(parts[0]) * die_average(f"d{parts[1]}") + e.damage_bonus
            )
        elif e.damage_bonus:
            avg_dmg_per_attack += e.damage_bonus
    avg_dmg_per_attack /= max(1, len(living_enemies))

    return attacks_on_me * 0.45 * avg_dmg_per_attack


def evaluate_hide(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Attempt to Hide from enemies. Requires cover (proxy: not adjacent to enemy).

    On success: Hidden condition (off-guard to enemies, DC 11 flat check to target).
    (AoN: https://2e.aonprd.com/Actions.aspx — Hide)
    (AoN: https://2e.aonprd.com/Conditions.aspx — Hidden)
    Cover proxy is CP5.3 simplification. Full LoS deferred to CP6.
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")
    if "hidden" in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Already hidden")

    # Cover proxy: ineligible if any living enemy is adjacent
    for enemy in state.enemies.values():
        if enemy.current_hp > 0 and _grid_distance_ft(actor.position, enemy.position) <= 5:
            return ActionResult(action=action, eligible=False,
                               ineligibility_reason="No cover — adjacent to enemy")

    stealth = skill_bonus(actor.character, Skill.STEALTH)
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    if not living_enemies:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No enemies to hide from")

    avg_perc_dc = sum(10 + e.perception_bonus for e in living_enemies) / len(living_enemies)
    p_success = _d20_success_probability(stealth, int(avg_perc_dc))

    # Score: attack bonus from Hidden (+2 to attack rolls) + flat check defense.
    # Only count attack bonus if actor will plausibly use attack-roll actions.
    # Auto-hit spells (Force Barrage) and save spells (Fear) don't benefit.
    # (AoN: Hidden gives +2 circumstance bonus to attack rolls only)
    remaining_actions = min(actor.actions_remaining - 1, 2)

    # Count how many remaining actions would benefit from hidden attack bonus:
    # melee strikes (if enemies in reach) and attack-roll spells (Needle Darts)
    attack_roll_actions = 0
    if remaining_actions > 0:
        has_melee_target = any(
            _grid_distance_ft(actor.position, e.position) <= melee_reach_ft(actor.character)
            for e in state.enemies.values() if e.current_hp > 0
        )
        if has_melee_target:
            attack_roll_actions = remaining_actions
        else:
            # Check if actor has attack-roll spells (Attack trait)
            from pf2e.spells import SPELL_REGISTRY, SpellPattern
            for slug in actor.character.known_spells:
                defn = SPELL_REGISTRY.get(slug)
                if defn and defn.pattern == SpellPattern.ATTACK_ROLL:
                    # Each attack-roll spell costs defn.action_cost actions
                    attack_roll_actions = remaining_actions // defn.action_cost
                    break

    avg_dmg = 5.0
    if actor.character.equipped_weapons:
        avg_dmg = damage_avg(actor, actor.character.equipped_weapons[0])  # type: ignore[arg-type]

    off_guard_ev = attack_roll_actions * 0.10 * avg_dmg
    flat_check_ev = _hidden_defensive_value(state)

    hide_ev = p_success * (off_guard_ev + flat_check_ev)

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={action.actor_name: ("hidden",)},
            score_delta=hide_ev,
            description=f"Hide (EV {hide_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.3: SNEAK
# ---------------------------------------------------------------------------

def evaluate_sneak(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Move while maintaining Hidden. Half Speed. Stealth vs Perception.

    Must already be Hidden. On failure: Hidden lost.
    (AoN: https://2e.aonprd.com/Actions.aspx — Sneak)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")
    if "hidden" not in actor.conditions:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Must be Hidden to Sneak")
    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="No target position")

    stealth = skill_bonus(actor.character, Skill.STEALTH)
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    avg_perc_dc = sum(10 + e.perception_bonus for e in living_enemies) / max(1, len(living_enemies))
    p_success = _d20_success_probability(stealth, int(avg_perc_dc))

    outcomes: list[ActionOutcome] = []
    if p_success > 0:
        outcomes.append(ActionOutcome(
            probability=p_success,
            position_changes={action.actor_name: action.target_position},
            description=f"Sneak to {action.target_position} — remain hidden",
        ))
    if 1 - p_success > 0:
        outcomes.append(ActionOutcome(
            probability=1 - p_success,
            position_changes={action.actor_name: action.target_position},
            conditions_removed={action.actor_name: ("hidden",)},
            description=f"Sneak to {action.target_position} — detected",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# CP5.3: SEEK
# ---------------------------------------------------------------------------

def evaluate_seek(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Attempt to locate Hidden enemies. Always eligible. Scores 0 if none hidden.

    (AoN: https://2e.aonprd.com/Actions.aspx — Seek)
    """
    from pf2e.combat_math import perception_bonus as _perception_bonus

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")

    hidden_enemies = [e for e in state.enemies.values()
                      if e.current_hp > 0 and "hidden" in e.conditions]
    seek_ev = 0.0
    if hidden_enemies:
        perc = _perception_bonus(actor.character)
        p_success = _d20_success_probability(perc, 15)
        # Value of revealing: remove flat check defense
        for e in hidden_enemies:
            avg_dmg = (die_average(f"d{e.damage_dice.split('d')[1]}" if 'd' in e.damage_dice else "d4")
                       * int(e.damage_dice.split('d')[0] if 'd' in e.damage_dice else "1")
                       + e.damage_bonus) if e.damage_dice else 0
            seek_ev += p_success * 0.45 * avg_dmg * e.num_attacks_per_turn

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            description=f"Seek ({len(hidden_enemies)} hidden, EV {seek_ev:.2f})",
        ),),
    )


# ---------------------------------------------------------------------------
# CP5.3: AID
# ---------------------------------------------------------------------------

AID_DC = 15


def evaluate_aid(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Prepare to Aid an ally. 1 action, reaction next turn. 0.5 discount.

    Success: +1 circumstance to ally's check. Crit success: +2.
    Crit failure: -1 penalty.
    (AoN: https://2e.aonprd.com/Actions.aspx — Aid)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not a PC")
    target = state.pcs.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Invalid or dead ally")
    if action.actor_name == action.target_name:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Cannot Aid yourself")

    # Use best skill bonus for Aid roll
    best_bonus = max(
        skill_bonus(actor.character, s) for s in Skill
    )
    p_success = _d20_success_probability(best_bonus, AID_DC)
    p_crit = _d20_crit_success_probability(best_bonus, AID_DC)
    p_crit_fail = _d20_crit_fail_probability(best_bonus, AID_DC)

    # Rough ally avg damage for bonus EV
    ally_avg_dmg = 5.0
    if target.character.equipped_weapons:
        ally_avg_dmg = damage_avg(target, target.character.equipped_weapons[0])  # type: ignore[arg-type]

    bonus_ev = (p_success * 0.05 + p_crit * 0.10 - p_crit_fail * 0.05) * ally_avg_dmg
    aid_ev = bonus_ev * 0.5  # next-round discount

    aiding_tag = f"aiding_{action.target_name.lower().replace(' ', '_')}"
    aided_tag = f"aided_by_{action.actor_name.lower().replace(' ', '_')}"

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_applied={
                action.actor_name: (aiding_tag,),
                action.target_name: (aided_tag,),
            },
            score_delta=aid_ev,
            description=f"Aid {action.target_name} (EV {aid_ev:.2f}, discounted)",
        ),),
    )


# ---------------------------------------------------------------------------
# CP6: STAND
# ---------------------------------------------------------------------------

def evaluate_stand(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Stand up from Prone. Costs 1 action.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2323)
    """
    actor = state.pcs.get(action.actor_name) or state.enemies.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Actor not found")
    if not actor.prone:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Not prone")

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            conditions_removed={action.actor_name: ("prone",)},
            description="Stand up (Prone cleared)",
        ),),
    )


# ---------------------------------------------------------------------------
# Hand state: INTERACT and RELEASE (CP7.2)
# ---------------------------------------------------------------------------

def evaluate_interact(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Draw a stowed weapon. Costs 1 action.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2151 — Interact)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not found")

    weapon_name = action.weapon_name
    weapon_exists = any(
        eq.weapon.name == weapon_name for eq in actor.character.equipped_weapons
    )
    if not weapon_exists:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"{weapon_name!r} not equipped")
    if weapon_name in actor.held_weapons:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"{weapon_name} already held")

    eq = next(e for e in actor.character.equipped_weapons if e.weapon.name == weapon_name)
    hands_needed = eq.weapon.hands
    hands_free = 2 - len(actor.held_weapons)
    if hands_free < hands_needed:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=(
                                f"Drawing {weapon_name} needs {hands_needed} hand(s); "
                                f"only {hands_free} free"
                            ))

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            held_weapons_add=(weapon_name,),
            actor_name=action.actor_name,
            description=f"Draw {weapon_name}",
        ),),
    )


def evaluate_release(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Release a held item. Free action (0 cost, no reactions).

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2150 — Release)
    """
    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not found")

    item_name = action.weapon_name
    if item_name not in actor.held_weapons:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"{item_name} not currently held")

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            held_weapons_remove=(item_name,),
            actor_name=action.actor_name,
            description=f"Release {item_name}",
        ),),
    )


# ---------------------------------------------------------------------------
# Spell chassis evaluator (CP5.4)
# ---------------------------------------------------------------------------

def evaluate_spell(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Evaluate a spell cast using the SpellDefinition chassis.

    action.tactic_name holds the spell slug.
    action.target_name is the primary target.
    action.action_cost is the actions spent (1-3 for scaling spells).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2302)
    """
    from pf2e.spells import SPELL_REGISTRY, SpellPattern

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not found")

    slug = action.tactic_name
    defn = SPELL_REGISTRY.get(slug)
    if defn is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"Unknown spell: {slug!r}")

    if slug not in actor.character.known_spells:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"Spell {slug!r} not known")

    # Spell slot resource check (CP7.2)
    if defn.uses_spell_slot:
        slot_key = f"spell_slot_{defn.spell_slot_rank}"
        remaining = actor.resources.get(slot_key, 0)
        if remaining <= 0:
            return ActionResult(
                action=action, eligible=False,
                ineligibility_reason=f"No {slot_key} remaining",
            )

    if defn.pattern == SpellPattern.AUTO_HIT_DAMAGE:
        result = _evaluate_auto_hit_spell(action, state, actor, defn)
    elif defn.pattern == SpellPattern.SAVE_OR_CONDITION:
        from pf2e.save_condition import evaluate_condition_spell
        result = evaluate_condition_spell(action, state, actor, defn)
    elif defn.pattern == SpellPattern.ATTACK_ROLL:
        from pf2e.strike import evaluate_spell_attack_roll
        result = evaluate_spell_attack_roll(action, state, actor, defn)
    elif defn.pattern == SpellPattern.SAVE_FOR_DAMAGE:
        from pf2e.save_damage import evaluate_save_damage_spell
        result = evaluate_save_damage_spell(action, state, actor, defn)
    else:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason=f"Unimplemented: {defn.pattern}")

    # Casting a hostile spell breaks Hidden condition.
    # Subtract the defensive value being lost — the beam search must weigh
    # whether this spell is worth giving up the Hidden flat check defense.
    # (AoN: Hidden — "you become observed" after a hostile action)
    if result.eligible and "hidden" in actor.conditions:
        hidden_penalty = _hidden_defensive_value(state)
        result = ActionResult(
            action=result.action,
            outcomes=tuple(
                ActionOutcome(
                    probability=o.probability,
                    hp_changes=o.hp_changes,
                    position_changes=o.position_changes,
                    conditions_applied=o.conditions_applied,
                    conditions_removed={
                        **o.conditions_removed,
                        action.actor_name: ("hidden",),
                    },
                    reactions_consumed=o.reactions_consumed,
                    score_delta=o.score_delta - hidden_penalty,
                    description=o.description,
                )
                for o in result.outcomes
            ),
        )

    # Apply spell slot cost to all outcomes
    if result.eligible and defn.uses_spell_slot:
        slot_key = f"spell_slot_{defn.spell_slot_rank}"
        result = ActionResult(
            action=result.action,
            outcomes=tuple(
                ActionOutcome(
                    probability=o.probability,
                    hp_changes=o.hp_changes,
                    position_changes=o.position_changes,
                    conditions_applied=o.conditions_applied,
                    conditions_removed=o.conditions_removed,
                    reactions_consumed=o.reactions_consumed,
                    score_delta=o.score_delta,
                    description=o.description,
                    resource_changes={slot_key: -1},
                    actor_name=action.actor_name,
                    held_weapons_add=o.held_weapons_add,
                    held_weapons_remove=o.held_weapons_remove,
                )
                for o in result.outcomes
            ),
        )

    return result


def _evaluate_auto_hit_spell(
    action: Action, state: RoundState,
    actor: CombatantSnapshot, defn: "SpellDefinition",
) -> ActionResult:
    """Auto-hit damage spell (Force Barrage pattern).

    No roll — damage applies automatically. Scales with actions spent.
    (AoN: https://2e.aonprd.com/Spells.aspx?ID=1536)
    """
    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No valid target")

    actions_spent = action.action_cost
    missiles = defn.missiles_per_action * actions_spent
    dmg_per_missile = die_average(defn.damage_die) + defn.damage_bonus
    total_dmg = missiles * dmg_per_missile

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            hp_changes={action.target_name: -total_dmg},
            description=f"{defn.name} ({missiles} missiles): {total_dmg:.1f} force",
        ),),
    )


def _evaluate_condition_spell(
    action: Action, state: RoundState,
    actor: CombatantSnapshot, defn: "SpellDefinition",
) -> ActionResult:
    """Non-basic save, condition outcomes (Fear pattern).

    Each degree of success produces a distinct condition.
    EV is computed as score_delta from the condition's combat impact.
    (AoN: https://2e.aonprd.com/Spells.aspx?ID=1524)
    """
    from pf2e.combat_math import class_dc

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No valid target")

    dc = class_dc(actor.character)
    save_bonus = target.saves.get(defn.save_type, 0)
    outcomes_d20 = enumerate_d20_outcomes(save_bonus, dc)

    crit_s_prob = outcomes_d20.critical_success / 20
    success_prob = outcomes_d20.success / 20
    failure_prob = outcomes_d20.failure / 20
    crit_f_prob = outcomes_d20.critical_failure / 20

    # Map degree labels to d20 probabilities
    degree_probs = {
        "crit_success": crit_s_prob,
        "success": success_prob,
        "failure": failure_prob,
        "crit_failure": crit_f_prob,
        "crit_failure_fleeing": crit_f_prob,  # same prob as crit_failure
    }

    # Compute EV of frightened condition on an enemy:
    # Frightened N reduces enemy checks/DCs by N.
    # - Reduces enemy attack rolls → fewer hits → damage prevented
    # - Reduces enemy AC (it's a DC) → better ally hit rates → extra damage
    # Approximate as: frightened_level * 0.05 * enemy_attacks * avg_damage * 2
    # (×2 accounts for both offensive reduction and defensive reduction)
    def _frightened_ev(level: int) -> float:
        if level == 0 or not target.damage_dice:
            return 0.0
        if "d" in target.damage_dice:
            parts = target.damage_dice.split("d", 1)
            avg_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
        else:
            avg_dmg = float(target.damage_bonus)
        # Each point of frightened ≈ 5% swing per attack × both offense+defense
        return level * 0.05 * target.num_attacks_per_turn * avg_dmg * 2

    outcomes: list[ActionOutcome] = []

    # Build one outcome per meaningful degree
    # Crit success: no effect
    if crit_s_prob > 0:
        outcomes.append(ActionOutcome(
            probability=crit_s_prob,
            description=f"{defn.name}: no effect (crit success)",
        ))

    # Success: frightened 1
    if success_prob > 0:
        fev = _frightened_ev(1)
        outcomes.append(ActionOutcome(
            probability=success_prob,
            conditions_applied={action.target_name: ("frightened_1",)},
            score_delta=fev,
            description=f"{defn.name}: frightened 1 (EV {fev:.1f})",
        ))

    # Failure: frightened 2
    if failure_prob > 0:
        fev = _frightened_ev(2)
        outcomes.append(ActionOutcome(
            probability=failure_prob,
            conditions_applied={action.target_name: ("frightened_2",)},
            score_delta=fev,
            description=f"{defn.name}: frightened 2 (EV {fev:.1f})",
        ))

    # Crit failure: frightened 3 + fleeing 1 round
    if crit_f_prob > 0:
        fev = _frightened_ev(3)
        # Fleeing removes the enemy from combat for 1 round — high value
        flee_ev = target.num_attacks_per_turn * (
            die_average(f"d{target.damage_dice.split('d')[1]}")
            + target.damage_bonus
            if "d" in target.damage_dice else target.damage_bonus
        ) if target.damage_dice else 0.0
        outcomes.append(ActionOutcome(
            probability=crit_f_prob,
            conditions_applied={action.target_name: ("frightened_3", "fleeing_1")},
            score_delta=fev + flee_ev,
            description=f"{defn.name}: frightened 3 + fleeing (EV {fev + flee_ev:.1f})",
        ))

    return ActionResult(action=action, outcomes=tuple(outcomes))


def _evaluate_attack_roll_spell(
    action: Action, state: RoundState,
    actor: CombatantSnapshot, defn: "SpellDefinition",
) -> ActionResult:
    """Spell attack roll vs target AC. Crit doubles damage.

    For cantrips with the Attack trait: MAP applies if the caster
    has already made an attack this turn (map_count > 0).
    (AoN: https://2e.aonprd.com/Spells.aspx?ID=1375 — Needle Darts)
    """
    from pf2e.combat_math import spell_attack_bonus

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No valid target")

    # MAP applies for Attack-trait spells (never agile)
    penalty = map_penalty(actor.map_count + 1, agile=False)
    atk_bonus = spell_attack_bonus(actor.character) + penalty

    # Off-guard/prone reduce effective AC
    effective_ac = target.ac - (2 if (target.off_guard or target.prone) else 0)

    outcomes_d20 = enumerate_d20_outcomes(atk_bonus, effective_ac)

    base_dmg = defn.damage_dice * die_average(defn.damage_die) + defn.damage_bonus
    crit_dmg = base_dmg * 2
    # Phase C: Needle Darts crit adds 1 persistent bleed damage

    miss_prob = (outcomes_d20.failure + outcomes_d20.critical_failure) / 20
    hit_prob = outcomes_d20.success / 20
    crit_prob = outcomes_d20.critical_success / 20

    outcomes: list[ActionOutcome] = []
    if miss_prob > 0:
        outcomes.append(ActionOutcome(
            probability=miss_prob,
            description=f"{defn.name}: miss",
        ))
    if hit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=hit_prob,
            hp_changes={action.target_name: -base_dmg},
            description=f"{defn.name}: hit {base_dmg:.1f}",
        ))
    if crit_prob > 0:
        outcomes.append(ActionOutcome(
            probability=crit_prob,
            hp_changes={action.target_name: -crit_dmg},
            description=f"{defn.name}: crit {crit_dmg:.1f}",
        ))

    return ActionResult(action=action, outcomes=tuple(outcomes))


def _evaluate_save_damage_spell(
    action: Action, state: RoundState,
    actor: CombatantSnapshot, defn: "SpellDefinition",
) -> ActionResult:
    """Basic save for damage. Crit success=0, success=half, fail=full, crit fail=double.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2296)
    """
    from pf2e.combat_math import class_dc

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No valid target")

    dice = defn.damage_dice
    if defn.scales_with_actions:
        # Not currently used but future-proofing
        extra_actions = action.action_cost - 1
        dice += extra_actions * 4  # generic scaling placeholder
    base_dmg = dice * die_average(defn.damage_die) + defn.damage_bonus

    dc = class_dc(actor.character)
    save_mod = target.saves.get(defn.save_type, 0)
    outcomes_d20 = enumerate_d20_outcomes(save_mod, dc)

    ev = (
        (outcomes_d20.critical_failure / 20) * base_dmg * 2
        + (outcomes_d20.failure / 20) * base_dmg
        + (outcomes_d20.success / 20) * base_dmg * 0.5
    )

    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            hp_changes={action.target_name: -ev},
            description=f"{defn.name}: EV {ev:.2f}",
        ),),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ACTION_EVALUATORS: dict[ActionType, Callable[..., ActionResult]] = {
    ActionType.END_TURN: evaluate_end_turn,
    ActionType.PLANT_BANNER: evaluate_plant_banner,
    ActionType.RAISE_SHIELD: evaluate_raise_shield,
    ActionType.STEP: evaluate_step,
    ActionType.STRIDE: evaluate_stride,
    ActionType.STRIKE: evaluate_strike,
    ActionType.TRIP: evaluate_trip,
    ActionType.DISARM: evaluate_disarm,
    ActionType.DEMORALIZE: evaluate_demoralize,
    ActionType.CREATE_A_DIVERSION: evaluate_create_a_diversion,
    ActionType.FEINT: evaluate_feint,
    ActionType.SHIELD_BLOCK: evaluate_shield_block,
    ActionType.INTERCEPT_ATTACK: evaluate_intercept_attack,
    ActionType.ACTIVATE_TACTIC: evaluate_activate_tactic,
    # CP5.2
    ActionType.ANTHEM: evaluate_anthem,
    ActionType.SOOTHE: evaluate_soothe,
    ActionType.MORTAR_AIM: evaluate_mortar_aim,
    ActionType.MORTAR_LOAD: evaluate_mortar_load,
    ActionType.MORTAR_LAUNCH: evaluate_mortar_launch,
    ActionType.TAUNT: evaluate_taunt,
    # CP5.3
    ActionType.RECALL_KNOWLEDGE: evaluate_recall_knowledge,
    ActionType.HIDE: evaluate_hide,
    ActionType.SNEAK: evaluate_sneak,
    ActionType.SEEK: evaluate_seek,
    ActionType.AID: evaluate_aid,
    ActionType.STAND: evaluate_stand,
    # CP5.4: spell chassis
    ActionType.CAST_SPELL: evaluate_spell,
    # CP7.2: hand state
    ActionType.INTERACT: evaluate_interact,
    ActionType.RELEASE: evaluate_release,
}


def evaluate_action(
    action: Action,
    state: RoundState,
    spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Dispatch to the appropriate evaluator based on action.type.

    EVER_READY is not in the dispatcher — it's a passive feature,
    not an action. (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
    """
    evaluator = _ACTION_EVALUATORS.get(action.type)
    if evaluator is None:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=f"No evaluator registered for {action.type}",
        )
    return evaluator(action, state, spatial)


# ---------------------------------------------------------------------------
# CP10.4: Late-wire contest roll chassis to avoid circular import
# ---------------------------------------------------------------------------

def _wire_contest_roll() -> None:
    from pf2e.contest_roll import evaluate_contest_roll
    for action_type in (
        ActionType.TRIP, ActionType.DISARM, ActionType.DEMORALIZE,
        ActionType.CREATE_A_DIVERSION, ActionType.FEINT,
    ):
        _ACTION_EVALUATORS[action_type] = evaluate_contest_roll

_wire_contest_roll()


# ---------------------------------------------------------------------------
# CP10.4.2: Late-wire auto-state chassis
# ---------------------------------------------------------------------------

def _wire_auto_state() -> None:
    from pf2e.auto_state import evaluate_auto_state
    for atype in (
        ActionType.STAND,
        ActionType.RAISE_SHIELD,
        ActionType.DROP_PRONE,
        ActionType.TAKE_COVER,
    ):
        _ACTION_EVALUATORS[atype] = evaluate_auto_state

_wire_auto_state()


# ---------------------------------------------------------------------------
# CP10.4.3: Late-wire strike chassis
# ---------------------------------------------------------------------------

def _wire_strike() -> None:
    from pf2e.strike import evaluate_pc_weapon_strike, evaluate_enemy_strike

    def _strike_dispatch(action, state, spatial=None):
        if action.actor_name in state.pcs:
            return evaluate_pc_weapon_strike(action, state, spatial)
        return evaluate_enemy_strike(action, state, spatial)

    _ACTION_EVALUATORS[ActionType.STRIKE] = _strike_dispatch

_wire_strike()
