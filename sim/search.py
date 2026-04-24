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

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.combat_math import max_hp
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState

logger = logging.getLogger(__name__)

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
            new_hp = result.pcs[name].current_hp + delta
            result = result.with_pc_update(name, current_hp=int(new_hp))
        elif name in result.enemies:
            new_hp = result.enemies[name].current_hp + delta
            result = result.with_enemy_update(name, current_hp=int(new_hp))
    for name, pos in outcome.position_changes.items():
        if name in result.pcs:
            result = result.with_pc_update(name, position=pos)
        elif name in result.enemies:
            result = result.with_enemy_update(name, position=pos)
    for name, conds in outcome.conditions_applied.items():
        if name in result.pcs:
            updates: dict[str, object] = {}
            for c in conds:
                if c == "off_guard":
                    updates["off_guard"] = True
                elif c == "prone":
                    updates["prone"] = True
                elif c.startswith("frightened_"):
                    updates["frightened"] = int(c.split("_")[1])
            if updates:
                result = result.with_pc_update(name, **updates)
        elif name in result.enemies:
            updates = {}
            for c in conds:
                if c == "off_guard":
                    updates["off_guard"] = True
                elif c == "prone":
                    updates["prone"] = True
            if updates:
                result = result.with_enemy_update(name, **updates)
    for name, count in outcome.reactions_consumed.items():
        if name in result.pcs:
            pc = result.pcs[name]
            result = result.with_pc_update(
                name,
                reactions_available=max(0, pc.reactions_available - count),
            )
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


def beam_search_turn(
    state: RoundState,
    actor_name: str,
    config: SearchConfig,
    candidate_actions: Callable[[RoundState, str], list[Action]],
    evaluate_action: Callable[[Action, RoundState], ActionResult],
    negate_score: bool = False,
) -> TurnPlan:
    """Find the best 3-action sequence for actor_name.

    Args:
        negate_score: If True, maximize -score (for adversarial enemy search).
    """
    initial = state
    beam: list[_BeamEntry] = [_BeamEntry(state=state, actions=[], weight=1.0)]

    for depth in range(3):
        k = config.beam_widths[depth] if not negate_score else (
            config.enemy_beam_widths[depth]
        )
        next_beam: list[tuple[float, _BeamEntry]] = []

        for entry in beam:
            # Check if turn already ended
            if entry.actions and entry.actions[-1].type == ActionType.END_TURN:
                sc = score_state(entry.state, initial)
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

            for action in candidates:
                result = evaluate_action(action, entry.state)
                if not result.eligible:
                    continue
                child_states = apply_action_result(
                    result, entry.state, initial, config,
                )
                for child_state, weight in child_states:
                    new_actions = entry.actions + [action]
                    new_weight = entry.weight * weight
                    sc = score_state(child_state, initial)
                    sc = -sc if negate_score else sc
                    next_beam.append((
                        sc * new_weight,
                        _BeamEntry(
                            state=child_state,
                            actions=new_actions,
                            weight=new_weight,
                        ),
                    ))

        # Keep top K
        next_beam.sort(key=lambda x: x[0], reverse=True)
        beam = [entry for _, entry in next_beam[:k]]

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

    best = max(beam, key=lambda e: score_state(e.state, initial) * e.weight
               if not negate_score
               else -score_state(e.state, initial) * e.weight)
    breakdown = compute_breakdown(best.state, initial)
    sc = breakdown.total if not negate_score else -breakdown.total

    logger.info(
        f"beam_search_turn({actor_name}): best score={sc:.2f}, "
        f"actions={[a.type.name for a in best.actions]}"
    )

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
) -> TurnPlan:
    """Find the enemy's best 3-action sequence (sign-flipped scoring).

    No recursive sub-searches (D16 single-best-response).
    """
    return beam_search_turn(
        state, enemy_name, config,
        candidate_actions, evaluate_action,
        negate_score=True,
    )


# ---------------------------------------------------------------------------
# Full round simulation
# ---------------------------------------------------------------------------

def simulate_round(
    initial: RoundState,
    config: SearchConfig,
    candidate_actions: Callable[[RoundState, str], list[Action]],
    evaluate_action: Callable[[Action, RoundState], ActionResult],
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
            )
        elif name in current.enemies:
            plan = adversarial_enemy_turn(
                current, name, config,
                candidate_actions, evaluate_action,
            )
        else:
            continue

        plans.append(plan)
        current = plan.resulting_state

    logger.info(
        f"simulate_round: {len(plans)} turns, "
        f"final score={score_state(current, initial):.2f}"
    )

    return plans, current
