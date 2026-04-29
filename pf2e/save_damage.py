"""pf2e/save_damage.py — BasicSave Damage Chassis (CP10.4.4)

Shared math for basic-save damage actions. Two callers:
  evaluate_save_damage_spell — single-target save spell (from evaluate_spell)
  aoe_enemy_ev / aoe_friendly_fire_ev — AoE damage (from evaluate_mortar_launch)

Basic save fractions (defender perspective):
  crit success = 0, success = half, failure = full, crit failure = double
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2297)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pf2e.combat_math import die_average, enumerate_d20_outcomes
from pf2e.types import SaveType

if TYPE_CHECKING:
    from pf2e.actions import Action, ActionOutcome, ActionResult
    from pf2e.spells import SpellDefinition
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


def basic_save_ev(dc: int, save_mod: int, base_dmg: float) -> float:
    """Expected damage of a basic save for one target.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2297)
    """
    outcomes = enumerate_d20_outcomes(save_mod, dc)
    return (
        (outcomes.critical_failure / 20) * base_dmg * 2.0
        + (outcomes.failure / 20) * base_dmg
        + (outcomes.success / 20) * base_dmg * 0.5
        # critical_success: 0 damage
    )


def aoe_enemy_ev(
    dc: int,
    save_type: SaveType,
    base_dmg: float,
    enemies: list[EnemySnapshot],
) -> float:
    """Total basic-save EV against a list of enemy snapshots.

    Skips dead enemies (current_hp <= 0).
    """
    total = 0.0
    for e in enemies:
        if e.current_hp <= 0:
            continue
        save_mod = e.saves.get(save_type, 0)
        total += basic_save_ev(dc, save_mod, base_dmg)
    return total


def aoe_friendly_fire_ev(
    dc: int,
    save_type: SaveType,
    base_dmg: float,
    allies_in_burst: list[CombatantSnapshot],
) -> float:
    """EV of damage dealt to pre-filtered allies in the burst area.

    Caller determines which allies are in the burst. This function
    does the save math only. Burst geometry deferred to CP10.6.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2384 — AoE hits all creatures)
    """
    from pf2e.combat_math import save_bonus

    total = 0.0
    for ally in allies_in_burst:
        if ally.current_hp <= 0:
            continue
        mod = save_bonus(ally.character, save_type)
        total += basic_save_ev(dc, mod, base_dmg)
    return total


def evaluate_save_damage_spell(
    action: Action,
    state: RoundState,
    actor: CombatantSnapshot,
    defn: SpellDefinition,
) -> ActionResult:
    """Single-target basic save spell. EV-collapsed (probability=1.0).

    Called from evaluate_spell() when defn.pattern == SAVE_FOR_DAMAGE.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2297)
    """
    from pf2e.actions import ActionOutcome, ActionResult
    from pf2e.combat_math import class_dc

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason="No valid target",
        )
    dice = defn.damage_dice
    if defn.scales_with_actions:
        extra_actions = action.action_cost - 1
        dice += extra_actions * 4  # generic scaling placeholder
    base_dmg = dice * die_average(defn.damage_die) + defn.damage_bonus
    dc = class_dc(actor.character)
    save_mod = target.saves.get(defn.save_type, 0)
    ev = basic_save_ev(dc, save_mod, base_dmg)
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            hp_changes={action.target_name: -ev},
            description=f"{defn.name}: EV {ev:.2f}",
        ),),
    )
