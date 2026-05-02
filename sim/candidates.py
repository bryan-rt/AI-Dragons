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
from sim.grid import (
    GridState, Pos, are_flanking, can_reach, compute_cover_level,
    CoverLevel, distance_ft, is_within_reach, shortest_movement_cost,
)
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
# Faction-agnostic helpers (CP11.2.3)
# ---------------------------------------------------------------------------

def _opponents(state: RoundState, actor_name: str) -> dict[str, object]:
    """Living opposing combatants relative to actor's faction."""
    if actor_name in state.pcs:
        return {n: e for n, e in state.enemies.items() if e.current_hp > 0}
    return {n: p for n, p in state.pcs.items() if p.current_hp > 0}


def _allies(state: RoundState, actor_name: str) -> dict[str, object]:
    """Living allied combatants relative to actor's faction, excl. actor."""
    if actor_name in state.pcs:
        return {n: p for n, p in state.pcs.items()
                if n != actor_name and p.current_hp > 0}
    return {n: e for n, e in state.enemies.items()
            if n != actor_name and e.current_hp > 0}


def _combatant_speed(snap: object) -> int:
    """Speed in feet for any combatant snapshot type."""
    cs = getattr(snap, 'current_speed', None)
    if cs is not None:
        return cs
    spd = getattr(snap, 'speed', None)
    if spd is not None:
        return spd
    char = getattr(snap, 'character', None)
    if char is not None:
        return getattr(char, 'speed', 25)
    return 25


def _snap_max_hp(snap: object) -> int:
    """Max HP for any combatant snapshot type."""
    mhp = getattr(snap, 'max_hp', None)
    if mhp is not None and not callable(mhp):
        return int(mhp)
    char = getattr(snap, 'character', None)
    if char is not None:
        return max_hp(char)  # type: ignore[arg-type]
    return 0


def _opponent_threat_score(snap: object) -> float:
    """Approximate offensive threat of a combatant snapshot.

    EnemySnapshot: attack_bonus × num_attacks_per_turn.
    CombatantSnapshot: attack_bonus from first weapon × 2.
    """
    if hasattr(snap, 'attack_bonus') and hasattr(snap, 'num_attacks_per_turn'):
        return float(snap.attack_bonus * snap.num_attacks_per_turn)
    char = getattr(snap, 'character', None)
    if char and getattr(char, 'equipped_weapons', None):
        eq = char.equipped_weapons[0]
        from pf2e.combat_math import attack_bonus as _atk
        try:
            bonus = _atk(snap, eq, 0)  # type: ignore[arg-type]
            return float(bonus * 2)
        except Exception:
            pass
    return 0.0


# ---------------------------------------------------------------------------
# Shared tactical stride categories A–E (CP11.2.3)
# ---------------------------------------------------------------------------

def _add_tactical_stride_categories(
    actor_pos: Pos,
    actor_name: str,
    actor_char: object,
    state: RoundState,
    grid: GridState,
    occupied: set[Pos],
    candidates: set[Pos],
) -> None:
    """Add faction-agnostic tactical stride categories A–E.

    Called by both _add_stride_candidates (PC) and _enemy_candidates
    (NPC). All faction reads go through _opponents/_allies helpers.
    """
    opp = list(_opponents(state, actor_name).values())
    alli = list(_allies(state, actor_name).values())
    scan_range = 6

    # -------------------------------------------------------------------
    # Category A: Cover — square granting cover from most threatening opp
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2361 — Cover)
    # -------------------------------------------------------------------
    if opp:
        most_threatening = max(opp, key=_opponent_threat_score)
        cover_added = 0
        for dr in range(-scan_range, scan_range + 1):
            if cover_added >= 4:
                break
            for dc in range(-scan_range, scan_range + 1):
                if cover_added >= 4:
                    break
                dest = (actor_pos[0] + dr, actor_pos[1] + dc)
                if dest == actor_pos:
                    continue
                if not (0 <= dest[0] < grid.rows
                        and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                # attacker=opponent, defender=actor at dest
                if compute_cover_level(
                    most_threatening.position, dest, grid,
                ) > CoverLevel.NONE:
                    candidates.add(dest)
                    cover_added += 1

    # -------------------------------------------------------------------
    # Category B: Chokepoint — squares with ≤3 non-wall adjacent squares
    # Distance proxy for opponent reachability (BFS deferred CP11.2.4).
    # -------------------------------------------------------------------
    chokepoint_added = 0
    for dr in range(-scan_range, scan_range + 1):
        if chokepoint_added >= 3:
            break
        for dc in range(-scan_range, scan_range + 1):
            if chokepoint_added >= 3:
                break
            dest = (actor_pos[0] + dr, actor_pos[1] + dc)
            if dest == actor_pos:
                continue
            if not (0 <= dest[0] < grid.rows
                    and 0 <= dest[1] < grid.cols):
                continue
            if dest in occupied or dest in grid.walls:
                continue
            approach_count = sum(
                1
                for adr in (-1, 0, 1)
                for adc in (-1, 0, 1)
                if (adr != 0 or adc != 0)
                and 0 <= dest[0] + adr < grid.rows
                and 0 <= dest[1] + adc < grid.cols
                and (dest[0] + adr, dest[1] + adc) not in grid.walls
            )
            if approach_count > 3:
                continue
            # At least one opponent within 2× their speed (distance proxy)
            any_opp_nearby = any(
                distance_ft(snap.position, dest)
                    <= _combatant_speed(snap) * 2
                for snap in opp[:3]
            )
            if any_opp_nearby:
                candidates.add(dest)
                chokepoint_added += 1

    # -------------------------------------------------------------------
    # Category C: Threat escape — fewer opponents can reach actor here
    # Distance proxy (BFS deferred CP11.2.4).
    # -------------------------------------------------------------------
    current_threat = sum(
        1 for snap in opp
        if distance_ft(snap.position, actor_pos) <= _combatant_speed(snap)
    )
    escape_added = 0
    if current_threat > 0:
        for dr in range(-scan_range, scan_range + 1):
            if escape_added >= 3:
                break
            for dc in range(-scan_range, scan_range + 1):
                if escape_added >= 3:
                    break
                dest = (actor_pos[0] + dr, actor_pos[1] + dc)
                if dest == actor_pos:
                    continue
                if not (0 <= dest[0] < grid.rows
                        and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                dest_threat = sum(
                    1 for snap in opp
                    if distance_ft(snap.position, dest)
                        <= _combatant_speed(snap)
                )
                if dest_threat < current_threat:
                    candidates.add(dest)
                    escape_added += 1

    # -------------------------------------------------------------------
    # Category D: Defensive withdrawal — maximize distance from opponents
    # HP gate removed: always generated, beam scores value.
    # -------------------------------------------------------------------
    if opp:
        best_dist = -1
        best_pos: Pos | None = None
        for dr in range(-scan_range, scan_range + 1):
            for dc in range(-scan_range, scan_range + 1):
                dest = (actor_pos[0] + dr, actor_pos[1] + dc)
                if dest == actor_pos:
                    continue
                if not (0 <= dest[0] < grid.rows
                        and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                min_opp_dist = min(
                    distance_ft(dest, snap.position) for snap in opp
                )
                if min_opp_dist > best_dist:
                    best_dist = min_opp_dist
                    best_pos = dest
        if best_pos is not None:
            candidates.add(best_pos)

    # -------------------------------------------------------------------
    # Category E: Reactive Strike interdiction — interpose between
    # opponent and ally. Dormant: gated on has_reactive_strike=False
    # for all current characters.
    # (AoN: https://2e.aonprd.com/Actions.aspx?ID=3041)
    # -------------------------------------------------------------------
    if actor_char and getattr(actor_char, 'has_reactive_strike', False):
        actor_reach = melee_reach_ft(actor_char)
        rs_added = 0
        for ally_snap in alli:
            if rs_added >= 3:
                break
            for opp_snap in opp:
                if rs_added >= 3:
                    break
                er, ec = opp_snap.position
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        dest = (er + dr, ec + dc)
                        if not (0 <= dest[0] < grid.rows
                                and 0 <= dest[1] < grid.cols):
                            continue
                        if dest in occupied or dest in grid.walls:
                            continue
                        if not is_within_reach(
                            dest, opp_snap.position, actor_reach,
                        ):
                            continue
                        if distance_ft(dest, ally_snap.position) <= 5:
                            candidates.add(dest)
                            rs_added += 1


# ---------------------------------------------------------------------------
# Shared candidate generators (CP11.2.2.2)
# ---------------------------------------------------------------------------

def _add_demoralize_candidates(
    actor_name: str,
    actor_pos: Pos,
    actor_conditions: frozenset[str],
    state: RoundState,
    actions: list[Action],
) -> None:
    """DEMORALIZE candidates for any actor. Faction-agnostic.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2304)
    """
    opp = _opponents(state, actor_name)
    for en_name, target in opp.items():
        if target.current_hp <= 0:
            continue
        if "demoralize_immune" in target.conditions:
            continue
        already_frightened = max(
            (int(c.split("_")[1]) for c in target.conditions
             if c.startswith("frightened_")),
            default=0,
        )
        if already_frightened >= 2:
            continue
        if distance_ft(actor_pos, target.position) <= 30:
            actions.append(Action(
                type=ActionType.DEMORALIZE, actor_name=actor_name,
                action_cost=1, target_name=en_name,
            ))


def _add_feint_candidates(
    actor_name: str,
    actor_pos: Pos,
    actor_reach: int,
    actions_remaining: int,
    state: RoundState,
    actions: list[Action],
) -> None:
    """FEINT candidates for any actor with 2+ actions. Faction-agnostic.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
    """
    if actions_remaining < 2:
        return
    opp = _opponents(state, actor_name)
    for en_name, target in opp.items():
        if target.current_hp <= 0:
            continue
        if target.off_guard or getattr(target, 'prone', False):
            continue
        if is_within_reach(actor_pos, target.position, actor_reach):
            actions.append(Action(
                type=ActionType.FEINT, actor_name=actor_name,
                action_cost=1, target_name=en_name,
            ))


def _add_cast_spell_candidates(
    actor_name: str,
    actor_pos: Pos,
    actor_char: object,
    resources: dict[str, int],
    actions_remaining: int,
    state: RoundState,
    actions: list[Action],
) -> None:
    """CAST_SPELL candidates for any actor with known_spells. Faction-agnostic.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2302)
    """
    from pf2e.spells import SPELL_REGISTRY
    known = getattr(actor_char, 'known_spells', {})
    if not known:
        return
    opp = _opponents(state, actor_name)
    for slug, rank in known.items():
        defn = SPELL_REGISTRY.get(slug)
        if defn is None:
            continue
        if defn.uses_spell_slot:
            slot_key = f"spell_slot_{defn.spell_slot_rank}"
            if resources.get(slot_key, 0) <= 0:
                continue
        if defn.scales_with_actions:
            costs = [c for c in range(1, 4) if c <= actions_remaining]
        else:
            costs = ([defn.action_cost]
                     if defn.action_cost <= actions_remaining else [])
        for cost in costs:
            for en_name, target in opp.items():
                if target.current_hp <= 0:
                    continue
                if distance_ft(actor_pos, target.position) > defn.range_ft:
                    continue
                actions.append(Action(
                    type=ActionType.CAST_SPELL, actor_name=actor_name,
                    action_cost=cost, target_name=en_name,
                    tactic_name=slug,
                ))


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

    # STRIKE: one per (held weapon, living enemy in reach) — CP7.2: only held weapons
    reach = melee_reach_ft(actor.character)
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if is_within_reach(actor.position, enemy.position, reach):
            for eq in actor.character.equipped_weapons:
                if eq.weapon.name not in actor.held_weapons:
                    continue  # Must draw via INTERACT first
                if eq.weapon.is_melee:
                    actions.append(Action(
                        type=ActionType.STRIKE, actor_name=actor_name,
                        action_cost=1, target_name=en_name,
                        weapon_name=eq.weapon.name,
                    ))

    # TRIP / DISARM: only if a HELD weapon has the trait — CP7.2
    held_weapons = [eq for eq in actor.character.equipped_weapons
                    if eq.weapon.name in actor.held_weapons]
    has_trip = any("trip" in eq.weapon.traits for eq in held_weapons)
    has_disarm = any("disarm" in eq.weapon.traits for eq in held_weapons)
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

    # DEMORALIZE: shared generator (CP11.2.2.2)
    _add_demoralize_candidates(
        actor_name, actor.position, actor.conditions, state, actions,
    )

    # CREATE_A_DIVERSION: one per living enemy, not immune.
    # Suppress if target already off_guard (from prone, prior Diversion, etc.).
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0:
            continue
        if "diversion_immune" in enemy.conditions:
            continue
        if enemy.off_guard or enemy.prone:
            continue
        actions.append(Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name=actor_name,
            action_cost=1, target_name=en_name,
        ))

    # FEINT: shared generator (CP11.2.2.2)
    _add_feint_candidates(
        actor_name, actor.position, reach, actor.actions_remaining,
        state, actions,
    )

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

    # FIRST_AID: if any ally is dying and actor has >= 2 actions
    if actor.actions_remaining >= 2:
        for pc_name, pc in state.pcs.items():
            if pc_name == actor_name:
                continue
            if 0 < pc.dying < 4:
                actions.append(Action(
                    type=ActionType.FIRST_AID, actor_name=actor_name,
                    action_cost=2, target_name=pc_name,
                ))

    # CAST_SPELL: shared generator (CP11.2.2.2)
    _add_cast_spell_candidates(
        actor_name, actor.position, actor.character,
        actor.resources, actor.actions_remaining, state, actions,
    )

    # INTERACT: draw a stowed weapon when a free hand is available (CP7.2)
    if actor.actions_remaining >= 1:
        hands_free = 2 - len(actor.held_weapons)
        for eq in actor.character.equipped_weapons:
            if eq.weapon.name in actor.held_weapons:
                continue
            hands_needed = eq.weapon.hands
            if hands_free >= hands_needed:
                actions.append(Action(
                    type=ActionType.INTERACT, actor_name=actor_name,
                    action_cost=1, weapon_name=eq.weapon.name,
                ))

    # RELEASE: free action to drop a held item (enables two-hand grip) (CP7.2)
    # Only generate when releasing enables a two-hand damage upgrade
    if len(actor.held_weapons) == 2:
        for item_name in actor.held_weapons:
            remaining = [w for w in actor.held_weapons if w != item_name]
            for eq in actor.character.equipped_weapons:
                if eq.weapon.name in remaining:
                    if any(t.startswith("two_hand_") for t in eq.weapon.traits):
                        actions.append(Action(
                            type=ActionType.RELEASE, actor_name=actor_name,
                            action_cost=0, weapon_name=item_name,
                        ))

    # STAND: if prone
    if actor.prone and actor.actions_remaining >= 1:
        actions.append(Action(
            type=ActionType.STAND, actor_name=actor_name, action_cost=1,
        ))

    # CRAWL: if prone, adjacent squares (5 ft movement)
    if actor.prone and actor.actions_remaining >= 1:
        _add_crawl_candidates(actor, state, actor_name, actions)

    # DROP_PRONE: eligible if not already prone, >= 1 action
    if not actor.prone and actor.actions_remaining >= 1:
        actions.append(Action(
            type=ActionType.DROP_PRONE, actor_name=actor_name, action_cost=1,
        ))

    # TAKE_COVER: eligible if not already covered, >= 1 action
    # Spatial cover geometry deferred to CP10.6
    if "cover" not in actor.conditions and actor.actions_remaining >= 1:
        actions.append(Action(
            type=ActionType.TAKE_COVER, actor_name=actor_name, action_cost=1,
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


def _add_crawl_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
) -> None:
    """Add CRAWL actions when prone: adjacent squares only (5 ft).
    Enemy crawl candidates deferred — no current enemy goes prone.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=76)
    """
    if not actor.prone:
        return
    speed = (actor.current_speed if actor.current_speed is not None
             else actor.character.speed)
    if speed < 10:
        return
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
                type=ActionType.CRAWL, actor_name=actor_name,
                action_cost=1, target_position=dest,
            ))


def _add_stride_candidates(
    actor: CombatantSnapshot, state: RoundState,
    actor_name: str, actions: list[Action],
    bfs_cache: dict | None,
) -> None:
    """Add STRIDE actions using heuristic destination categories.

    Categories:
    1. Aggressive: adjacent to living enemies
    2. Defensive withdrawal: maximize distance from enemies (HP < 50%)
    3. Adjacent to wounded ally (HP < 50%)
    4. Kiting: within reach weapon range but outside 5ft enemy melee
    5. Flanking setup: opposite side of enemy from adjacent ally
    6. Mortar arc: standoff within mortar range

    Max ~30 destinations total, deduplicated, filtered by can_reach.
    """
    occupied = _occupied_positions(state) - {actor.position}
    grid: GridState = state.grid  # type: ignore[assignment]
    speed = actor.current_speed if actor.current_speed is not None else actor.character.speed
    candidates: set[Pos] = set()

    # Category 1: Aggressive — squares adjacent to living enemies
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

    # Category 2: (moved to _add_tactical_stride_categories as Category D)

    # Category 3: Adjacent to wounded ally
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

    # Category 4: Kiting — within weapon reach but outside 5ft enemy melee
    # For actors with reach > 5ft (Aetregan's Scorpion Whip = 10ft)
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=684 — Reach)
    reach = melee_reach_ft(actor.character)
    if reach > 5:
        kite_count = 0
        for en_name, enemy in state.enemies.items():
            if enemy.current_hp <= 0 or kite_count >= 8:
                continue
            er, ec = enemy.position
            for dr in range(-4, 5):
                for dc in range(-4, 5):
                    if kite_count >= 8:
                        break
                    dest = (er + dr, ec + dc)
                    if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                        continue
                    if dest in occupied or dest in grid.walls:
                        continue
                    if not is_within_reach(dest, enemy.position, reach):
                        continue
                    # Must be outside standard melee reach (>5ft from ALL enemies)
                    too_close = any(
                        distance_ft(dest, e.position) <= 5
                        for e in state.enemies.values() if e.current_hp > 0
                    )
                    if too_close:
                        continue
                    candidates.add(dest)
                    kite_count += 1

    # Category 5: Flanking setup — opposite side of enemy from adjacent ally
    # Validates with are_flanking() for rules-correct geometry.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2388 — Flanking)
    flanking_added = 0
    for en_name, enemy in state.enemies.items():
        if enemy.current_hp <= 0 or flanking_added >= 4:
            continue
        adjacent_allies = [
            pc for pname, pc in state.pcs.items()
            if pname != actor_name
            and pc.current_hp > 0
            and distance_ft(pc.position, enemy.position) <= 5
        ]
        for ally in adjacent_allies:
            if flanking_added >= 4:
                break
            ar, ac = ally.position
            er, ec = enemy.position
            dest = (2 * er - ar, 2 * ec - ac)
            if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                continue
            if dest in occupied or dest in grid.walls:
                continue
            if are_flanking(dest, enemy.position, ally.position):
                candidates.add(dest)
                flanking_added += 1

    # Category 6: Mortar arc — standoff within mortar range, outside melee
    # (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4 — Light Mortar 120ft)
    if actor.character.has_light_mortar:
        MORTAR_RANGE_FT = 120
        SAFE_DIST_FT = 10
        mortar_best: Pos | None = None
        mortar_best_score = -1
        for dr in range(-8, 9):
            for dc in range(-8, 9):
                dest = (actor.position[0] + dr, actor.position[1] + dc)
                if not (0 <= dest[0] < grid.rows and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                living_enemies = [e for e in state.enemies.values()
                                  if e.current_hp > 0]
                if not living_enemies:
                    break
                if not all(
                    distance_ft(dest, e.position) <= MORTAR_RANGE_FT
                    for e in living_enemies
                ):
                    continue
                min_enemy_dist = min(
                    distance_ft(dest, e.position) for e in living_enemies
                )
                if min_enemy_dist < SAFE_DIST_FT:
                    continue
                if min_enemy_dist > mortar_best_score:
                    mortar_best_score = min_enemy_dist
                    mortar_best = dest
        if mortar_best is not None:
            candidates.add(mortar_best)

    # Categories A–E: faction-agnostic tactical categories (CP11.2.3)
    _add_tactical_stride_categories(
        actor.position, actor_name, actor.character,
        state, grid, occupied, candidates,
    )

    # Filter by BFS reachability within speed (can_reach targets dest directly)
    valid: list[Pos] = []
    for dest in candidates:
        if dest == actor.position:
            continue
        if can_reach(actor.position, dest, speed, occupied | grid.walls, grid):
            valid.append(dest)

    # Cap at ~35
    for dest in valid[:35]:
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
                    if can_reach(actor.position, dest, half_speed,
                                 occupied | grid.walls, grid):
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

def _enemy_target_priority(
    enemy: EnemySnapshot,
    pc: CombatantSnapshot,
    state: RoundState,
) -> float:
    """Score for this enemy targeting this PC. Higher = more attractive.

    Used for stride destination selection only — all in-reach PCs get
    Strike candidates regardless.
    """
    score = 0.0

    # Wounded bonus: prefer targets closer to death
    pc_max = max_hp(pc.character)
    if pc_max > 0:
        score += (1.0 - pc.current_hp / pc_max) * 10.0

    # Off-guard or prone: +2 attack is valuable
    if pc.off_guard or pc.prone:
        score += 4.0

    # Guardian penalty: Intercept Attack risks redirection
    for _ally_name, ally_pc in state.pcs.items():
        if ally_pc.current_hp <= 0:
            continue
        if not getattr(ally_pc.character, 'guardian_reactions', 0):
            continue
        if (distance_ft(ally_pc.position, pc.position) <= 10
                and ally_pc.guardian_reactions_available > 0):
            score -= 6.0

    # Distance penalty: closer is better
    score -= distance_ft(enemy.position, pc.position) * 0.1

    return score


def _enemy_melee_reach(enemy: EnemySnapshot) -> int:
    """Return melee reach in feet for this enemy.

    Flat-stat enemies (character=None): always 5ft.
    NPC enemies: 10ft if any equipped weapon has the reach trait.
    (AoN: https://2e.aonprd.com/Traits.aspx?ID=684 — Reach)
    """
    if enemy.character is None:
        return 5
    for eq in enemy.character.equipped_weapons:
        if "reach" in eq.weapon.traits:
            return 10
    return 5


def _enemy_preferred_range(enemy: EnemySnapshot) -> int:
    """Return preferred engagement range for this enemy in feet.

    Melee enemies: melee reach (5 or 10).
    Caster enemies: max spell range across known spells in SPELL_REGISTRY.
    """
    if enemy.character is None or not enemy.character.known_spells:
        return _enemy_melee_reach(enemy)
    from pf2e.spells import SPELL_REGISTRY
    max_range = 0
    for slug in enemy.character.known_spells:
        defn = SPELL_REGISTRY.get(slug)
        if defn and defn.range_ft > 5:
            max_range = max(max_range, defn.range_ft)
    if max_range > 0:
        return max_range
    return _enemy_melee_reach(enemy)


def _best_adjacent_dest(
    target_pos: Pos,
    start: Pos,
    speed: int,
    occupied: set[Pos],
    grid: GridState,
) -> Pos | None:
    """Find the cheapest reachable square adjacent to target_pos."""
    best: Pos | None = None
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
            cost = shortest_movement_cost(start, dest, occupied | grid.walls, grid)
            if cost < best_cost and cost <= speed:
                best_cost = cost
                best = dest
    return best


def _enemy_candidates(state: RoundState, actor_name: str) -> list[Action]:
    """Generate candidates for enemy combatants during adversarial sub-search.

    CP11.2.2: priority-based targeting, reach-aware strikes, flanking
    setup, caster standoff positioning.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2432)
    """
    enemy = state.enemies[actor_name]
    actions: list[Action] = []

    # F1 fix: caster enemies have no damage_dice but are not defenseless
    is_caster = (
        enemy.character is not None
        and bool(enemy.character.known_spells)
    )
    if enemy.current_hp <= 0 or (not enemy.damage_dice and not is_caster):
        return [_end_turn(actor_name)]

    reach = _enemy_melee_reach(enemy)
    enemy_speed = enemy.speed
    grid: GridState = state.grid  # type: ignore[assignment]
    occupied = _occupied_positions(state) - {enemy.position}
    living_pcs = [
        (name, pc) for name, pc in state.pcs.items() if pc.current_hp > 0
    ]

    # -------------------------------------------------------------------
    # STRIKE: all living PCs within melee reach
    # -------------------------------------------------------------------
    has_melee_target = False
    for pc_name, pc in living_pcs:
        if is_within_reach(enemy.position, pc.position, reach):
            actions.append(Action(
                type=ActionType.STRIKE, actor_name=actor_name,
                action_cost=1, target_name=pc_name,
            ))
            has_melee_target = True

    # -------------------------------------------------------------------
    # STRIDE destinations (only when no melee target)
    # -------------------------------------------------------------------
    if not has_melee_target and living_pcs:
        preferred_range = _enemy_preferred_range(enemy)
        is_ranged = preferred_range > reach

        stride_destinations: set[Pos] = set()

        # --- Category 1: Best target approach / caster standoff ---
        best_pc_name, best_pc = max(
            living_pcs,
            key=lambda x: _enemy_target_priority(enemy, x[1], state),
        )

        if not is_ranged:
            # Melee: approach best-priority target
            dest = _best_adjacent_dest(
                best_pc.position, enemy.position, enemy_speed, occupied, grid,
            )
            if dest is not None:
                stride_destinations.add(dest)
            else:
                # Intermediate approach: no adjacent-to-PC square reachable
                # this turn. Find closest reachable square toward target.
                target_pos = best_pc.position
                best_advance: Pos | None = None
                best_remaining_dist = 999
                for dr in range(-6, 7):
                    for dc in range(-6, 7):
                        adv = (enemy.position[0] + dr, enemy.position[1] + dc)
                        if adv == enemy.position:
                            continue
                        if not (0 <= adv[0] < grid.rows
                                and 0 <= adv[1] < grid.cols):
                            continue
                        if adv in occupied or adv in grid.walls:
                            continue
                        if not can_reach(
                            enemy.position, adv, enemy_speed,
                            occupied | grid.walls, grid,
                        ):
                            continue
                        remaining = distance_ft(adv, target_pos)
                        if remaining < best_remaining_dist:
                            best_remaining_dist = remaining
                            best_advance = adv
                if best_advance is not None:
                    stride_destinations.add(best_advance)
        else:
            # Caster: find standoff within spell range but outside melee
            for min_safe_dist in (15, 10, 5):
                best_standoff: Pos | None = None
                best_standoff_score = -999.0
                for dr in range(-8, 9):
                    for dc in range(-8, 9):
                        dest = (enemy.position[0] + dr, enemy.position[1] + dc)
                        if not (0 <= dest[0] < grid.rows
                                and 0 <= dest[1] < grid.cols):
                            continue
                        if dest in occupied or dest in grid.walls:
                            continue
                        if not can_reach(
                            enemy.position, dest, enemy_speed,
                            occupied | grid.walls, grid,
                        ):
                            continue
                        # At least one PC in spell range
                        if not any(
                            distance_ft(dest, pc.position) <= preferred_range
                            for _, pc in living_pcs
                        ):
                            continue
                        # Outside safe distance from all PCs
                        min_pc_dist = min(
                            distance_ft(dest, pc.position)
                            for _, pc in living_pcs
                        )
                        if min_pc_dist < min_safe_dist:
                            continue
                        if min_pc_dist > best_standoff_score:
                            best_standoff_score = min_pc_dist
                            best_standoff = dest
                if best_standoff is not None:
                    stride_destinations.add(best_standoff)
                    break

            # Fallback: approach best target if no standoff found
            if not stride_destinations:
                dest = _best_adjacent_dest(
                    best_pc.position, enemy.position, enemy_speed,
                    occupied, grid,
                )
                if dest is not None:
                    stride_destinations.add(dest)

        # --- Category 2: Flanking setup ---
        flanking_added = 0
        for en_name, en_snap in state.enemies.items():
            if en_name == actor_name or en_snap.current_hp <= 0:
                continue
            if flanking_added >= 2:
                break
            for pc_name, pc in living_pcs:
                if distance_ft(en_snap.position, pc.position) > 5:
                    continue
                # Reflect ally through PC to find flanking position
                ar, ac_col = en_snap.position
                pr, pc_col = pc.position
                dest = (2 * pr - ar, 2 * pc_col - ac_col)
                if not (0 <= dest[0] < grid.rows
                        and 0 <= dest[1] < grid.cols):
                    continue
                if dest in occupied or dest in grid.walls:
                    continue
                if not can_reach(
                    enemy.position, dest, enemy_speed,
                    occupied | grid.walls, grid,
                ):
                    continue
                if are_flanking(dest, pc.position, en_snap.position):
                    stride_destinations.add(dest)
                    flanking_added += 1
                    break

        # Categories A–E: faction-agnostic tactical categories (CP11.2.3)
        _add_tactical_stride_categories(
            enemy.position, actor_name,
            getattr(enemy, 'character', None),
            state, grid, occupied, stride_destinations,
        )

        # Emit stride candidates (skip zero-distance strides)
        for dest in stride_destinations:
            if dest == enemy.position:
                continue
            actions.append(Action(
                type=ActionType.STRIDE, actor_name=actor_name,
                action_cost=1, target_position=dest,
            ))

    # -------------------------------------------------------------------
    # Shared candidate generators (CP11.2.2.2)
    # Only for NPC enemies with NPCData (flat-stat enemies skip)
    # -------------------------------------------------------------------
    if enemy.character is not None and enemy.actions_remaining >= 1:
        _add_demoralize_candidates(
            actor_name, enemy.position, enemy.conditions, state, actions,
        )
        _add_feint_candidates(
            actor_name, enemy.position, reach,
            enemy.actions_remaining, state, actions,
        )
        _add_cast_spell_candidates(
            actor_name, enemy.position, enemy.character,
            getattr(enemy, 'resources', {}),
            enemy.actions_remaining, state, actions,
        )

    # -------------------------------------------------------------------
    # STAND: if prone
    # -------------------------------------------------------------------
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
