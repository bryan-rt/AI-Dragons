"""sim/verbose.py — Verbose per-action formatting for combat output.

Formats TurnPlan action results as human-readable probability breakdowns.
All lines are guaranteed <= 80 characters.

Pure presentation — no behavior changes.
(AoN MAP: https://2e.aonprd.com/Rules.aspx?ID=2188)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pf2e.actions import Action, ActionResult
    from sim.round_state import RoundState
    from sim.search import TurnPlan

MAX_LINE = 80


def format_verbose_turn(plan: TurnPlan, pre_state: RoundState) -> str:
    """Format one combatant's turn with per-action probability breakdown.

    pre_state: RoundState AFTER _reset_turn_state, BEFORE the first action.
    plan.intermediate_states[i]: state AFTER plan.actions[i].
    Returns a multi-line string (no trailing newline), or "" if empty.
    """
    if not plan.action_results:
        return ""

    lines: list[str] = []
    for i, (action, result) in enumerate(
        zip(plan.actions, plan.action_results)
    ):
        pre = pre_state if i == 0 else plan.intermediate_states[i - 1]
        post = plan.intermediate_states[i]
        action_lines = format_verbose_action(
            i + 1, action, result, pre, post)
        lines.extend(action_lines)

    return "\n".join(lines)


def format_verbose_action(
    index: int,
    action: Action,
    result: ActionResult,
    pre_state: RoundState,
    post_state: RoundState,
) -> list[str]:
    """Format one action's verbose detail lines.

    index: 1-based action number (shown in main output, verbose lines
    are indented underneath).
    """
    from pf2e.actions import ActionType

    lines: list[str] = []

    if action.type == ActionType.STRIKE:
        lines.extend(_format_strike_detail(
            action, result, pre_state, post_state))
    elif action.type in (
        ActionType.STRIDE, ActionType.STEP, ActionType.CRAWL,
    ):
        lines.extend(_format_movement_detail(action, pre_state))
    elif action.type == ActionType.ACTIVATE_TACTIC:
        lines.extend(_format_tactic_detail(
            action, result, pre_state, post_state))
    elif action.type == ActionType.CAST_SPELL:
        lines.extend(_format_spell_detail(
            action, result, pre_state, post_state))
    elif action.type in (
        ActionType.DEMORALIZE, ActionType.TRIP, ActionType.DISARM,
        ActionType.CREATE_A_DIVERSION, ActionType.FEINT,
    ):
        lines.extend(_format_skill_detail(action, result))
    elif action.type == ActionType.ANTHEM:
        lines.extend(_format_anthem_detail(action, pre_state))

    return [_clamp(ln) for ln in lines]


# -------------------------------------------------------------------
# Strike detail
# -------------------------------------------------------------------

def _format_strike_detail(
    action: Action,
    result: ActionResult,
    pre_state: RoundState,
    post_state: RoundState,
) -> list[str]:
    """Strike probability breakdown lines."""
    from pf2e.combat_math import map_penalty

    lines: list[str] = []

    # Determine MAP display from pre-action state
    if action.actor_name in pre_state.pcs:
        actor = pre_state.pcs[action.actor_name]
        is_agile = False
        for eq in actor.character.equipped_weapons:
            if (not action.weapon_name
                    or eq.weapon.name == action.weapon_name):
                is_agile = eq.weapon.is_agile
                break
        penalty = map_penalty(actor.map_count + 1, agile=is_agile)
    elif action.actor_name in pre_state.enemies:
        actor = pre_state.enemies[action.actor_name]
        penalty = map_penalty(actor.map_count + 1, agile=False)
    else:
        penalty = 0
    map_str = f"map={penalty:+d}" if penalty != 0 else "map=0"

    # Target AC
    target_ac = _get_ac(action.target_name, pre_state)

    # Parse outcomes into miss/hit/crit
    miss_prob, hit_prob, crit_prob = 0.0, 0.0, 0.0
    hit_dmg, crit_dmg = 0.0, 0.0
    for o in result.outcomes:
        if not o.hp_changes:
            miss_prob += o.probability
        else:
            dmg = abs(next(iter(o.hp_changes.values()), 0.0))
            if "crit" in o.description.lower():
                crit_prob += o.probability
                crit_dmg = dmg
            else:
                hit_prob += o.probability
                hit_dmg = dmg

    lines.append(f"     {map_str}  vs AC {target_ac}")
    prob_parts: list[str] = []
    if miss_prob > 0:
        prob_parts.append(f"Miss {miss_prob:.0%}")
    if hit_prob > 0:
        prob_parts.append(f"Hit {hit_dmg:.1f} ({hit_prob:.0%})")
    if crit_prob > 0:
        prob_parts.append(
            f"Crit {crit_dmg:.1f} ({crit_prob:.0%})")
    lines.append(f"     {' | '.join(prob_parts)}")

    # EV and HP delta
    ev = sum(
        abs(next(iter(o.hp_changes.values()), 0.0)) * o.probability
        for o in result.outcomes if o.hp_changes
    )
    hp_str = _hp_delta(action.target_name, pre_state, post_state)
    lines.append(f"     EV: {ev:.2f} dmg  {hp_str}")

    return lines


# -------------------------------------------------------------------
# Movement detail
# -------------------------------------------------------------------

def _format_movement_detail(
    action: Action,
    pre_state: RoundState,
) -> list[str]:
    """Stride/Step/Crawl: show from-position."""
    if action.actor_name in pre_state.pcs:
        from_pos = pre_state.pcs[action.actor_name].position
    elif action.actor_name in pre_state.enemies:
        from_pos = pre_state.enemies[action.actor_name].position
    else:
        return []
    return [f"     from {from_pos}"]


# -------------------------------------------------------------------
# Tactic detail
# -------------------------------------------------------------------

def _format_tactic_detail(
    action: Action,
    result: ActionResult,
    pre_state: RoundState,
    post_state: RoundState,
) -> list[str]:
    """ACTIVATE_TACTIC: show squadmate + outcome probabilities."""
    lines: list[str] = []
    if not result.outcomes:
        return lines

    # Extract description from first non-trivial outcome
    desc = ""
    for o in result.outcomes:
        if o.description:
            desc = o.description
            break

    # Extract squadmate reference from description (-> Name ...)
    if "\u2192" in desc:
        detail = desc.split("\u2192", 1)[1].strip()
        lines.append(f"     \u2192 {detail[:60]}")

    # Probability breakdown from outcomes
    miss_prob, hit_prob, crit_prob = 0.0, 0.0, 0.0
    hit_dmg, crit_dmg = 0.0, 0.0
    for o in result.outcomes:
        if not o.hp_changes:
            miss_prob += o.probability
        else:
            dmg = abs(next(iter(o.hp_changes.values()), 0.0))
            if "crit" in o.description.lower():
                crit_prob += o.probability
                crit_dmg = dmg
            else:
                hit_prob += o.probability
                hit_dmg = dmg

    if hit_prob + crit_prob > 0:
        prob_parts: list[str] = []
        if miss_prob > 0:
            prob_parts.append(f"Miss {miss_prob:.0%}")
        if hit_prob > 0:
            prob_parts.append(
                f"Hit {hit_dmg:.1f} ({hit_prob:.0%})")
        if crit_prob > 0:
            prob_parts.append(
                f"Crit {crit_dmg:.1f} ({crit_prob:.0%})")
        lines.append(f"     {' | '.join(prob_parts)}")

        ev = sum(
            abs(next(iter(o.hp_changes.values()), 0.0))
            * o.probability
            for o in result.outcomes if o.hp_changes
        )
        # Find primary target
        target = ""
        for o in result.outcomes:
            if o.hp_changes:
                target = next(iter(o.hp_changes.keys()), "")
                break
        hp_str = _hp_delta(
            target, pre_state, post_state) if target else ""
        lines.append(f"     EV: {ev:.2f} dmg  {hp_str}")

    return lines


# -------------------------------------------------------------------
# Spell detail
# -------------------------------------------------------------------

def _format_spell_detail(
    action: Action,
    result: ActionResult,
    pre_state: RoundState,
    post_state: RoundState,
) -> list[str]:
    """Spell: auto-hit vs save vs attack roll."""
    if not result.outcomes:
        return []

    # Auto-hit: single outcome with prob ~1.0
    if (len(result.outcomes) == 1
            and result.outcomes[0].probability > 0.99):
        o = result.outcomes[0]
        if o.hp_changes:
            dmg = abs(next(iter(o.hp_changes.values()), 0.0))
            target = next(
                iter(o.hp_changes.keys()), action.target_name)
            hp_str = _hp_delta(target, pre_state, post_state)
            return [f"     auto-hit: {dmg:.1f} dmg  {hp_str}"]
        return []

    # Attack roll or save: multiple outcomes — reuse strike format
    return _format_strike_detail(
        action, result, pre_state, post_state)


# -------------------------------------------------------------------
# Skill action detail
# -------------------------------------------------------------------

def _format_skill_detail(
    action: Action,
    result: ActionResult,
) -> list[str]:
    """Demoralize, Trip, Feint, CaD, Disarm outcomes."""
    parts: list[str] = []
    for o in result.outcomes:
        if o.probability < 0.001:
            continue
        pct = f"{o.probability:.0%}"
        if o.conditions_applied:
            conds: list[str] = []
            for _name, cs in o.conditions_applied.items():
                conds.extend(cs)
            label = ", ".join(conds[:2])
        elif o.description:
            label = o.description.split(":")[0].strip()[:30]
        else:
            label = "no effect"
        parts.append(f"{label} ({pct})")
    if parts:
        return [f"     {' | '.join(parts)}"]
    return []


# -------------------------------------------------------------------
# Anthem / buff detail
# -------------------------------------------------------------------

def _format_anthem_detail(
    action: Action,
    pre_state: RoundState,
) -> list[str]:
    """Show which allies are in anthem aura range."""
    if action.actor_name not in pre_state.pcs:
        return []
    actor_pos = pre_state.pcs[action.actor_name].position
    allies: list[str] = []
    for name, pc in pre_state.pcs.items():
        if name == action.actor_name or pc.current_hp <= 0:
            continue
        dr = abs(pc.position[0] - actor_pos[0])
        dc = abs(pc.position[1] - actor_pos[1])
        diag = min(dr, dc)
        dist = ((diag // 2) * 10 + ((diag + 1) // 2) * 5
                + abs(dr - dc) * 5)
        if dist <= 60:
            allies.append(name)
    if allies:
        return [f"     aura: {', '.join(allies)}"]
    return ["     aura: no allies in range"]


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _get_ac(name: str, state: RoundState) -> int:
    """Look up a combatant's AC from RoundState."""
    if name in state.enemies:
        return state.enemies[name].ac
    if name in state.pcs:
        from pf2e.combat_math import armor_class
        return armor_class(state.pcs[name])
    return 0


def _hp_delta(
    name: str,
    pre_state: RoundState,
    post_state: RoundState,
) -> str:
    """Return '[Name: 23->16]' or '[Name: 16]' if HP unchanged."""
    def _get_hp(st: RoundState, n: str) -> int | None:
        if n in st.pcs:
            return st.pcs[n].current_hp
        if n in st.enemies:
            return st.enemies[n].current_hp
        return None

    pre_hp = _get_hp(pre_state, name)
    post_hp = _get_hp(post_state, name)
    if pre_hp is None or post_hp is None:
        return ""
    if pre_hp != post_hp:
        return f"[{name}: {pre_hp}\u2192{post_hp}]"
    return f"[{name}: {post_hp}]"


def _clamp(line: str, max_len: int = MAX_LINE) -> str:
    """Truncate line to max_len with ellipsis if needed."""
    if len(line) <= max_len:
        return line
    return line[:max_len - 1] + "\u2026"
