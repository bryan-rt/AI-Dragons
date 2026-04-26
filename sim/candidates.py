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

    # ANTHEM: if Bard with Courageous Anthem and anthem not yet active
    if (actor.character.has_courageous_anthem
            and not state.anthem_active
            and actor.actions_remaining >= 1):
        actions.append(Action(
            type=ActionType.ANTHEM, actor_name=actor_name, action_cost=1,
        ))

    # SOOTHE: if has spell and slot unused, 2 actions, wounded ally exists
    if (actor.character.has_soothe
            and "soothe_used" not in actor.conditions
            and actor.actions_remaining >= 2):
        has_wounded = any(
            pc.current_hp > 0 and pc.current_hp < max_hp(pc.character)
            for pc in state.pcs.values()
        )
        if has_wounded:
            actions.append(Action(
                type=ActionType.SOOTHE, actor_name=actor_name, action_cost=2,
            ))

    # MORTAR sequence
    if actor.character.has_light_mortar:
        if ("mortar_deployed" in actor.conditions
                and "mortar_aimed" not in actor.conditions
                and actor.actions_remaining >= 1):
            actions.append(Action(
                type=ActionType.MORTAR_AIM, actor_name=actor_name, action_cost=1,
            ))
        if ("mortar_aimed" in actor.conditions
                and "mortar_loaded" not in actor.conditions
                and actor.actions_remaining >= 1):
            actions.append(Action(
                type=ActionType.MORTAR_LOAD, actor_name=actor_name, action_cost=1,
            ))
        if ("mortar_aimed" in actor.conditions
                and "mortar_loaded" in actor.conditions
                and actor.actions_remaining >= 1):
            actions.append(Action(
                type=ActionType.MORTAR_LAUNCH, actor_name=actor_name, action_cost=1,
            ))

    # TAUNT: Guardian only, one at a time, enemy within 30 ft
    if (actor.character.has_taunt
            and not any(c.startswith("taunting_") for c in actor.conditions)
            and actor.actions_remaining >= 1):
        for en_name, enemy in state.enemies.items():
            if enemy.current_hp <= 0:
                continue
            if distance_ft(actor.position, enemy.position) <= 30:
                actions.append(Action(
                    type=ActionType.TAUNT, actor_name=actor_name,
                    action_cost=1, target_name=en_name,
                ))

    # RECALL_KNOWLEDGE: per living enemy not yet recalled, if Society trained
    from pf2e.combat_math import skill_bonus as _skill_bonus
    from pf2e.types import Skill as _Skill
    society_bonus = _skill_bonus(actor.character, _Skill.SOCIETY)
    if society_bonus > -2 and actor.actions_remaining >= 1:
        for en_name in state.enemies:
            tag = "recalled_" + en_name.lower().replace(" ", "_")
            if tag not in actor.conditions and state.enemies[en_name].current_hp > 0:
                actions.append(Action(
                    type=ActionType.RECALL_KNOWLEDGE, actor_name=actor_name,
                    action_cost=1, target_name=en_name,
                ))

    # HIDE: if not hidden and not adjacent to any enemy
    if ("hidden" not in actor.conditions
            and actor.actions_remaining >= 1):
        adjacent_enemy = any(
            distance_ft(actor.position, e.position) <= 5
            for e in state.enemies.values() if e.current_hp > 0
        )
        if not adjacent_enemy:
            actions.append(Action(
                type=ActionType.HIDE, actor_name=actor_name, action_cost=1,
            ))

    # SNEAK: if hidden, half-Speed destinations
    if "hidden" in actor.conditions and actor.actions_remaining >= 1:
        _add_sneak_candidates(actor, state, actor_name, actions)

    # SEEK: always if actions remain
    if actor.actions_remaining >= 1:
        actions.append(Action(
            type=ActionType.SEEK, actor_name=actor_name, action_cost=1,
        ))

    # AID: per living ally (not self)
    if actor.actions_remaining >= 1:
        for pc_name, pc in state.pcs.items():
            if pc_name != actor_name and pc.current_hp > 0:
                actions.append(Action(
                    type=ActionType.AID, actor_name=actor_name,
                    action_cost=1, target_name=pc_name,
                ))

    # CAST_SPELL: for each known spell in SPELL_REGISTRY (CP5.4)
    from pf2e.spells import SPELL_REGISTRY
    for slug, rank in actor.character.known_spells.items():
        defn = SPELL_REGISTRY.get(slug)
        if defn is None:
            continue
        # Determine valid action costs
        if defn.scales_with_actions:
            costs = [c for c in range(1, 4) if c <= actor.actions_remaining]
        else:
            costs = [defn.action_cost] if defn.action_cost <= actor.actions_remaining else []
        for cost in costs:
            for en_name, enemy in state.enemies.items():
                if enemy.current_hp <= 0:
                    continue
                if distance_ft(actor.position, enemy.position) > defn.range_ft:
                    continue
                actions.append(Action(
                    type=ActionType.CAST_SPELL,
                    actor_name=actor_name,
                    action_cost=cost,
                    target_name=en_name,
                    tactic_name=slug,
                ))

    # STAND: if prone
    if actor.prone and actor.actions_remaining >= 1:
        actions.append(Action(
            type=ActionType.STAND, actor_name=actor_name, action_cost=1,
        ))

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


def _add_sneak_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
) -> None:
    """Add SNEAK actions: same heuristic as STRIDE but capped at half Speed."""
    occupied = _occupied_positions(state) - {actor.position}
    grid: GridState = state.grid  # type: ignore[assignment]
    half_speed = (actor.current_speed if actor.current_speed is not None
                  else actor.character.speed) // 2
    # Aggressive destinations within half speed
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
                    cost = shortest_movement_cost(
                        actor.position, dest, occupied | grid.walls, grid,
                    )
                    if cost <= half_speed:
                        actions.append(Action(
                            type=ActionType.SNEAK, actor_name=actor_name,
                            action_cost=1, target_position=dest,
                        ))
        if len([a for a in actions if a.type == ActionType.SNEAK]) >= 5:
            break


def _add_tactic_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
) -> None:
    """Add ACTIVATE_TACTIC actions for each affordable prepared tactic.

    Only Commanders can activate tactics. Gated on has_commander_banner
    (proxy for Commander class — only Aetregan has this set).
    """
    if not actor.character.has_commander_banner:
        return
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
    """Generate candidates for enemy combatants during adversarial sub-search.

    Enemies use a simplified action set: STRIKE any PC in melee reach,
    STRIDE toward nearest PC if none in reach, END_TURN.
    """
    enemy = state.enemies[actor_name]
    actions: list[Action] = []

    if enemy.current_hp <= 0 or not enemy.damage_dice:
        return [_end_turn(actor_name)]

    # STRIKE: each living PC within 5-ft melee reach
    has_target_in_reach = False
    for pc_name, pc in state.pcs.items():
        if pc.current_hp <= 0:
            continue
        if distance_ft(enemy.position, pc.position) <= 5:
            actions.append(Action(
                type=ActionType.STRIKE, actor_name=actor_name,
                action_cost=1, target_name=pc_name,
            ))
            has_target_in_reach = True

    # STRIDE toward nearest PC if no one is in melee reach
    if not has_target_in_reach:
        grid: GridState = state.grid  # type: ignore[assignment]
        occupied = _occupied_positions(state) - {enemy.position}
        # Find nearest living PC and stride toward them
        nearest_pc_name: str | None = None
        nearest_dist = 999
        for pc_name, pc in state.pcs.items():
            if pc.current_hp <= 0:
                continue
            d = distance_ft(enemy.position, pc.position)
            if d < nearest_dist:
                nearest_dist = d
                nearest_pc_name = pc_name

        if nearest_pc_name is not None:
            target_pos = state.pcs[nearest_pc_name].position
            # Find best square adjacent to the target PC within enemy speed
            enemy_speed = 25  # standard enemy speed
            best_dest: Pos | None = None
            best_cost = 999
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    dest = (target_pos[0] + dr, target_pos[1] + dc)
                    if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                        continue
                    if dest in occupied or dest in grid.walls:
                        continue
                    cost = shortest_movement_cost(
                        enemy.position, dest, occupied | grid.walls, grid,
                    )
                    if cost < best_cost and cost <= enemy_speed:
                        best_cost = cost
                        best_dest = dest

            if best_dest is not None:
                actions.append(Action(
                    type=ActionType.STRIDE, actor_name=actor_name,
                    action_cost=1, target_position=best_dest,
                ))

    # STAND for prone enemies
    if enemy.prone:
        actions.append(Action(
            type=ActionType.STAND, actor_name=actor_name, action_cost=1,
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
