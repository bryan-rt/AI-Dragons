"""pf2e/save_condition.py — SaveCondition Chassis (CP10.4.5)

Non-basic save → conditions by degree of success.
Reads SpellDefinition.condition_by_degree generically.

Currently handles: Fear (frightened + fleeing).
Incapacitation trait degree-shift deferred — Fear lacks the trait.
(AoN Fear: https://2e.aonprd.com/Spells.aspx?ID=1524)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pf2e.combat_math import class_dc, die_average, enumerate_d20_outcomes

if TYPE_CHECKING:
    from pf2e.actions import Action, ActionOutcome, ActionResult
    from pf2e.spells import SpellDefinition
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


# Degree label prefix → checked longest-first so "crit_failure" doesn't
# match "failure". Order matters for startswith matching.
_DEGREE_PREFIXES = ["crit_success", "crit_failure", "success", "failure"]


def _enemy_avg_damage(target: EnemySnapshot) -> float:
    """Average damage per attack from an enemy's damage_dice + damage_bonus.

    Uses split("d", 1) to correctly handle multi-dice strings ("2d8").
    NOTE: old flee_ev code used split('d')[1] which ignores dice count —
    this is a correctness fix. No impact on "1d8" targets (e.g. Bandit1).
    """
    if not target.damage_dice or "d" not in target.damage_dice:
        return float(target.damage_bonus)
    parts = target.damage_dice.split("d", 1)
    return int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus


def condition_ev(
    condition_name: str,
    condition_value: int,
    target: EnemySnapshot,
) -> float:
    """EV of applying one condition instance to a target.

    "frightened": each level reduces all enemy checks/DCs by 1.
        value * 0.05 * attacks * avg_dmg * 2
        (x2: both offensive reduction and defensive reduction)
    "fleeing": target cannot attack for one round.
        attacks * avg_dmg (full turn prevented; conservative)
        (AoN: https://2e.aonprd.com/Conditions.aspx?ID=17)
    "" or unknown: 0.0
    """
    if not condition_name:
        return 0.0
    avg = _enemy_avg_damage(target)
    if condition_name == "frightened":
        return condition_value * 0.05 * target.num_attacks_per_turn * avg * 2
    if condition_name == "fleeing":
        return target.num_attacks_per_turn * avg
    return 0.0


def evaluate_condition_spell(
    action: Action,
    state: RoundState,
    actor: CombatantSnapshot,
    defn: SpellDefinition,
) -> ActionResult:
    """Non-basic save → conditions by degree.

    Reads defn.condition_by_degree generically. Merges multiple
    entries with the same degree prefix into one ActionOutcome.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2195)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason="No valid target",
        )

    dc = class_dc(actor.character)
    save_mod = target.saves.get(defn.save_type, 0)
    d20 = enumerate_d20_outcomes(save_mod, dc)

    degree_probs = {
        "crit_success": d20.critical_success / 20,
        "crit_failure": d20.critical_failure / 20,
        "success":      d20.success / 20,
        "failure":      d20.failure / 20,
    }

    # Group condition_by_degree entries by degree prefix.
    # Each bucket: [condition_tags], cumulative_score_delta
    buckets: dict[str, tuple[list[str], float]] = {
        d: ([], 0.0) for d in _DEGREE_PREFIXES
    }
    for label, cond_name, cond_value in defn.condition_by_degree:
        for degree in _DEGREE_PREFIXES:
            if label.startswith(degree):
                cond_list, ev_total = buckets[degree]
                if cond_name:
                    cond_list.append(
                        f"{cond_name}_{cond_value}" if cond_value
                        else cond_name
                    )
                ev_total += condition_ev(cond_name, cond_value, target)
                buckets[degree] = (cond_list, ev_total)
                break

    outcomes: list[ActionOutcome] = []
    for degree in _DEGREE_PREFIXES:
        prob = degree_probs[degree]
        if prob <= 0:
            continue
        cond_list, score = buckets[degree]
        conditions_applied = (
            {action.target_name: tuple(cond_list)} if cond_list else {}
        )
        outcomes.append(ActionOutcome(
            probability=prob,
            conditions_applied=conditions_applied,
            score_delta=score,
            description=(
                f"{defn.name} {degree}: "
                + (", ".join(cond_list) if cond_list else "no effect")
            ),
        ))

    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))
