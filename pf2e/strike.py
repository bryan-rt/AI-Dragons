"""pf2e/strike.py — Strike Chassis (CP10.4.3)

Unified attack-roll evaluators. Three paths share a common d20 core:
  evaluate_pc_weapon_strike   — PC weapon strikes
  evaluate_enemy_strike       — enemy strikes vs PCs
  evaluate_spell_attack_roll  — spell attack rolls (called by evaluate_spell)

Ranged strikes deferred to CP10.6.
(AoN Attack rolls: https://2e.aonprd.com/Rules.aspx?ID=2187)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pf2e.combat_math import (
    armor_class,
    attack_bonus as _attack_bonus,
    damage_avg,
    die_average,
    enumerate_d20_outcomes,
    expected_enemy_turn_damage,
    map_penalty,
    melee_reach_ft,
    spell_attack_bonus,
)

if TYPE_CHECKING:
    from pf2e.actions import Action, ActionOutcome, ActionResult
    from pf2e.spells import SpellDefinition
    from pf2e.tactics import SpatialQueries
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


# ---------------------------------------------------------------------------
# Geometry helpers (duplicated from actions.py to avoid circular import,
# same pattern as contest_roll.py)
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


def _are_flanking(
    actor_pos: tuple[int, int],
    target_pos: tuple[int, int],
    ally_pos: tuple[int, int],
) -> bool:
    """Pure geometry flanking check. Duplicated from sim/grid.py.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2375)
    """
    if actor_pos == target_pos or ally_pos == target_pos:
        return False
    if actor_pos == ally_pos:
        return False
    dr_a = actor_pos[0] - target_pos[0]
    dc_a = actor_pos[1] - target_pos[1]
    dr_b = ally_pos[0] - target_pos[0]
    dc_b = ally_pos[1] - target_pos[1]
    return (dr_a * dr_b + dc_a * dc_b) <= 0


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
# Shared helpers
# ---------------------------------------------------------------------------

def is_flanking(
    actor_pos: tuple[int, int],
    target_pos: tuple[int, int],
    state: RoundState,
) -> bool:
    """True if any living PC ally flanks target with actor AND
    threatens target (within melee reach). PC-attacker only.
    Enemy flanking deferred to future checkpoint.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2375)
    """
    for ally in state.pcs.values():
        if ally.current_hp <= 0:
            continue
        if ally.position == actor_pos:
            continue
        reach = melee_reach_ft(ally.character)
        if not _is_within_weapon_reach(ally.position, target_pos, reach):
            continue
        if _are_flanking(actor_pos, target_pos, ally.position):
            return True
    return False


def effective_target_ac(
    target: CombatantSnapshot | EnemySnapshot,
    actor_pos: tuple[int, int],
    state: RoundState,
    cover_bonus: int = 0,
) -> int:
    """AC after off-guard, prone, flanking reductions, and cover bonus.
    cover_bonus: computed by caller from sim.grid.compute_cover_level.
    (AoN off-guard: https://2e.aonprd.com/Conditions.aspx?ID=58)
    (AoN flanking: https://2e.aonprd.com/Rules.aspx?ID=2375)
    (AoN cover: https://2e.aonprd.com/Rules.aspx?ID=2347)
    """
    flanked = is_flanking(actor_pos, target.position, state)
    penalty = 2 if (target.off_guard or target.prone or flanked) else 0
    return target.ac - penalty + cover_bonus


def build_strike_outcomes(
    bonus: int,
    effective_ac: int,
    hit_dmg: float,
    crit_dmg: float,
    target_name: str,
) -> list[ActionOutcome]:
    """Core miss/hit/crit outcome builder.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2189)
    """
    from pf2e.actions import ActionOutcome

    d20 = enumerate_d20_outcomes(bonus, effective_ac)
    miss = (d20.failure + d20.critical_failure) / 20
    hit = d20.success / 20
    crit = d20.critical_success / 20
    outcomes: list[ActionOutcome] = []
    if miss > 0:
        outcomes.append(ActionOutcome(
            probability=miss, description=f"Miss ({miss:.0%})"))
    if hit > 0:
        outcomes.append(ActionOutcome(
            probability=hit, hp_changes={target_name: -hit_dmg},
            description=f"Hit {hit_dmg:.1f} ({hit:.0%})"))
    if crit > 0:
        outcomes.append(ActionOutcome(
            probability=crit, hp_changes={target_name: -crit_dmg},
            description=f"Crit {crit_dmg:.1f} ({crit:.0%})"))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))
    return outcomes


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strike_hidden_ev(state: RoundState, actor: CombatantSnapshot) -> float:
    """EV of Hidden condition lost when Striking. DC 11 flat check = 50%.
    NOTE: actions.py uses 0.45 (bug). Correct value is 0.50 (DC11 = 10/20).
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=45)
    """
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    if not living_enemies:
        return 0.0
    living_pcs = sum(1 for pc in state.pcs.values() if pc.current_hp > 0)
    if living_pcs <= 0:
        return 0.0
    total_attacks = sum(e.num_attacks_per_turn for e in living_enemies)
    attacks_on_me = total_attacks / living_pcs
    avg_dmg_per_atk = sum(
        expected_enemy_turn_damage(e, actor) / e.num_attacks_per_turn
        for e in living_enemies if e.num_attacks_per_turn > 0
    ) / max(1, len(living_enemies))
    return attacks_on_me * 0.50 * avg_dmg_per_atk


def _find_weapon(actor: CombatantSnapshot, weapon_name: str):
    """Find EquippedWeapon by name; fall back to first weapon."""
    for eq in actor.character.equipped_weapons:
        if eq.weapon.name == weapon_name:
            return eq
    if actor.character.equipped_weapons:
        return actor.character.equipped_weapons[0]
    return None


def _has_recalled(actor: CombatantSnapshot, enemy_name: str) -> bool:
    tag = "recalled_" + enemy_name.lower().replace(" ", "_")
    return tag in actor.conditions


# ---------------------------------------------------------------------------
# PC weapon strike
# ---------------------------------------------------------------------------

def evaluate_pc_weapon_strike(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """PC weapon strike. MAP, anthem, two-hand, W/R, focus fire, hidden.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2322)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not a PC")
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

    # Cover bonus: defender gains +N circ AC if wall between them
    # Runtime import avoids module-level pf2e/ -> sim/ dependency
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2347)
    cover_bonus = 0
    if getattr(state, 'grid', None) is not None:
        from sim.grid import compute_cover_level
        cover_bonus = compute_cover_level(
            actor.position, target.position, state.grid).value

    # Attack bonus: attack_bonus() includes ability+prof+item+MAP+frightened+status.
    # Then add anthem delta (if cast mid-turn) and hidden bonus.
    penalty = map_penalty(actor.map_count + 1, equipped.weapon.is_agile)
    bonus = _attack_bonus(actor, equipped, penalty)
    # Anthem simplification: if anthem_active but snapshot doesn't reflect it
    anthem_atk = 1 if state.anthem_active else 0
    anthem_delta = anthem_atk - actor.status_bonus_attack
    if anthem_delta > 0:
        bonus += anthem_delta
    # Hidden strike: +2 circumstance bonus to attack
    if "hidden" in actor.conditions:
        bonus += 2

    eff_ac = effective_target_ac(
        target, actor.position, state, cover_bonus=cover_bonus)

    # Damage
    hit_dmg = damage_avg(actor, equipped)
    # Two-hand upgrade: sole held item + weapon has two_hand_dN trait
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=718)
    for trait in equipped.weapon.traits:
        if trait.startswith("two_hand_"):
            two_hand_die = trait.split("_", 2)[2]  # "d10" from "two_hand_d10"
            if (equipped.weapon.name in actor.held_weapons
                    and len(actor.held_weapons) == 1):
                base_avg = die_average(equipped.weapon.damage_die)
                upgraded_avg = die_average(two_hand_die)
                hit_dmg += (upgraded_avg - base_avg) * equipped.total_damage_dice
            break
    # Anthem damage delta
    anthem_dmg = 1 if state.anthem_active else 0
    anthem_dmg_delta = anthem_dmg - actor.status_bonus_damage
    if anthem_dmg_delta > 0:
        hit_dmg += anthem_dmg_delta

    # W/R: apply if Recall Knowledge used
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=724 — Versatile)
    if _has_recalled(actor, action.target_name):
        base_type = equipped.weapon.damage_type.name.lower()
        available_types = [base_type]
        for trait in equipped.weapon.traits:
            if trait.startswith("versatile_"):
                alt = trait[len("versatile_"):]
                type_map = {"p": "piercing", "s": "slashing", "b": "bludgeoning"}
                if alt in type_map:
                    available_types.append(type_map[alt])
        best_wr = max(
            target.weaknesses.get(dt, 0) - target.resistances.get(dt, 0)
            for dt in available_types
        )
        hit_dmg = max(0.0, hit_dmg + best_wr)

    # Deadly die adds after doubling on crit
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=570)
    # NOTE: scales to 2/3 dice with greater/major striking runes — deferred.
    deadly = equipped.weapon.deadly_die
    deadly_extra = die_average(deadly) if deadly else 0.0
    crit_dmg = hit_dmg * 2 + deadly_extra

    outcomes = build_strike_outcomes(bonus, eff_ac, hit_dmg, crit_dmg,
                                     action.target_name)

    # Focus fire bonus: extra score_delta for concentrating on wounded target
    if actor.map_count > 0:
        hp_frac = target.current_hp / max(1, target.max_hp)
        if hp_frac < 0.5 and target.damage_dice and "d" in target.damage_dice:
            parts = target.damage_dice.split("d", 1)
            avg_en_dmg = (int(parts[0]) * die_average(f"d{parts[1]}")
                          + target.damage_bonus)
            kill_prox = 1.0 - hp_frac
            focus_bonus = kill_prox * avg_en_dmg * target.num_attacks_per_turn * 0.3
            outcomes = [ActionOutcome(
                probability=o.probability, hp_changes=o.hp_changes,
                position_changes=o.position_changes,
                conditions_applied=o.conditions_applied,
                conditions_removed=o.conditions_removed,
                reactions_consumed=o.reactions_consumed,
                score_delta=o.score_delta + focus_bonus,
                description=o.description,
            ) for o in outcomes]

    # Hidden clears on any Strike
    if "hidden" in actor.conditions:
        hidden_pen = _strike_hidden_ev(state, actor)
        outcomes = [ActionOutcome(
            probability=o.probability, hp_changes=o.hp_changes,
            position_changes=o.position_changes,
            conditions_applied=o.conditions_applied,
            conditions_removed={**o.conditions_removed,
                                action.actor_name: ("hidden",)},
            reactions_consumed=o.reactions_consumed,
            score_delta=o.score_delta - hidden_pen,
            description=o.description,
        ) for o in outcomes]

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# Enemy strike
# ---------------------------------------------------------------------------

def evaluate_enemy_strike(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Enemy Strike against a PC target.

    Simplification: enemy MAP not tracked per snapshot. Each Strike
    uses raw attack_bonus. This overestimates enemy damage (conservative).
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2322)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    actor = state.enemies.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not found as enemy")
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

    # Enemy uses armor_class() for target AC (full derivation including
    # shield, off-guard, frightened). Flanking stub feeds through here.
    target_ac = armor_class(target)

    # Parse NdX+B damage
    if "d" in actor.damage_dice:
        parts = actor.damage_dice.split("d", 1)
        num_dice = int(parts[0])
        hit_dmg = num_dice * die_average(f"d{parts[1]}") + actor.damage_bonus
    else:
        hit_dmg = float(actor.damage_bonus)
    crit_dmg = hit_dmg * 2

    outcomes = build_strike_outcomes(actor.attack_bonus, target_ac,
                                     hit_dmg, crit_dmg, action.target_name)

    return ActionResult(action=action, outcomes=tuple(outcomes))


# ---------------------------------------------------------------------------
# Spell attack roll
# ---------------------------------------------------------------------------

def evaluate_spell_attack_roll(
    action: Action, state: RoundState,
    actor: CombatantSnapshot, defn: SpellDefinition,
) -> ActionResult:
    """Spell attack roll vs AC. MAP applies (Attack trait).
    Not a top-level evaluator — called by evaluate_spell() in actions.py.
    Note: ranged-in-melee penalty is NOT a PF2e Remaster rule.
    (AoN: https://2e.aonprd.com/Spells.aspx?ID=1375 — Needle Darts)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No valid target")

    penalty = map_penalty(actor.map_count + 1, agile=False)
    atk_bonus = spell_attack_bonus(actor.character) + penalty

    # Cover bonus for spell attacks
    cover_bonus = 0
    if getattr(state, 'grid', None) is not None:
        from sim.grid import compute_cover_level
        cover_bonus = compute_cover_level(
            actor.position, target.position, state.grid).value

    eff_ac = effective_target_ac(
        target, actor.position, state, cover_bonus=cover_bonus)

    base_dmg = defn.damage_dice * die_average(defn.damage_die) + defn.damage_bonus
    crit_dmg = base_dmg * 2

    outcomes = build_strike_outcomes(atk_bonus, eff_ac, base_dmg, crit_dmg,
                                     action.target_name)

    return ActionResult(action=action, outcomes=tuple(outcomes))
