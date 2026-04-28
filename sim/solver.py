"""Full combat solver for PF2e tactical simulation.

Runs combat to completion (all enemies defeated or 10-round cap).
Evaluates top 5 distinct plans via seed variation. Returns optimal solution.

Single-round simulate_round() in sim/search.py remains unchanged.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from pf2e.actions import Action, ActionResult, ActionType, evaluate_action
from sim.candidates import generate_candidates
from sim.initiative import roll_initiative
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.search import (
    SearchConfig,
    TurnPlan,
    _action_label,
    adversarial_enemy_turn,
    beam_search_turn,
    score_state,
)

if TYPE_CHECKING:
    from sim.scenario import Scenario

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TurnLog:
    """Log of one combatant's turn in the combat."""
    combatant_name: str
    is_enemy: bool
    actions: list[str]
    score_delta: float
    hp_summary: dict[str, int]


@dataclass
class RoundLog:
    """Log of one full round (all combatants act once)."""
    round_number: int
    turns: list[TurnLog] = field(default_factory=list)


@dataclass
class CombatSolution:
    """Result of a full combat evaluation."""
    scenario_name: str
    party_composition: list[str]
    seed: int
    outcome: str          # "victory", "wipe", "timeout", "impossible"
    rounds_taken: int
    total_score: float
    difficulty_rating: str
    rounds: list[RoundLog] = field(default_factory=list)
    is_optimal: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_dead(name: str, state: RoundState) -> bool:
    if name in state.pcs:
        return state.pcs[name].current_hp <= 0
    if name in state.enemies:
        return state.enemies[name].current_hp <= 0
    return True


def _all_enemies_dead(state: RoundState) -> bool:
    return all(s.current_hp <= 0 for s in state.enemies.values())


def _all_pcs_dead(state: RoundState) -> bool:
    return all(s.current_hp <= 0 for s in state.pcs.values())


def _hp_summary(state: RoundState) -> dict[str, int]:
    summary: dict[str, int] = {}
    for name, snap in state.pcs.items():
        summary[name] = max(0, snap.current_hp)
    for name, snap in state.enemies.items():
        summary[name] = max(0, snap.current_hp)
    return summary


def _difficulty_rating(outcome: str, rounds_taken: int) -> str:
    """Derive scenario difficulty. Thresholds are CP7 calibration targets."""
    if outcome != "victory":
        return "impossible"
    if rounds_taken <= 2:
        return "trivial"
    if rounds_taken <= 4:
        return "easy"
    if rounds_taken <= 6:
        return "medium"
    if rounds_taken <= 8:
        return "hard"
    return "very_hard"


def _compute_cumulative_score(
    round_scores: list[float],
    rounds_taken: int,
    state: RoundState,
    max_rounds: int = 10,
) -> float:
    """Cumulative score with round bonus and survival bonus.

    Survival bonus has two components:
    - Flat 15 per surviving PC (rewards keeping everyone alive)
    - 0.5 × remaining HP (rewards healthy survivors)

    This ensures all-4-alive always beats 3-alive regardless of kill timing.
    Weights are CP7 calibration targets — verify against more scenarios.
    """
    base = sum(round_scores)
    round_bonus = (max_rounds - rounds_taken) * 10.0
    survivors_alive = sum(1 for s in state.pcs.values() if s.current_hp > 0)
    survivor_flat_bonus = survivors_alive * 15.0
    survivor_hp_bonus = sum(
        s.current_hp for s in state.pcs.values() if s.current_hp > 0
    ) * 0.5
    return base + round_bonus + survivor_flat_bonus + survivor_hp_bonus


# ---------------------------------------------------------------------------
# Turn state management
# ---------------------------------------------------------------------------

def _reset_turn_state(state: RoundState, actor_name: str) -> RoundState:
    """Reset per-turn fields at start of a combatant's turn.

    Resets: actions_remaining=3, map_count=0
    Clears: shield_raised (start of actor's turn per AoN)
    Clears: aiding_*/aided_by_* (consumed at turn start)
    Clears: anthem_active if actor is the anthem caster
    Clears: taunting_*/taunted_by_* if actor is the taunter

    MUST be called before beam_search_turn() for every combatant.
    """
    if actor_name in state.pcs:
        snap = state.pcs[actor_name]
        to_clear = set()
        # Shield raised clears at start of actor's turn
        if snap.shield_raised:
            to_clear.add("shield_raised")
        # Aid conditions clear at start of turn
        to_clear |= {c for c in snap.conditions
                     if c.startswith("aiding_") or c.startswith("aided_by_")}
        # Anthem caster: clear anthem_active from RoundState
        if getattr(snap.character, "has_courageous_anthem", False):
            state = replace(state, anthem_active=False)
        # Taunt: clear taunting_* from actor and taunted_by_* from enemies
        if getattr(snap.character, "has_taunt", False):
            taunt_conds = {c for c in snap.conditions if c.startswith("taunting_")}
            to_clear |= taunt_conds
            for ename, esnap in state.enemies.items():
                enemy_clear = {c for c in esnap.conditions
                               if c.startswith("taunted_by_")}
                if enemy_clear:
                    state = state.with_enemy_update(
                        ename, conditions=esnap.conditions - enemy_clear,
                    )

        new_conds = snap.conditions - to_clear
        state = state.with_pc_update(
            actor_name,
            actions_remaining=3,
            map_count=0,
            shield_raised=False,
            conditions=new_conds,
            used_flourish_this_turn=False,
        )
    elif actor_name in state.enemies:
        snap = state.enemies[actor_name]
        state = state.with_enemy_update(
            actor_name,
            actions_remaining=3,
        )

    return state


def _end_of_turn_cleanup(state: RoundState, actor_name: str) -> RoundState:
    """Apply end-of-turn condition processing.

    Frightened: decrement by 1 at end of affected creature's turn.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=42)
    """
    def _decrement_frightened(conditions: frozenset[str]) -> frozenset[str]:
        new_conds = set(conditions)
        for c in list(new_conds):
            if c.startswith("frightened_"):
                try:
                    val = int(c.split("_")[1])
                except (IndexError, ValueError):
                    continue
                new_conds.discard(c)
                if val > 1:
                    new_conds.add(f"frightened_{val - 1}")
        return frozenset(new_conds)

    if actor_name in state.pcs:
        snap = state.pcs[actor_name]
        new_conds = _decrement_frightened(snap.conditions)
        if new_conds != snap.conditions:
            # Also update the frightened int field
            fright_val = 0
            for c in new_conds:
                if c.startswith("frightened_"):
                    try:
                        fright_val = int(c.split("_")[1])
                    except (IndexError, ValueError):
                        pass
            state = state.with_pc_update(
                actor_name, conditions=new_conds, frightened=fright_val,
            )
    elif actor_name in state.enemies:
        snap = state.enemies[actor_name]
        new_conds = _decrement_frightened(snap.conditions)
        if new_conds != snap.conditions:
            state = state.with_enemy_update(actor_name, conditions=new_conds)

    return state


# ---------------------------------------------------------------------------
# Core combat loop
# ---------------------------------------------------------------------------

def _run_single_combat(
    scenario: Scenario,
    seed: int,
    max_rounds: int,
    config: SearchConfig | None = None,
) -> CombatSolution:
    """Run one full combat to completion with the given seed."""
    if config is None:
        config = SearchConfig()

    # Build initial state with initiative
    dummy_state = RoundState.from_scenario(scenario, [])
    init_order = roll_initiative(
        list(dummy_state.pcs.values()),
        list(dummy_state.enemies.values()),
        seed=seed,
        explicit=scenario.initiative_explicit or None,
    )
    state = RoundState.from_scenario(scenario, init_order)

    # Create callables for beam search
    def candidate_fn(s: RoundState, actor: str) -> list[Action]:
        return generate_candidates(s, actor)

    def evaluate_fn(action: Action, s: RoundState) -> ActionResult:
        return evaluate_action(action, s)

    round_logs: list[RoundLog] = []
    round_scores: list[float] = []

    for round_num in range(1, max_rounds + 1):
        round_log = RoundLog(round_number=round_num)
        initial_round_state = state

        for actor_name in init_order:
            if _is_dead(actor_name, state):
                continue

            # Reset action economy BEFORE search
            state = _reset_turn_state(state, actor_name)

            is_enemy = actor_name in state.enemies
            if is_enemy:
                plan = adversarial_enemy_turn(
                    state, actor_name, config, candidate_fn, evaluate_fn,
                )
            else:
                plan = beam_search_turn(
                    state, actor_name, config, candidate_fn, evaluate_fn,
                )

            state = plan.resulting_state

            # Build turn log
            action_labels = [_action_label(a, state) for a in plan.actions]
            turn_log = TurnLog(
                combatant_name=actor_name,
                is_enemy=is_enemy,
                actions=action_labels,
                score_delta=plan.expected_score,
                hp_summary=_hp_summary(state),
            )
            round_log.turns.append(turn_log)

            # End-of-turn cleanup
            state = _end_of_turn_cleanup(state, actor_name)

            # Victory check mid-round
            if _all_enemies_dead(state):
                round_logs.append(round_log)
                rs = score_state(state, initial_round_state)
                round_scores.append(rs)
                total = _compute_cumulative_score(
                    round_scores, round_num, state, max_rounds,
                )
                return CombatSolution(
                    scenario_name=scenario.name,
                    party_composition=list(state.pcs.keys()),
                    seed=seed,
                    outcome="victory",
                    rounds_taken=round_num,
                    total_score=total,
                    difficulty_rating=_difficulty_rating("victory", round_num),
                    rounds=round_logs,
                )

        round_logs.append(round_log)
        rs = score_state(state, initial_round_state)
        round_scores.append(rs)

        # Wipe check at round end
        if _all_pcs_dead(state):
            total = _compute_cumulative_score(
                round_scores, round_num, state, max_rounds,
            )
            return CombatSolution(
                scenario_name=scenario.name,
                party_composition=list(state.pcs.keys()),
                seed=seed,
                outcome="wipe",
                rounds_taken=round_num,
                total_score=total,
                difficulty_rating="impossible",
                rounds=round_logs,
            )

    # Timeout
    total = _compute_cumulative_score(
        round_scores, max_rounds, state, max_rounds,
    )
    return CombatSolution(
        scenario_name=scenario.name,
        party_composition=list(state.pcs.keys()),
        seed=seed,
        outcome="timeout",
        rounds_taken=max_rounds,
        total_score=total,
        difficulty_rating=_difficulty_rating("timeout", max_rounds),
        rounds=round_logs,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def solve_combat(
    scenario: Scenario,
    seed: int = 42,
    max_rounds: int = 10,
    num_plans: int = 5,
) -> CombatSolution:
    """Run full combat to completion. Evaluate num_plans distinct plans.

    Plans are seeded with [seed, seed+1, ..., seed+num_plans-1].
    Diversity comes from different initiative orders per seed.
    Note: if seeds produce identical initiative orders, plans may be similar.
    True first-action branching is a CP7 enhancement.
    """
    solutions: list[CombatSolution] = []
    for i in range(num_plans):
        solution = _run_single_combat(scenario, seed + i, max_rounds)
        solutions.append(solution)
        logger.info(
            f"Plan {i+1}/{num_plans} (seed={seed+i}): "
            f"{solution.outcome} in {solution.rounds_taken}r, "
            f"score={solution.total_score:.1f}"
        )

    # Pick best winning plan
    winning = [s for s in solutions if s.outcome == "victory"]
    if winning:
        best = max(winning, key=lambda s: s.total_score)
        return dataclasses.replace(best, is_optimal=True)

    # No winning plan — return highest-scoring failure
    best_failed = max(solutions, key=lambda s: s.total_score)
    return dataclasses.replace(
        best_failed, outcome="impossible",
        difficulty_rating="impossible", is_optimal=False,
    )


# ---------------------------------------------------------------------------
# Output formatter
# ---------------------------------------------------------------------------

def format_combat_solution(solution: CombatSolution) -> str:
    """Format a CombatSolution as a human-readable combat log."""
    lines: list[str] = []
    lines.append(f"=== Combat Solution: {solution.scenario_name} ===")
    lines.append(f"Party: {', '.join(solution.party_composition)}")
    outcome_text = f"{solution.outcome.title()} in {solution.rounds_taken} round(s)"
    lines.append(f"Outcome: {outcome_text}")
    lines.append(f"Difficulty: {solution.difficulty_rating.replace('_', ' ').title()}")
    lines.append(f"Total Score: {solution.total_score:.1f}")
    lines.append("")

    for round_log in solution.rounds:
        lines.append(f"--- Round {round_log.round_number} ---")
        lines.append("")
        for turn in round_log.turns:
            prefix = "[ENEMY] " if turn.is_enemy else ""
            lines.append(f"[{prefix}{turn.combatant_name}]  "
                         f"(Turn EV: {turn.score_delta:.1f})")
            for i, action in enumerate(turn.actions, 1):
                lines.append(f"  {i}. {action}")
            # HP summary for living combatants
            hp_parts = [f"{n}: {hp}" for n, hp in turn.hp_summary.items()
                        if hp > 0]
            if hp_parts:
                lines.append(f"  HP: {', '.join(hp_parts)}")
            lines.append("")

    if solution.outcome == "impossible":
        lines.append("No winning plan found. Scenario may be too hard.")
    else:
        lines.append(f"=== Result: {solution.outcome.title()} "
                     f"in {solution.rounds_taken} round(s) ===")
        lines.append(f"Difficulty: {solution.difficulty_rating.replace('_', ' ').title()}")

    return "\n".join(lines)
