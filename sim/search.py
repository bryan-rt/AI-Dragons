"""Beam search turn evaluator with adversarial enemy sub-search.

Implements per-turn beam search (K=50/20/10, depth 3) with hybrid
state threading (EV-collapse + kill/drop branching at >=5% threshold).

CP5.1.3b delivers the search machinery with injectable evaluator
callables. CP5.1.3c wires in real action evaluators.

Scoring per D11/D12:
  score = kill_score - drop_score + damage_dealt - 0.5 * damage_taken
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.combat_math import max_hp
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState

if TYPE_CHECKING:
    from sim.scenario import Scenario

logger = logging.getLogger(__name__)

# ActionTypes with the attack trait (increment MAP)
_ATTACK_TRAIT_TYPES = frozenset({
    ActionType.STRIKE, ActionType.TRIP, ActionType.DISARM,
})

# ---------------------------------------------------------------------------
# Role multipliers (D18 deferred effects catalog; hardcoded per Non-Decisions)
# ---------------------------------------------------------------------------

_ROLE_MULTIPLIERS: dict[str, float] = {"Dalai Alpaca": 2.0}
_DEFAULT_ROLE_MULTIPLIER: float = 1.0


def role_multiplier(pc_name: str) -> float:
    """Scoring multiplier on drop_cost for role importance.

    Dalai Alpaca = 2.0 (support role; Anthem loss is costly).
    All others = 1.0.
    Refactor to Character.role_weight in CP6.
    """
    return _ROLE_MULTIPLIERS.get(pc_name, _DEFAULT_ROLE_MULTIPLIER)


# ---------------------------------------------------------------------------
# Scoring (D11/D12)
# ---------------------------------------------------------------------------

def kill_value(enemy: EnemySnapshot) -> float:
    """D12: kill_value = max_hp + 10 * num_attacks_per_turn."""
    return float(enemy.max_hp) + 10.0 * enemy.num_attacks_per_turn


def drop_cost(pc: CombatantSnapshot) -> float:
    """D12: drop_cost = max_hp + 10 * role_multiplier."""
    return float(max_hp(pc.character)) + 10.0 * role_multiplier(pc.name)


@dataclass(frozen=True)
class ScoreBreakdown:
    """Components of the scoring function."""
    kill_score: float
    drop_score: float
    damage_dealt: float
    damage_taken: float

    @property
    def total(self) -> float:
        return (self.kill_score - self.drop_score
                + self.damage_dealt - 0.5 * self.damage_taken)


def compute_breakdown(
    state: RoundState, initial: RoundState,
) -> ScoreBreakdown:
    """Compute scoring breakdown between two states."""
    kill_total = 0.0
    damage_dealt_total = 0.0
    for name, enemy in state.enemies.items():
        init_enemy = initial.enemies.get(name)
        if init_enemy is None:
            continue
        damage_dealt_total += max(0.0, init_enemy.current_hp - enemy.current_hp)
        if enemy.current_hp <= 0 and init_enemy.current_hp > 0:
            kill_total += kill_value(enemy)

    drop_total = 0.0
    damage_taken_total = 0.0
    for name, pc in state.pcs.items():
        init_pc = initial.pcs.get(name)
        if init_pc is None:
            continue
        damage_taken_total += max(0.0, init_pc.current_hp - pc.current_hp)
        if pc.current_hp <= 0 and init_pc.current_hp > 0:
            drop_total += drop_cost(pc)

    return ScoreBreakdown(
        kill_score=kill_total,
        drop_score=drop_total,
        damage_dealt=damage_dealt_total,
        damage_taken=damage_taken_total,
    )


def score_state(state: RoundState, initial: RoundState) -> float:
    """Score the outcome of actions taken since initial. Positive = good for PCs."""
    return compute_breakdown(state, initial).total


# ---------------------------------------------------------------------------
# Search config and plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchConfig:
    """Configuration for the beam search."""
    beam_widths: tuple[int, int, int] = (50, 20, 10)
    enemy_beam_widths: tuple[int, int, int] = (20, 10, 5)
    kill_drop_branch_threshold: float = 0.05
    outcome_prune_threshold: float = 0.001
    seed: int = 42
    debug: bool = False


# ---------------------------------------------------------------------------
# Debug beam output (CP11.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DebugActionEntry:
    """Depth-1 evaluated candidate."""
    action: str
    action_cost: int
    score: float
    hp_delta: float
    condition_ev: float


@dataclass(frozen=True)
class DebugSequenceEntry:
    """Depth 2+ survivor sequence."""
    action_sequence: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class DebugTurnLog:
    """Full debug log for one combatant's turn."""
    actor: str
    actor_type: str
    initiative_position: int
    pre_turn_hp: dict[str, int]
    candidates_generated: int
    depth_1_evaluated: tuple[DebugActionEntry, ...]
    depth_2_survivors: tuple[DebugSequenceEntry, ...]
    depth_3_survivors: tuple[DebugSequenceEntry, ...]
    winner_sequence: tuple[str, ...]
    winner_score: float
    winner_breakdown: dict[str, float]


def _debug_serialize(
    logs: list[DebugTurnLog],
    scenario_name: str,
    seed: int,
    rounds: list[list[DebugTurnLog]] | None = None,
) -> dict:
    """Convert debug logs to JSON-serializable dict.

    If `rounds` is provided (multi-round), use nested structure.
    Otherwise wrap `logs` as a single round.
    """
    def _entry_to_dict(e: DebugActionEntry) -> dict:
        return {
            "action": e.action, "action_cost": e.action_cost,
            "score": round(e.score, 4), "hp_delta": round(e.hp_delta, 4),
            "condition_ev": round(e.condition_ev, 4),
        }

    def _seq_to_dict(s: DebugSequenceEntry) -> dict:
        return {
            "action_sequence": list(s.action_sequence),
            "score": round(s.score, 4),
        }

    def _turn_to_dict(t: DebugTurnLog) -> dict:
        return {
            "actor": t.actor,
            "actor_type": t.actor_type,
            "initiative_position": t.initiative_position,
            "pre_turn_hp": t.pre_turn_hp,
            "candidates_generated": t.candidates_generated,
            "depths": [
                {
                    "depth": 1,
                    "total_evaluated": len(t.depth_1_evaluated),
                    "survivors_into_next": len(t.depth_2_survivors),
                    "evaluated": [_entry_to_dict(e) for e in t.depth_1_evaluated],
                },
                {
                    "depth": 2,
                    "total_evaluated": len(t.depth_2_survivors),
                    "survivors_into_next": len(t.depth_3_survivors),
                    "evaluated": [_seq_to_dict(s) for s in t.depth_2_survivors],
                },
                {
                    "depth": 3,
                    "total_evaluated": len(t.depth_3_survivors),
                    "survivors_into_next": None,
                    "evaluated": [_seq_to_dict(s) for s in t.depth_3_survivors],
                },
            ],
            "winner": {
                "action_sequence": list(t.winner_sequence),
                "final_score": round(t.winner_score, 4),
                "score_breakdown": {
                    k: round(v, 4) for k, v in t.winner_breakdown.items()
                },
            },
        }

    round_groups = rounds if rounds else [logs]
    return {
        "scenario": scenario_name,
        "seed": seed,
        "rounds": [
            {
                "round_number": i + 1,
                "turns": [_turn_to_dict(t) for t in round_logs],
            }
            for i, round_logs in enumerate(round_groups)
        ],
    }


@dataclass(frozen=True)
class TurnPlan:
    """Result of a beam search for one character's turn."""
    actor_name: str
    actions: tuple[Action, ...]
    expected_score: float
    resulting_state: RoundState
    score_breakdown: ScoreBreakdown


# ---------------------------------------------------------------------------
# Hybrid state threading (D14, D22)
# ---------------------------------------------------------------------------

def apply_outcome_to_state(
    outcome: ActionOutcome,
    state: RoundState,
) -> RoundState:
    """Apply a single ActionOutcome's deltas to a RoundState."""
    result = state
    for name, delta in outcome.hp_changes.items():
        if name in result.pcs:
            pc = result.pcs[name]
            post_hp = pc.current_hp + delta
            if post_hp <= 0 and pc.current_hp > 0 and pc.dying == 0:
                # PC drops to 0 HP → gain Dying (1 + wounded + doomed)
                # Crit dying (+1) approximation deferred
                # (AoN: https://2e.aonprd.com/Conditions.aspx?ID=11)
                new_dying = max(1, 1 + pc.wounded + pc.doomed)
                result = result.with_pc_update(
                    name, current_hp=0, dying=new_dying)
            else:
                result = result.with_pc_update(
                    name, current_hp=max(0, int(post_hp)))
        elif name in result.enemies:
            new_hp = result.enemies[name].current_hp + delta
            result = result.with_enemy_update(name, current_hp=int(new_hp))
    for name, pos in outcome.position_changes.items():
        if name in result.pcs:
            result = result.with_pc_update(name, position=pos)
        elif name in result.enemies:
            result = result.with_enemy_update(name, position=pos)
    _HARDCODED_PC = {"off_guard", "prone", "shield_raised"}
    _HARDCODED_ENEMY = {"off_guard", "prone"}
    for name, conds in outcome.conditions_applied.items():
        if name in result.pcs:
            updates: dict[str, object] = {}
            extra_conditions: set[str] = set()
            for c in conds:
                if c == "off_guard":
                    updates["off_guard"] = True
                elif c == "prone":
                    updates["prone"] = True
                elif c == "shield_raised":
                    updates["shield_raised"] = True
                elif c.startswith("frightened_"):
                    updates["frightened"] = int(c.split("_")[1])
                else:
                    extra_conditions.add(c)
            if extra_conditions:
                from pf2e.damage_pipeline import merge_persistent_tag
                merged = result.pcs[name].conditions
                for ec in extra_conditions:
                    if ec.startswith("persistent_"):
                        merged = merge_persistent_tag(merged, ec)
                    else:
                        merged = merged | {ec}
                updates["conditions"] = merged
            if updates:
                result = result.with_pc_update(name, **updates)
        elif name in result.enemies:
            updates = {}
            extra_conditions = set()
            for c in conds:
                if c == "off_guard":
                    updates["off_guard"] = True
                elif c == "prone":
                    updates["prone"] = True
                else:
                    extra_conditions.add(c)
            if extra_conditions:
                from pf2e.damage_pipeline import merge_persistent_tag
                merged = result.enemies[name].conditions
                for ec in extra_conditions:
                    if ec.startswith("persistent_"):
                        merged = merge_persistent_tag(merged, ec)
                    else:
                        merged = merged | {ec}
                updates["conditions"] = merged
            if updates:
                result = result.with_enemy_update(name, **updates)
    for name, count in outcome.reactions_consumed.items():
        if name in result.pcs:
            pc = result.pcs[name]
            result = result.with_pc_update(
                name,
                reactions_available=max(0, pc.reactions_available - count),
            )
    # Remove conditions listed in conditions_removed
    # Must update bool/int fields in addition to frozenset (CP10.5 bug fix)
    for name, conds in outcome.conditions_removed.items():
        if name in result.pcs:
            updates: dict[str, object] = {}
            for c in conds:
                if c == "prone":
                    updates["prone"] = False
                elif c == "off_guard":
                    updates["off_guard"] = False
                elif c == "shield_raised":
                    updates["shield_raised"] = False
                elif c.startswith("frightened_"):
                    updates["frightened"] = 0
            new_conds = result.pcs[name].conditions - set(conds)
            updates["conditions"] = new_conds
            result = result.with_pc_update(name, **updates)
        elif name in result.enemies:
            updates = {}
            for c in conds:
                if c == "prone":
                    updates["prone"] = False
                elif c == "off_guard":
                    updates["off_guard"] = False
            new_conds = result.enemies[name].conditions - set(conds)
            updates["conditions"] = new_conds
            result = result.with_enemy_update(name, **updates)
    # Resource changes (spell slots, consumables)
    if outcome.resource_changes and outcome.actor_name and outcome.actor_name in result.pcs:
        pc = result.pcs[outcome.actor_name]
        new_resources = dict(pc.resources)
        for key, delta in outcome.resource_changes.items():
            new_resources[key] = max(0, new_resources.get(key, 0) + delta)
        result = result.with_pc_update(outcome.actor_name, resources=new_resources)

    # Hand state changes (INTERACT draw / RELEASE)
    if outcome.actor_name and outcome.actor_name in result.pcs:
        pc = result.pcs[outcome.actor_name]
        if outcome.held_weapons_add or outcome.held_weapons_remove:
            new_held = list(pc.held_weapons)
            for item in outcome.held_weapons_remove:
                if item in new_held:
                    new_held.remove(item)
            for item in outcome.held_weapons_add:
                if item not in new_held:
                    new_held.append(item)
            result = result.with_pc_update(
                outcome.actor_name, held_weapons=tuple(new_held),
            )

    # Anthem activation: if any PC's conditions_applied contains "anthem_active",
    # set the round-level anthem_active flag on RoundState.
    # (AoN: https://2e.aonprd.com/Spells.aspx — Courageous Anthem)
    for name, conds in outcome.conditions_applied.items():
        if "anthem_active" in conds:
            result = replace(result, anthem_active=True)
            break
    return result


def apply_action_result(
    result: ActionResult,
    state: RoundState,
    initial: RoundState,
    config: SearchConfig,
) -> list[tuple[RoundState, float]]:
    """Apply ActionResult outcomes with hybrid branching (D14/D22).

    Returns list of (new_state, weight) pairs. Weight is the
    probability of reaching that state from the parent.
    """
    if not result.eligible or not result.outcomes:
        return [(state, 1.0)]

    # Partition outcomes by whether they cross a kill/drop threshold
    crossing_prob = 0.0
    non_crossing_outcomes: list[ActionOutcome] = []

    for outcome in result.outcomes:
        if outcome.probability < config.outcome_prune_threshold:
            continue
        crosses = False
        for name, delta in outcome.hp_changes.items():
            if name in state.enemies:
                post_hp = state.enemies[name].current_hp + delta
                if post_hp <= 0 and state.enemies[name].current_hp > 0:
                    crosses = True
            elif name in state.pcs:
                post_hp = state.pcs[name].current_hp + delta
                if post_hp <= 0 and state.pcs[name].current_hp > 0:
                    crosses = True
        if crosses:
            crossing_prob += outcome.probability
        else:
            non_crossing_outcomes.append(outcome)

    # Branch if crossing probability meets threshold
    if crossing_prob >= config.kill_drop_branch_threshold:
        # Event world: target(s) HP = 0
        event_state = state
        for outcome in result.outcomes:
            if outcome.probability < config.outcome_prune_threshold:
                continue
            for name, delta in outcome.hp_changes.items():
                if name in event_state.enemies:
                    post_hp = event_state.enemies[name].current_hp + delta
                    if post_hp <= 0 and event_state.enemies[name].current_hp > 0:
                        event_state = event_state.with_enemy_update(
                            name, current_hp=0,
                        )
                elif name in event_state.pcs:
                    post_hp = event_state.pcs[name].current_hp + delta
                    if post_hp <= 0 and event_state.pcs[name].current_hp > 0:
                        event_state = event_state.with_pc_update(
                            name, current_hp=0,
                        )
        event_state = event_state.with_branch_probability(
            state.branch_probability * crossing_prob,
        )

        # No-event world: EV-fold non-crossing outcomes
        no_event_state = state
        if non_crossing_outcomes:
            total_nc_prob = sum(o.probability for o in non_crossing_outcomes)
            if total_nc_prob > 0:
                for name in set().union(
                    *(o.hp_changes.keys() for o in non_crossing_outcomes),
                ):
                    ev_delta = sum(
                        o.hp_changes.get(name, 0) * o.probability
                        for o in non_crossing_outcomes
                    ) / total_nc_prob
                    if name in no_event_state.pcs:
                        new_hp = no_event_state.pcs[name].current_hp + ev_delta
                        no_event_state = no_event_state.with_pc_update(
                            name, current_hp=int(new_hp),
                        )
                    elif name in no_event_state.enemies:
                        new_hp = (no_event_state.enemies[name].current_hp
                                  + ev_delta)
                        no_event_state = no_event_state.with_enemy_update(
                            name, current_hp=int(new_hp),
                        )
        no_event_state = no_event_state.with_branch_probability(
            state.branch_probability * (1.0 - crossing_prob),
        )

        branches = []
        if crossing_prob > config.outcome_prune_threshold:
            branches.append((event_state, crossing_prob))
        if (1.0 - crossing_prob) > config.outcome_prune_threshold:
            branches.append((no_event_state, 1.0 - crossing_prob))
        return branches if branches else [(state, 1.0)]

    # No branching: EV-collapse all outcomes
    ev_state = state

    # EV-fold HP changes (probability-weighted)
    for outcome in result.outcomes:
        if outcome.probability < config.outcome_prune_threshold:
            continue
        for name, delta in outcome.hp_changes.items():
            weighted = delta * outcome.probability
            if name in ev_state.pcs:
                new_hp = ev_state.pcs[name].current_hp + weighted
                ev_state = ev_state.with_pc_update(
                    name, current_hp=int(new_hp),
                )
            elif name in ev_state.enemies:
                new_hp = ev_state.enemies[name].current_hp + weighted
                ev_state = ev_state.with_enemy_update(
                    name, current_hp=int(new_hp),
                )

    # Apply non-HP state changes (conditions, positions, reactions) from the
    # most probable outcome. For deterministic outcomes (prob=1.0), this
    # applies all changes. For multi-outcome results, the most likely
    # outcome's conditions are applied (heuristic for CP5.1.3c).
    best_outcome = max(
        (o for o in result.outcomes
         if o.probability >= config.outcome_prune_threshold),
        key=lambda o: o.probability,
        default=None,
    )
    if best_outcome is not None:
        non_hp_outcome = ActionOutcome(
            probability=1.0,
            conditions_applied=best_outcome.conditions_applied,
            position_changes=best_outcome.position_changes,
            reactions_consumed=best_outcome.reactions_consumed,
        )
        ev_state = apply_outcome_to_state(non_hp_outcome, ev_state)

    return [(ev_state, 1.0)]


# ---------------------------------------------------------------------------
# Beam search
# ---------------------------------------------------------------------------

@dataclass
class _BeamEntry:
    """A candidate in the beam."""
    state: RoundState
    actions: list[Action]
    weight: float  # cumulative branch probability
    action_ev: float = 0.0  # accumulated evaluator score_delta (conditions, etc.)


def beam_search_turn(
    state: RoundState,
    actor_name: str,
    config: SearchConfig,
    candidate_actions: Callable[[RoundState, str], list[Action]],
    evaluate_action: Callable[[Action, RoundState], ActionResult],
    negate_score: bool = False,
    debug_sink: list[DebugTurnLog] | None = None,
) -> TurnPlan:
    """Find the best 3-action sequence for actor_name.

    Args:
        negate_score: If True, maximize -score (for adversarial enemy search).
        debug_sink: If not None, append a DebugTurnLog for this turn.
    """
    initial = state
    beam: list[_BeamEntry] = [_BeamEntry(state=state, actions=[], weight=1.0)]

    # Debug collection (write-only — never read during search)
    _dbg_depth1: list[DebugActionEntry] = []
    _dbg_depth2: list[DebugSequenceEntry] = []
    _dbg_depth3: list[DebugSequenceEntry] = []
    _dbg_candidates_generated = 0

    for depth in range(3):
        k = config.beam_widths[depth] if not negate_score else (
            config.enemy_beam_widths[depth]
        )
        next_beam: list[tuple[float, _BeamEntry]] = []

        for entry in beam:
            # Check if turn already ended
            if entry.actions and entry.actions[-1].type == ActionType.END_TURN:
                hp_sc = score_state(entry.state, initial)
                sc = hp_sc + entry.action_ev
                sc = -sc if negate_score else sc
                next_beam.append((sc * entry.weight, entry))
                continue

            candidates = candidate_actions(entry.state, actor_name)
            if not candidates:
                # No legal actions — force end turn
                end = Action(
                    type=ActionType.END_TURN, actor_name=actor_name,
                    action_cost=0,
                )
                candidates = [end]

            if depth == 0 and debug_sink is not None:
                _dbg_candidates_generated = len(candidates)

            for action in candidates:
                result = evaluate_action(action, entry.state)
                if not result.eligible:
                    continue
                # Accumulate evaluator score_delta (condition EV, chain credit)
                action_ev_delta = sum(
                    o.probability * o.score_delta for o in result.outcomes
                )
                child_states = apply_action_result(
                    result, entry.state, initial, config,
                )
                for child_state, weight in child_states:
                    # Track MAP and action economy on the actor
                    child_state = _update_action_economy(
                        child_state, actor_name, action,
                    )
                    new_actions = entry.actions + [action]
                    new_weight = entry.weight * weight
                    new_action_ev = entry.action_ev + action_ev_delta
                    hp_sc = score_state(child_state, initial)
                    sc = hp_sc + new_action_ev
                    sc = -sc if negate_score else sc
                    next_beam.append((
                        sc * new_weight,
                        _BeamEntry(
                            state=child_state,
                            actions=new_actions,
                            weight=new_weight,
                            action_ev=new_action_ev,
                        ),
                    ))

                    # Debug: collect depth-1 entries
                    if depth == 0 and debug_sink is not None:
                        _dbg_depth1.append(DebugActionEntry(
                            action=_action_label(action, state),
                            action_cost=action.action_cost,
                            score=sc * new_weight,
                            hp_delta=hp_sc,
                            condition_ev=action_ev_delta,
                        ))

        # Keep top K
        next_beam.sort(key=lambda x: x[0], reverse=True)
        beam = [entry for _, entry in next_beam[:k]]

        # Debug: collect depth 2/3 survivors
        if debug_sink is not None and beam:
            survivors = [
                DebugSequenceEntry(
                    action_sequence=tuple(
                        _action_label(a, state) for a in e.actions
                    ),
                    score=(score_state(e.state, initial) + e.action_ev) * e.weight,
                )
                for e in beam
            ]
            if depth == 1:
                _dbg_depth2 = survivors
            elif depth == 2:
                _dbg_depth3 = survivors

        if not beam:
            break

    # Select best
    if not beam:
        end_action = Action(
            type=ActionType.END_TURN, actor_name=actor_name, action_cost=0,
        )
        breakdown = compute_breakdown(state, initial)
        return TurnPlan(
            actor_name=actor_name,
            actions=(end_action,),
            expected_score=breakdown.total,
            resulting_state=state,
            score_breakdown=breakdown,
        )

    best = max(beam, key=lambda e:
               (score_state(e.state, initial) + e.action_ev) * e.weight
               if not negate_score
               else -(score_state(e.state, initial) + e.action_ev) * e.weight)
    breakdown = compute_breakdown(best.state, initial)
    sc = (breakdown.total + best.action_ev) if not negate_score else -(breakdown.total + best.action_ev)

    logger.info(
        f"beam_search_turn({actor_name}): best score={sc:.2f}, "
        f"actions={[a.type.name for a in best.actions]}"
    )

    # Debug: finalize and append turn log
    if debug_sink is not None:
        pre_hp: dict[str, int] = {}
        for n, p in state.pcs.items():
            pre_hp[n] = p.current_hp
        for n, e in state.enemies.items():
            pre_hp[n] = e.current_hp
        init_pos = len(state.initiative_order) - len([
            n for n in state.initiative_order
            if n == actor_name or n not in (
                set(state.pcs) | set(state.enemies))
        ])
        # Find position in initiative order
        try:
            init_pos = list(state.initiative_order).index(actor_name) + 1
        except ValueError:
            init_pos = 0
        debug_sink.append(DebugTurnLog(
            actor=actor_name,
            actor_type="enemy" if actor_name in state.enemies else "pc",
            initiative_position=init_pos,
            pre_turn_hp=pre_hp,
            candidates_generated=_dbg_candidates_generated,
            depth_1_evaluated=tuple(sorted(
                _dbg_depth1, key=lambda e: e.score, reverse=True)),
            depth_2_survivors=tuple(_dbg_depth2),
            depth_3_survivors=tuple(_dbg_depth3),
            winner_sequence=tuple(
                _action_label(a, state) for a in best.actions),
            winner_score=sc,
            winner_breakdown={
                "damage_dealt": breakdown.damage_dealt,
                "damage_taken": breakdown.damage_taken,
                "kill_score": breakdown.kill_score,
                "drop_score": breakdown.drop_score,
            },
        ))

    return TurnPlan(
        actor_name=actor_name,
        actions=tuple(best.actions),
        expected_score=sc,
        resulting_state=best.state,
        score_breakdown=breakdown,
    )


def adversarial_enemy_turn(
    state: RoundState,
    enemy_name: str,
    config: SearchConfig,
    candidate_actions: Callable[[RoundState, str], list[Action]],
    evaluate_action: Callable[[Action, RoundState], ActionResult],
    debug_sink: list[DebugTurnLog] | None = None,
) -> TurnPlan:
    """Find the enemy's best 3-action sequence (sign-flipped scoring).

    No recursive sub-searches (D16 single-best-response).
    """
    return beam_search_turn(
        state, enemy_name, config,
        candidate_actions, evaluate_action,
        negate_score=True,
        debug_sink=debug_sink,
    )


# ---------------------------------------------------------------------------
# Full round simulation
# ---------------------------------------------------------------------------

def simulate_round(
    initial: RoundState,
    config: SearchConfig,
    candidate_actions: Callable[[RoundState, str], list[Action]],
    evaluate_action: Callable[[Action, RoundState], ActionResult],
    debug_sink: list[DebugTurnLog] | None = None,
) -> tuple[list[TurnPlan], RoundState]:
    """Simulate a full round in initiative order.

    For each combatant:
        - If PC: beam_search_turn
        - If enemy: adversarial_enemy_turn
        - Apply the plan's resulting_state as the new round state

    Returns:
        (list of TurnPlans in initiative order, final state)
    """
    current = initial
    plans: list[TurnPlan] = []

    for name in initial.initiative_order:
        if name in current.pcs:
            plan = beam_search_turn(
                current, name, config,
                candidate_actions, evaluate_action,
                debug_sink=debug_sink,
            )
        elif name in current.enemies:
            plan = adversarial_enemy_turn(
                current, name, config,
                candidate_actions, evaluate_action,
                debug_sink=debug_sink,
            )
        else:
            continue

        plans.append(plan)
        current = plan.resulting_state
        # End-of-turn condition processing (frightened decrement, etc.)
        from pf2e.conditions import process_end_of_turn
        current = process_end_of_turn(current, name)

    logger.info(
        f"simulate_round: {len(plans)} turns, "
        f"final score={score_state(current, initial):.2f}"
    )

    return plans, current


# ---------------------------------------------------------------------------
# Action economy tracking (MAP + actions_remaining)
# ---------------------------------------------------------------------------

def _update_action_economy(
    state: RoundState, actor_name: str, action: Action,
) -> RoundState:
    """Update map_count and actions_remaining on the actor after an action."""
    if action.type == ActionType.END_TURN:
        return state

    if actor_name in state.pcs:
        pc = state.pcs[actor_name]
        updates: dict[str, object] = {
            "actions_remaining": max(0, pc.actions_remaining - action.action_cost),
        }
        if action.type in _ATTACK_TRAIT_TYPES:
            updates["map_count"] = pc.map_count + 1
        return state.with_pc_update(actor_name, **updates)
    elif actor_name in state.enemies:
        enemy = state.enemies[actor_name]
        new_map = enemy.map_count
        if action.type in _ATTACK_TRAIT_TYPES:
            new_map += 1
        return state.with_enemy_update(
            actor_name,
            actions_remaining=max(0, enemy.actions_remaining - action.action_cost),
            map_count=new_map,
        )
    return state


# ---------------------------------------------------------------------------
# RoundRecommendation and formatting (Step 9)
# ---------------------------------------------------------------------------

@dataclass
class RoundRecommendation:
    """Human-readable recommendation for one combatant's turn."""
    actor_name: str
    actions: list[str]
    expected_score: float
    top_alternatives: list[tuple[list[str], float]]
    reasoning: str


def format_recommendation(rec: RoundRecommendation) -> str:
    """Format a RoundRecommendation as human-readable text."""
    lines = [f"=== Recommendation for {rec.actor_name} ==="]
    lines.append(f"Best plan (EV {rec.expected_score:.2f}):")
    for i, action in enumerate(rec.actions, 1):
        lines.append(f"  {i}. {action}")
    if rec.top_alternatives:
        lines.append("\nAlternatives:")
        for alt_actions, alt_score in rec.top_alternatives:
            lines.append(f"  {' / '.join(alt_actions)}  (EV {alt_score:.2f})")
    lines.append(f"\nReasoning: {rec.reasoning}")
    return "\n".join(lines)


def _action_label(action: Action, state: RoundState | None = None) -> str:
    """Human-readable label for an Action.

    Includes target where applicable. ACTIVATE_TACTIC labels are enriched
    with the responding squadmate and action.
    """
    if action.type == ActionType.END_TURN:
        return "End Turn"
    if action.type == ActionType.STRIKE:
        weapon = f" ({action.weapon_name})" if action.weapon_name else ""
        return f"Strike {action.target_name}{weapon}"
    if action.type in (ActionType.TRIP, ActionType.DISARM):
        return f"{action.type.name.title()} {action.target_name}"
    if action.type in (ActionType.DEMORALIZE, ActionType.FEINT):
        return f"{action.type.name.title()} {action.target_name}"
    if action.type == ActionType.CREATE_A_DIVERSION:
        return f"Create a Diversion vs {action.target_name}"
    if action.type in (ActionType.STRIDE, ActionType.STEP):
        return f"{action.type.name.title()} to {action.target_position}"
    if action.type == ActionType.RAISE_SHIELD:
        return "Raise Shield"
    if action.type == ActionType.ACTIVATE_TACTIC:
        detail = _tactic_detail(action, state)
        if detail:
            return f"Activate {action.tactic_name} ({detail})"
        return f"Activate {action.tactic_name}"
    if action.type == ActionType.CAST_SPELL:
        from pf2e.spells import SPELL_REGISTRY
        defn = SPELL_REGISTRY.get(action.tactic_name)
        name = defn.name if defn else action.tactic_name
        cost = f" ({action.action_cost}a)" if action.action_cost > 1 else ""
        return f"Cast {name}{cost} vs {action.target_name}"
    if action.type == ActionType.RECALL_KNOWLEDGE:
        return f"Recall Knowledge vs {action.target_name}"
    if action.type == ActionType.TAUNT:
        return f"Taunt {action.target_name}"
    if action.type == ActionType.INTERACT:
        return f"Draw {action.weapon_name}"
    if action.type == ActionType.RELEASE:
        return f"Release {action.weapon_name} (free)"
    if action.type == ActionType.HIDE:
        return "Hide (stealth)"
    if action.type == ActionType.ANTHEM:
        return "Courageous Anthem (+1 atk/dmg to party)"
    if action.type == ActionType.SNEAK:
        return f"Sneak to {action.target_position}"
    if action.type == ActionType.AID:
        return f"Aid {action.target_name}"
    return action.type.name


def _tactic_detail(action: Action, state: RoundState | None) -> str:
    """Extract who responds and how from a tactic evaluation."""
    if state is None:
        return ""
    try:
        from pf2e.actions import evaluate_activate_tactic
        result = evaluate_activate_tactic(action, state)
        if not result.eligible or not result.outcomes:
            return ""
        desc = result.outcomes[0].description
        # The justification from evaluate_tactic has the detail we need.
        # Parse the key info: "Strike Hard! -> Rook Longsword reaction Strike
        # at +7 (MAP 0) vs Bandit1 AC 15, EV 8.55"
        if "\u2192" in desc:
            # After the arrow is the detail
            detail = desc.split("\u2192", 1)[1].strip()
            # Shorten: take up to "EV" or first comma
            if ", EV" in detail:
                detail = detail[:detail.index(", EV")]
            return detail
        return ""
    except Exception:
        return ""


def _turn_plan_to_recommendation(
    plan: TurnPlan, pre_turn_state: RoundState | None = None,
) -> RoundRecommendation:
    """Convert a TurnPlan into a human-readable RoundRecommendation.

    pre_turn_state is the state BEFORE this actor's turn began — needed
    to re-evaluate ACTIVATE_TACTIC for the detail label (who responds).
    """
    state_for_labels = pre_turn_state if pre_turn_state is not None else plan.resulting_state
    action_labels = [_action_label(a, state_for_labels) for a in plan.actions]

    breakdown = plan.score_breakdown
    reasoning = (
        f"EV breakdown: damage_dealt={breakdown.damage_dealt:.1f}, "
        f"damage_taken={breakdown.damage_taken:.1f}, "
        f"kills={breakdown.kill_score:.0f}, drops={breakdown.drop_score:.0f}"
    )
    return RoundRecommendation(
        actor_name=plan.actor_name,
        actions=action_labels,
        expected_score=plan.expected_score,
        top_alternatives=[],
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Convenience: run full simulation from Scenario
# ---------------------------------------------------------------------------

def run_simulation(
    scenario: Scenario,
    seed: int = 42,
    config: SearchConfig | None = None,
    debug_sink: list[DebugTurnLog] | None = None,
) -> list[RoundRecommendation]:
    """Load scenario, roll initiative, run beam search, return recommendations.

    This is the main entry point for the CLI and integration tests.
    """
    from pf2e.actions import evaluate_action as pf2e_evaluate_action
    from sim.candidates import generate_candidates
    from sim.initiative import roll_initiative

    if config is None:
        config = SearchConfig()

    # Build initial state
    init_state = RoundState.from_scenario(
        scenario,
        roll_initiative(
            list(RoundState.from_scenario(scenario, []).pcs.values()),
            list(RoundState.from_scenario(scenario, []).enemies.values()),
            seed=seed,
            explicit=scenario.initiative_explicit or None,
        ),
    )

    # Create callables for the beam search
    def candidate_actions(state: RoundState, actor_name: str) -> list[Action]:
        return generate_candidates(state, actor_name)

    def evaluate_action_fn(action: Action, state: RoundState) -> ActionResult:
        return pf2e_evaluate_action(action, state)

    plans, final = simulate_round(
        init_state, config, candidate_actions, evaluate_action_fn,
        debug_sink=debug_sink,
    )

    # Reconstruct pre-turn states for tactic label enrichment
    pre_turn_states: list[RoundState] = []
    current = init_state
    for plan in plans:
        pre_turn_states.append(current)
        current = plan.resulting_state

    return [
        _turn_plan_to_recommendation(p, pre)
        for p, pre in zip(plans, pre_turn_states)
    ]
