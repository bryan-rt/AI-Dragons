"""Candidate action generation for the beam search.

Generates all legal parameterized Action objects for a given actor in
a given RoundState. Lives in sim/ because it needs spatial queries
and grid geometry (layering rule: pf2e/ must not import from sim/).

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2432 — Actions in combat)
"""

from __future__ import annotations

from pf2e.actions import Action, ActionType
from pf2e.combat_math import melee_reach_ft, max_hp
from pf2e.tactics import FOLIO_TACTICS, PREPARED_TACTICS
from sim.grid import GridState, Pos, distance_ft, is_within_reach, shortest_movement_cost
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


def generate_candidates(
    state: RoundState,
    actor_name: str,
    bfs_cache: dict | None = None,
) -> list[Action]:
    """Generate all legal parameterized actions for actor_name in state.

    For PCs: STRIKE, TRIP, DISARM, STEP, STRIDE, RAISE_SHIELD,
    DEMORALIZE, CREATE_A_DIVERSION, FEINT, ACTIVATE_TACTIC, END_TURN.
    For enemies: STRIKE against each reachable PC, END_TURN.

    Eligibility pre-filtering reduces evaluator calls in the beam search.
    """
    if actor_name in state.pcs:
        return _pc_candidates(state, actor_name, bfs_cache)
    elif actor_name in state.enemies:
        return _enemy_candidates(state, actor_name)
    return [_end_turn(actor_name)]


def _end_turn(actor_name: str) -> Action:
    return Action(type=ActionType.END_TURN, actor_name=actor_name, action_cost=0)


# ---------------------------------------------------------------------------
# PC candidate generation
# ---------------------------------------------------------------------------

def _pc_candidates(
    state: RoundState, actor_name: str, bfs_cache: dict | None,
) -> list[Action]:
    actor = state.pcs[actor_name]
    actions: list[Action] = []

    if actor.actions_remaining <= 0:
        return [_end_turn(actor_name)]

    # STRIKE: one per (weapon, living enemy in reach)
    reach = melee_reach_ft(actor.character)
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if is_within_reach(actor.position, enemy.position, reach):
            for eq in actor.character.equipped_weapons:
                if eq.weapon.is_melee:
                    actions.append(Action(
                        type=ActionType.STRIKE, actor_name=actor_name,
                        action_cost=1, target_name=en_name,
                        weapon_name=eq.weapon.name,
                    ))

    # TRIP / DISARM: one per living enemy in melee reach (if weapon has trait)
    has_trip = any("trip" in eq.weapon.traits for eq in actor.character.equipped_weapons)
    has_disarm = any("disarm" in eq.weapon.traits for eq in actor.character.equipped_weapons)
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if not is_within_reach(actor.position, enemy.position, reach):
            continue
        if has_trip and not enemy.prone:
            actions.append(Action(
                type=ActionType.TRIP, actor_name=actor_name,
                action_cost=1, target_name=en_name,
            ))
        if has_disarm:
            actions.append(Action(
                type=ActionType.DISARM, actor_name=actor_name,
                action_cost=1, target_name=en_name,
            ))

    # DEMORALIZE: one per living enemy within 30 ft, not immune
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if "demoralize_immune" in enemy.conditions:
            continue
        if distance_ft(actor.position, enemy.position) <= 30:
            actions.append(Action(
                type=ActionType.DEMORALIZE, actor_name=actor_name,
                action_cost=1, target_name=en_name,
            ))

    # CREATE_A_DIVERSION: one per living enemy, not immune
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if "diversion_immune" in enemy.conditions:
            continue
        actions.append(Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name=actor_name,
            action_cost=1, target_name=en_name,
        ))

    # FEINT: one per living enemy in melee reach (needs >= 2 actions)
    if actor.actions_remaining >= 2:
        for en_name, enemy in state.enemies.items():
            if enemy.current_hp <= 0:
                continue
            if is_within_reach(actor.position, enemy.position, reach):
                actions.append(Action(
                    type=ActionType.FEINT, actor_name=actor_name,
                    action_cost=1, target_name=en_name,
                ))

    # RAISE_SHIELD
    if (actor.character.shield is not None
            and not actor.shield_raised
            and actor.actions_remaining >= 1):
        actions.append(Action(
            type=ActionType.RAISE_SHIELD, actor_name=actor_name,
            action_cost=1,
        ))

    # STEP: one per valid adjacent square
    _add_step_candidates(actor, state, actor_name, actions)

    # STRIDE: heuristic destinations
    _add_stride_candidates(actor, state, actor_name, actions, bfs_cache)

    # ACTIVATE_TACTIC: one per prepared tactic with sufficient actions
    _add_tactic_candidates(actor, state, actor_name, actions)

    # Always include END_TURN
    actions.append(_end_turn(actor_name))

    return actions


def _add_step_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
) -> None:
    """Add STEP actions to adjacent unoccupied squares."""
    occupied = _occupied_positions(state)
    grid: GridState = state.grid  # type: ignore[assignment]
    r, c = actor.position
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            dest = (r + dr, c + dc)
            if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                continue
            if dest in occupied or dest in grid.walls:
                continue
            actions.append(Action(
                type=ActionType.STEP, actor_name=actor_name,
                action_cost=1, target_position=dest,
            ))


def _add_stride_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
    bfs_cache: dict | None,
) -> None:
    """Add STRIDE actions using 5-category heuristic destinations.

    Categories:
    1. Aggressive: adjacent to living enemies (top 2)
    2. Flanking: opposite ally adjacent to enemy (top 2)
    3. Banner reposition: (commander only, deferred)
    4. Defensive withdrawal: maximize distance from enemies (HP < 50%)
    5. Adjacent to wounded ally (HP < 50%)

    Max ~20 destinations total, deduplicated.
    """
    occupied = _occupied_positions(state) - {actor.position}
    grid: GridState = state.grid  # type: ignore[assignment]
    speed = actor.current_speed if actor.current_speed is not None else actor.character.speed
    candidates: set[Pos] = set()

    # 1. Aggressive: squares adjacent to living enemies
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                dest = (enemy.position[0] + dr, enemy.position[1] + dc)
                if (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols
                        and dest not in occupied and dest not in grid.walls):
                    candidates.add(dest)
        if len(candidates) >= 4:
            break

    # 4. Defensive withdrawal: if HP < 50%, find a square far from enemies
    actor_max_hp = max_hp(actor.character)
    if actor_max_hp > 0 and actor.current_hp / actor_max_hp < 0.5:
        best_dist = -1
        best_pos: Pos | None = None
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                dest = (actor.position[0] + dr, actor.position[1] + dc)
                if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                min_enemy_dist = min(
                    (distance_ft(dest, e.position)
                     for e in state.enemies.values() if e.current_hp > 0),
                    default=0,
                )
                if min_enemy_dist > best_dist:
                    best_dist = min_enemy_dist
                    best_pos = dest
        if best_pos is not None:
            candidates.add(best_pos)

    # 5. Adjacent to wounded ally
    for pc_name, pc in state.pcs.items():
        if pc_name == actor_name:
            continue
        pc_max = max_hp(pc.character)
        if pc_max > 0 and pc.current_hp / pc_max < 0.5:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    dest = (pc.position[0] + dr, pc.position[1] + dc)
                    if (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols
                            and dest not in occupied and dest not in grid.walls):
                        candidates.add(dest)
                        break  # One destination per wounded ally

    # Filter by BFS reachability within speed
    valid: list[Pos] = []
    for dest in candidates:
        if dest == actor.position:
            continue
        cost = shortest_movement_cost(
            actor.position, dest,
            occupied | grid.walls, grid,
        )
        if cost <= speed:
            valid.append(dest)

    # Cap at ~20
    for dest in valid[:20]:
        actions.append(Action(
            type=ActionType.STRIDE, actor_name=actor_name,
            action_cost=1, target_position=dest,
        ))


def _add_tactic_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
) -> None:
    """Add ACTIVATE_TACTIC actions for each affordable prepared tactic."""
    for key in PREPARED_TACTICS:
        defn = FOLIO_TACTICS[key]
        if actor.actions_remaining >= defn.action_cost:
            actions.append(Action(
                type=ActionType.ACTIVATE_TACTIC, actor_name=actor_name,
                action_cost=defn.action_cost, tactic_name=defn.name,
            ))


# ---------------------------------------------------------------------------
# Enemy candidate generation
# ---------------------------------------------------------------------------

def _enemy_candidates(state: RoundState, actor_name: str) -> list[Action]:
    """Generate STRIKE candidates for enemy combatants."""
    enemy = state.enemies[actor_name]
    actions: list[Action] = []

    if enemy.current_hp <= 0 or not enemy.damage_dice:
        return [_end_turn(actor_name)]

    for pc_name, pc in state.pcs.items():
        if pc.current_hp <= 0:
            continue
        if distance_ft(enemy.position, pc.position) <= 5:
            actions.append(Action(
                type=ActionType.STRIKE, actor_name=actor_name,
                action_cost=1, target_name=pc_name,
            ))

    actions.append(_end_turn(actor_name))
    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _occupied_positions(state: RoundState) -> set[Pos]:
    """All positions occupied by living combatants."""
    result: set[Pos] = set()
    for pc in state.pcs.values():
        if pc.current_hp > 0:
            result.add(pc.position)
    for enemy in state.enemies.values():
        if enemy.current_hp > 0:
            result.add(enemy.position)
    return result
